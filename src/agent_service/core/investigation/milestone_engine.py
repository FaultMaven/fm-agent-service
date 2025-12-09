"""Milestone-Based Investigation Engine

This module implements the new milestone-based investigation system that replaces
the old OODA framework. Instead of rigid phase orchestration, this engine completes
milestones opportunistically based on data availability.

Key Differences from OODA:
- NO phase transitions - milestones complete when data is available
- NO sequential constraints - multiple milestones can complete in one turn
- Status-based prompt generation instead of phase-based
- Progress tracked via InvestigationProgress, not phase transitions

Design Reference:
- docs/architecture/milestone-based-investigation-framework.md
- docs/architecture/prompt-implementation-examples.md

Architecture:
- Process turn → Generate status-based prompt → Invoke LLM → Process response
- Update milestones based on LLM state_updates
- Track turn progress for analytics
- Automatic status transitions (INVESTIGATING → RESOLVED)
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from fm_core_lib.models import (
    Case,
    CaseStatus,
    ConsultingData,
    Evidence,
    EvidenceCategory,
    EvidenceForm,
    EvidenceSourceType,
    Hypothesis,
    HypothesisCategory,
    HypothesisGenerationMode,
    HypothesisStatus,
    HypothesisEvidenceLink,
    EvidenceStance,
    InvestigationProgress,
    InvestigationStage,
    PathSelection,
    InvestigationPath,
    ProblemVerification,
    Solution,
    SolutionType,
    TurnProgress,
    TurnOutcome,
    TemporalState,
    UrgencyLevel,
    WorkingConclusion,
    RootCauseConclusion,
    ConfidenceLevel,
    DegradedMode,
    DegradedModeType,
)
from fm_core_lib.models.case import determine_investigation_path
from fm_core_lib.clients import CaseServiceClient
from typing import Protocol
import json

from .llm_schemas import (
    get_tools_for_status,
    get_tools_for_milestone_stage,
    MILESTONE_UPDATE_TOOL,
    EVIDENCE_ANALYSIS_TOOL,
    HYPOTHESIS_EVALUATION_TOOL,
    HYPOTHESIS_GENERATION_TOOL,
    PATH_SELECTION_TOOL
)

class ILLMProvider(Protocol):
    """LLM Provider interface for type hints"""
    pass


logger = logging.getLogger(__name__)


# =============================================================================
# Milestone Engine - Main Implementation
# =============================================================================


class MilestoneEngine:
    """
    Milestone-based investigation engine.

    Replaces the old OODA engine with a simpler, more flexible approach where
    the agent completes milestones opportunistically based on available data.

    Responsibilities:
    - Generate prompts based on case status (CONSULTING, INVESTIGATING, RESOLVED)
    - Invoke LLM with appropriate schema
    - Process LLM responses and update case state
    - Track milestone completion and turn progress
    - Automatic status transitions when milestones complete

    Key Design Principles:
    - No phase orchestration - milestones complete when data is available
    - Status-based prompts instead of phase-based
    - Multiple milestones can complete in single turn
    - Repository abstraction for persistence (no direct DB access)
    """

    def __init__(
        self,
        llm_provider: ILLMProvider,
        case_service_client: CaseServiceClient,
        trace_enabled: bool = True
    ):
        """Initialize milestone engine.

        Args:
            llm_provider: LLM provider implementation (ILLMProvider interface)
            case_service_client: HTTP client for case service communication (stateless)
            trace_enabled: Enable observability tracing
        """
        self.llm_provider = llm_provider
        self.case_client = case_service_client
        self.trace_enabled = trace_enabled

        logger.info("MilestoneEngine initialized with milestone-based architecture (stateless)")

    async def process_turn(
        self,
        case: Case,
        user_message: str,
        attachments: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Process a single conversation turn.

        This is the main entry point for the milestone engine. It:
        1. Generates status-appropriate prompt
        2. Invokes LLM with structured output
        3. Processes response and updates case state
        4. Records turn progress
        5. Checks for automatic status transitions

        Args:
            case: Current case
            user_message: User's message this turn
            attachments: Optional file attachments

        Returns:
            {
                "agent_response": str,        # Natural language response to user
                "case_updated": Case,         # Updated case object
                "metadata": {
                    "turn_number": int,
                    "milestones_completed": List[str],
                    "progress_made": bool,
                    "status_transitioned": bool,
                    "outcome": TurnOutcome
                }
            }

        Raises:
            MilestoneEngineError: If processing fails
        """
        logger.info(
            f"Processing turn {case.current_turn + 1} for case {case.case_id} "
            f"(status: {case.status})"
        )

        try:
            # Step 1: Generate status-based prompt
            prompt = self._build_prompt(case, user_message, attachments)

            # Step 2: Get appropriate tools for structured output
            tools = get_tools_for_status(case.status.value)

            # Step 3: Invoke LLM with structured output
            # Task type "chat" for main diagnostic conversations
            # (Future: "multimodal" for images, "synthesis" for KB queries)
            llm_response = await self.llm_provider.generate(
                prompt=prompt,
                temperature=0.7,
                max_tokens=4000,
                tools=tools if tools else None,
                tool_choice="auto" if tools else None
            )

            # Step 4: Extract response text and tool calls
            # Note: llm_response is a string directly, not an object with .content
            llm_response_text = llm_response
            tool_calls = None  # Tool calls handling would need separate implementation

            # Step 5: Process response and update state
            updated_case, turn_metadata = await self._process_response(
                case=case,
                user_message=user_message,
                llm_response=llm_response_text,
                tool_calls=tool_calls,
                attachments=attachments
            )

            # Step 5: Increment turn counter
            updated_case.current_turn += 1

            # Step 6: Record turn progress
            turn_record = self._create_turn_record(
                turn_number=updated_case.current_turn,
                milestones_completed=turn_metadata.get("milestones_completed", []),
                evidence_added=turn_metadata.get("evidence_added", []),
                hypotheses_generated=turn_metadata.get("hypotheses_generated", []),
                hypotheses_validated=turn_metadata.get("hypotheses_validated", []),
                solutions_proposed=turn_metadata.get("solutions_proposed", []),
                progress_made=turn_metadata.get("progress_made", False),
                outcome=turn_metadata.get("outcome", TurnOutcome.CONVERSATION),
                user_message=user_message,
                agent_response=llm_response_text
            )
            updated_case.turn_history.append(turn_record)

            # Step 7: Update progress tracking
            if turn_metadata.get("progress_made", False):
                updated_case.turns_without_progress = 0
            else:
                updated_case.turns_without_progress += 1

            # Step 8: Check degraded mode entry/exit
            if turn_metadata.get("progress_made", False):
                # Exit degraded mode if progress made
                self._check_degraded_mode_exit(updated_case, True)
            elif updated_case.turns_without_progress >= 3 and updated_case.degraded_mode is None:
                # Enter degraded mode after 3 turns without progress
                self._enter_degraded_mode(updated_case, "no_progress")

            # Step 9: Check automatic status transitions
            self._check_automatic_transitions(updated_case)

            # Step 10: Save case via HTTP client (stateless microservice)
            updated_case.updated_at = datetime.now(timezone.utc)
            updated_case.last_activity_at = datetime.now(timezone.utc)
            await self.case_client.update_case(case.case_id, updated_case)

            logger.info(
                f"Turn {updated_case.current_turn} processed successfully. "
                f"Status: {updated_case.status}, "
                f"Progress made: {turn_metadata.get('progress_made', False)}"
            )

            return {
                "agent_response": llm_response_text,
                "case_updated": updated_case,
                "metadata": {
                    "turn_number": updated_case.current_turn,
                    "milestones_completed": turn_metadata.get("milestones_completed", []),
                    "progress_made": turn_metadata.get("progress_made", False),
                    "status_transitioned": turn_metadata.get("status_transitioned", False),
                    "outcome": turn_metadata.get("outcome", TurnOutcome.CONVERSATION),
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            }

        except Exception as e:
            logger.error(
                f"Error processing turn for case {case.case_id}: {e}",
                exc_info=True
            )
            raise MilestoneEngineError(f"Turn processing failed: {e}") from e

    # =========================================================================
    # Prompt Generation
    # =========================================================================

    def _build_prompt(
        self,
        case: Case,
        user_message: str,
        attachments: Optional[List[Dict[str, Any]]] = None
    ) -> str:
        """
        Build status-appropriate prompt for LLM.

        Generates different prompts based on case status:
        - CONSULTING: Problem understanding and confirmation
        - INVESTIGATING: Milestone-based investigation
        - RESOLVED/CLOSED: Documentation and retrospective

        Args:
            case: Current case
            user_message: User's message
            attachments: Optional file attachments

        Returns:
            Complete prompt string
        """
        if case.status == CaseStatus.CONSULTING:
            return self._build_consulting_prompt(case, user_message)
        elif case.status == CaseStatus.INVESTIGATING:
            return self._build_investigating_prompt(case, user_message, attachments)
        elif case.status in [CaseStatus.RESOLVED, CaseStatus.CLOSED]:
            return self._build_terminal_prompt(case, user_message)
        else:
            raise MilestoneEngineError(f"Unknown case status: {case.status}")

    def _build_consulting_prompt(self, case: Case, user_message: str) -> str:
        """Build prompt for CONSULTING status."""
        return f"""You are FaultMaven, an AI troubleshooting copilot. The user is exploring a problem.

Status: CONSULTING (pre-investigation)
Turn: {case.current_turn + 1}

User Message:
{user_message}

Your Task:
1. Understand the user's problem
2. Ask clarifying questions if needed
3. Propose a clear, specific problem statement
4. Suggest quick fixes if obvious
5. Determine if formal investigation is needed

Current Context:
- Proposed Problem Statement: {case.consulting.proposed_problem_statement or "Not yet defined"}
- Problem Confirmed: {case.consulting.problem_statement_confirmed}
- Decided to Investigate: {case.consulting.decided_to_investigate}

Respond naturally and helpfully. If you have enough information, propose a clear problem statement.
If the user confirms it and wants to investigate, let them know you're ready to start."""

    def _build_investigating_prompt(
        self,
        case: Case,
        user_message: str,
        attachments: Optional[List[Dict[str, Any]]] = None
    ) -> str:
        """Build prompt for INVESTIGATING status."""

        # Build milestone status
        progress = case.progress
        milestones_status = f"""
Milestones Completed:
- Symptom Verified: {progress.symptom_verified}
- Scope Assessed: {progress.scope_assessed}
- Timeline Established: {progress.timeline_established}
- Changes Identified: {progress.changes_identified}
- Root Cause Identified: {progress.root_cause_identified} (confidence: {progress.root_cause_confidence:.2f})
- Solution Proposed: {progress.solution_proposed}
- Solution Applied: {progress.solution_applied}
- Solution Verified: {progress.solution_verified}

Current Stage: {progress.current_stage}
Progress: {len(progress.completed_milestones)}/8 milestones complete
"""

        # Build evidence summary
        evidence_summary = ""
        if case.evidence:
            evidence_summary = f"\nEvidence Collected ({len(case.evidence)} items):\n"
            for ev in case.evidence[-5:]:  # Last 5 evidence items
                evidence_summary += f"- [{ev.category.value}] {ev.summary}\n"

        # Build hypothesis summary
        hypothesis_summary = ""
        if case.hypotheses:
            active = [h for h in case.hypotheses.values() if h.status == HypothesisStatus.ACTIVE]
            if active:
                hypothesis_summary = f"\nActive Hypotheses ({len(active)}):\n"
                for h in active[:3]:  # Top 3 hypotheses
                    hypothesis_summary += f"- {h.statement} (likelihood: {h.likelihood:.2f})\n"

        # Build attachments note
        attachments_note = ""
        if attachments:
            attachments_note = f"\nAttachments Provided: {len(attachments)} file(s)"

        return f"""You are FaultMaven, an AI troubleshooting copilot conducting a formal investigation.

Status: INVESTIGATING
Case: {case.title}
Description: {case.description}
Turn: {case.current_turn + 1}

{milestones_status}

{evidence_summary}

{hypothesis_summary}

User Message:
{user_message}
{attachments_note}

Your Task:
Complete as many milestones as possible based on available data. You can complete multiple milestones in one turn.

If the user provides comprehensive data (logs, metrics, etc.), analyze it thoroughly and:
1. Verify symptoms and assess scope
2. Establish timeline and identify changes
3. Identify root cause if evidence is clear
4. Propose solution if root cause is known

Key Principles:
- Milestones complete opportunistically (not sequentially)
- Use evidence to advance investigation
- Generate hypotheses only when root cause is unclear
- Focus on solving the problem efficiently

Respond with your analysis and next steps."""

    def _build_terminal_prompt(self, case: Case, user_message: str) -> str:
        """Build prompt for RESOLVED/CLOSED status."""
        return f"""You are FaultMaven, an AI troubleshooting copilot. This case is closed.

Status: {case.status.upper()}
Case: {case.title}
Closure Reason: {case.closure_reason}
Closed At: {case.closed_at.isoformat() if case.closed_at else 'Unknown'}

User Message:
{user_message}

Your Task:
- Answer questions about the investigation
- Provide documentation or summaries if requested
- Clarify findings or recommendations
- DO NOT reopen investigation or modify case state

The investigation is complete. Focus on documentation and knowledge sharing."""

    # =========================================================================
    # Response Processing
    # =========================================================================

    async def _process_response(
        self,
        case: Case,
        user_message: str,
        llm_response: str,
        tool_calls: Optional[List[Any]] = None,
        attachments: Optional[List[Dict[str, Any]]] = None
    ) -> Tuple[Case, Dict[str, Any]]:
        """
        Process LLM response and update case state.

        This is where the milestone completion logic lives. Based on the LLM's
        response (including structured tool calls) and any provided evidence, we update:
        - Milestone completion flags (via structured output)
        - Evidence collection and categorization (via structured output)
        - Hypothesis generation/validation (via structured output)
        - Solutions

        Args:
            case: Current case
            user_message: User's message
            llm_response: LLM's response text
            tool_calls: Optional structured tool calls from LLM
            attachments: Optional attachments

        Returns:
            (updated_case, turn_metadata)
        """
        # Track what changed this turn
        milestones_completed = []
        evidence_added = []
        hypotheses_generated = []
        hypotheses_validated = []
        solutions_proposed = []

        # Process based on status
        if case.status == CaseStatus.CONSULTING:
            # Track uploaded files (files can be uploaded during CONSULTING)
            # NOTE: Files are NOT evidence yet - evidence is created during INVESTIGATING phase
            files_uploaded = []
            if attachments:
                for attachment in attachments:
                    uploaded_file = self._create_uploaded_file_from_attachment(
                        case=case,
                        attachment=attachment,
                        turn_number=case.current_turn + 1
                    )
                    case.uploaded_files.append(uploaded_file)
                    files_uploaded.append(uploaded_file.file_id)

            # Check for problem statement confirmation
            if "yes" in user_message.lower() or "correct" in user_message.lower():
                if case.consulting.proposed_problem_statement:
                    case.consulting.problem_statement_confirmed = True
                    case.consulting.problem_statement_confirmed_at = datetime.now(timezone.utc)

            # Check for investigation decision
            if "investigate" in user_message.lower() or "go ahead" in user_message.lower():
                if case.consulting.problem_statement_confirmed:
                    case.consulting.decided_to_investigate = True
                    case.consulting.decision_made_at = datetime.now(timezone.utc)

            # Check if should transition to INVESTIGATING
            status_transitioned = False
            if (case.consulting.problem_statement_confirmed and
                case.consulting.decided_to_investigate):
                await self._transition_to_investigating(case)
                status_transitioned = True

            metadata = {
                "progress_made": case.consulting.problem_statement_confirmed or len(files_uploaded) > 0,
                "outcome": TurnOutcome.DATA_PROVIDED if attachments else TurnOutcome.CONVERSATION,
                "status_transitioned": status_transitioned,
                "files_uploaded": files_uploaded  # Track uploaded files, not evidence (evidence only in INVESTIGATING)
            }

        elif case.status == CaseStatus.INVESTIGATING:
            # Track uploaded files AND create evidence from attachments
            if attachments:
                for attachment in attachments:
                    # 1. Track as uploaded file (for file count)
                    uploaded_file = self._create_uploaded_file_from_attachment(
                        case=case,
                        attachment=attachment,
                        turn_number=case.current_turn + 1
                    )
                    case.uploaded_files.append(uploaded_file)

                    # 2. Create evidence from file (for hypothesis evaluation)
                    evidence = self._create_evidence_from_attachment(
                        case=case,
                        attachment=attachment,
                        turn_number=case.current_turn + 1
                    )
                    case.evidence.append(evidence)
                    evidence_added.append(evidence.evidence_id)

            # Process structured tool calls from LLM
            if tool_calls:
                for tool_call in tool_calls:
                    function_name = tool_call.function.get("name")
                    arguments_str = tool_call.function.get("arguments", "{}")

                    try:
                        arguments = json.loads(arguments_str) if isinstance(arguments_str, str) else arguments_str
                    except json.JSONDecodeError:
                        logger.error(f"Failed to parse tool call arguments: {arguments_str}")
                        continue

                    # Handle different tool calls
                    if function_name == "update_milestones":
                        milestones = self._process_milestone_updates(case, arguments)
                        milestones_completed.extend(milestones)

                    elif function_name == "analyze_evidence":
                        evidence_id = self._process_evidence_analysis(case, arguments)
                        if evidence_id:
                            evidence_added.append(evidence_id)

                    elif function_name == "generate_hypothesis":
                        hypothesis_id = self._process_hypothesis_generation(case, arguments)
                        if hypothesis_id:
                            hypotheses_generated.append(hypothesis_id)

                    elif function_name == "evaluate_hypothesis":
                        hypothesis_id = self._process_hypothesis_evaluation(case, arguments)
                        if hypothesis_id:
                            hypotheses_validated.append(hypothesis_id)

            # Fallback: Simple keyword-based detection if no tool calls
            # (For LLMs that don't support function calling)
            if not tool_calls:
                response_lower = llm_response.lower()

                if not case.progress.symptom_verified and "symptom" in response_lower:
                    case.progress.symptom_verified = True
                    milestones_completed.append("symptom_verified")

                if not case.progress.root_cause_identified and "root cause" in response_lower:
                    case.progress.root_cause_identified = True
                    case.progress.root_cause_confidence = 0.8
                    case.progress.root_cause_method = "direct_analysis"
                    milestones_completed.append("root_cause_identified")

                if not case.progress.solution_proposed and "solution" in response_lower:
                    case.progress.solution_proposed = True
                    milestones_completed.append("solution_proposed")

            # Determine outcome
            if milestones_completed:
                outcome = TurnOutcome.MILESTONE_COMPLETED
            elif attachments:
                outcome = TurnOutcome.DATA_PROVIDED
            else:
                outcome = TurnOutcome.CONVERSATION

            metadata = {
                "milestones_completed": milestones_completed,
                "evidence_added": evidence_added,
                "hypotheses_generated": hypotheses_generated,
                "hypotheses_validated": hypotheses_validated,
                "solutions_proposed": solutions_proposed,
                "progress_made": len(milestones_completed) > 0 or len(evidence_added) > 0,
                "outcome": outcome,
                "status_transitioned": False
            }

        else:  # RESOLVED or CLOSED
            metadata = {
                "progress_made": False,
                "outcome": TurnOutcome.CONVERSATION,
                "status_transitioned": False
            }

        return case, metadata

    # =========================================================================
    # State Management
    # =========================================================================

    async def _transition_to_investigating(self, case: Case) -> None:
        """
        Transition case from CONSULTING to INVESTIGATING.

        This creates the initial investigation structures, determines
        investigation path, and copies the confirmed problem statement.
        """
        logger.info(f"Transitioning case {case.case_id} to INVESTIGATING")

        # Change status
        case.status = CaseStatus.INVESTIGATING

        # Copy confirmed problem statement to description
        if case.consulting.proposed_problem_statement:
            case.description = case.consulting.proposed_problem_statement

        # Initialize investigation progress
        case.progress = InvestigationProgress()

        # Initialize problem verification with confirmed statement
        case.problem_verification = ProblemVerification(
            symptom_statement=case.description
        )

        # Invoke path selection if verification complete
        # (This happens when temporal_state and urgency_level are set)
        if (case.problem_verification.temporal_state and
            case.problem_verification.urgency_level):
            path_selection = determine_investigation_path(case.problem_verification)
            case.path_selection = path_selection

            logger.info(
                f"Path selection: {path_selection.path.value} "
                f"(auto={path_selection.auto_selected}, "
                f"rationale={path_selection.rationale})"
            )

        # Initialize empty collections (already defaults in Case model)
        # case.evidence, case.hypotheses, case.solutions, case.turn_history are defaults

    def _check_automatic_transitions(self, case: Case) -> None:
        """
        Check if case should automatically transition status.

        Automatic Transitions:
        - INVESTIGATING → RESOLVED when solution_verified=True
        """
        if (case.status == CaseStatus.INVESTIGATING and
            case.progress.solution_verified):

            case.status = CaseStatus.RESOLVED
            case.resolved_at = datetime.now(timezone.utc)
            case.closed_at = datetime.now(timezone.utc)
            case.closure_reason = "resolved"

            # Calculate time to resolution
            if case.created_at:
                delta = case.closed_at - case.created_at
                # Store as metadata (no direct field for this)

            logger.info(
                f"Case {case.case_id} automatically transitioned to RESOLVED "
                f"(solution verified)"
            )

    def _enter_degraded_mode(
        self,
        case: Case,
        mode_type: str,
        reason: Optional[str] = None
    ) -> None:
        """
        Enter degraded mode when investigation is stuck.

        Implements recovery strategies based on specification:
        1. Engagement shift (DISCOVERY → HYPOTHESIS → EXPERT)
        2. Broader questions to elicit more information
        3. Expert mode with deeper technical analysis

        Args:
            case: Current case
            mode_type: Type of degradation (no_progress, limited_data, etc.)
            reason: Optional detailed reason
        """
        if case.degraded_mode:
            logger.warning(f"Case {case.case_id} already in degraded mode")
            return

        # Determine reason if not provided
        if not reason:
            if mode_type == "no_progress":
                reason = f"No progress for {case.turns_without_progress} consecutive turns"
            else:
                reason = "Investigation limitations encountered"

        case.degraded_mode = DegradedMode(
            mode_type=DegradedModeType(mode_type),
            reason=reason,
            entered_at=datetime.now(timezone.utc),
            attempted_actions=[]
        )

        logger.info(
            f"Case {case.case_id} entered degraded mode: {mode_type} - {reason}"
        )

        # Implement recovery strategy based on mode type
        self._apply_degraded_mode_recovery(case)

    def _apply_degraded_mode_recovery(self, case: Case) -> None:
        """
        Apply recovery strategy for degraded mode.

        Recovery strategies from specification:
        1. NO_PROGRESS → Shift engagement mode, ask broader questions
        2. INSUFFICIENT_DATA → Request specific evidence
        3. CIRCULAR_REASONING → Force hypothesis reevaluation
        4. STALLED_VERIFICATION → Suggest alternative approaches
        """
        if not case.degraded_mode:
            return

        mode_type = case.degraded_mode.mode_type

        if mode_type == DegradedModeType.NO_PROGRESS:
            # Strategy: Shift engagement mode progressively
            current_stage = case.progress.current_stage

            if current_stage == InvestigationStage.PROBLEM_VERIFICATION:
                # Still in verification - suggest moving to hypothesis exploration
                case.degraded_mode.attempted_actions.append(
                    "engagement_shift_to_hypothesis"
                )
                logger.info("Recovery: Suggesting hypothesis exploration mode")

            elif current_stage == InvestigationStage.INVESTIGATION:
                # In investigation - suggest expert mode with deeper analysis
                case.degraded_mode.attempted_actions.append(
                    "engagement_shift_to_expert"
                )
                logger.info("Recovery: Suggesting expert technical analysis mode")

        elif mode_type == DegradedModeType.INSUFFICIENT_DATA:
            # Strategy: Request specific evidence types
            case.degraded_mode.attempted_actions.append(
                "request_specific_evidence"
            )
            logger.info("Recovery: Requesting specific evidence types")

        elif mode_type == DegradedModeType.CIRCULAR_REASONING:
            # Strategy: Force hypothesis reevaluation
            active_hypotheses = [
                h for h in case.hypotheses.values()
                if h.status == HypothesisStatus.ACTIVE
            ]
            for hypothesis in active_hypotheses:
                hypothesis.status = HypothesisStatus.NEEDS_MORE_DATA

            case.degraded_mode.attempted_actions.append(
                "force_hypothesis_reevaluation"
            )
            logger.info("Recovery: Forcing hypothesis reevaluation")

        elif mode_type == DegradedModeType.STALLED_VERIFICATION:
            # Strategy: Suggest alternative verification approaches
            case.degraded_mode.attempted_actions.append(
                "suggest_alternate_verification"
            )
            logger.info("Recovery: Suggesting alternative verification approaches")

    def _check_degraded_mode_exit(self, case: Case, progress_made: bool) -> None:
        """
        Check if case should exit degraded mode.

        Exit conditions:
        - Progress made on milestone
        - New evidence added
        - Hypothesis validated

        Args:
            case: Current case
            progress_made: Whether progress was made this turn
        """
        if not case.degraded_mode:
            return

        if progress_made:
            logger.info(
                f"Case {case.case_id} exiting degraded mode: Progress made"
            )
            case.degraded_mode = None
            case.turns_without_progress = 0

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _create_uploaded_file_from_attachment(
        self,
        case: Case,
        attachment: Dict[str, Any],
        turn_number: int
    ) -> "UploadedFile":
        """
        Create uploaded file record from attachment.

        Args:
            case: Current case
            attachment: Attachment metadata with file_id, filename, data_type, etc.
            turn_number: Current turn number

        Returns:
            UploadedFile object
        """
        from fm_core_lib.models import UploadedFile

        uploaded_file = UploadedFile(
            file_id=attachment.get('file_id', f"file_{uuid4().hex[:12]}"),
            filename=attachment.get('filename', 'unknown'),
            size_bytes=attachment.get('size', 0),
            data_type=attachment.get('data_type', 'unknown'),
            uploaded_at_turn=turn_number,
            uploaded_at=datetime.now(timezone.utc),
            source_type=attachment.get('source_type', 'file_upload'),
            preprocessing_summary=attachment.get('summary', None),
            content_ref=attachment.get('s3_uri', attachment.get('file_id', 'unknown'))
        )

        return uploaded_file

    def _create_evidence_from_attachment(
        self,
        case: Case,
        attachment: Dict[str, Any],
        turn_number: int
    ) -> Evidence:
        """
        Create evidence object from file attachment.

        Args:
            case: Current case
            attachment: Attachment metadata
            turn_number: Current turn number

        Returns:
            Evidence object
        """
        # Infer category based on investigation state
        category = self._infer_evidence_category(case)

        # Create evidence
        evidence = Evidence(
            evidence_id=f"ev_{uuid4().hex[:12]}",
            summary=f"Uploaded file: {attachment.get('filename', 'unknown')}",
            preprocessed_content="[Content to be preprocessed]",  # Placeholder
            content_ref=attachment.get('s3_uri', 'unknown'),
            content_size_bytes=attachment.get('size', 0),
            preprocessing_method="pending",
            category=category,
            source_type=EvidenceSourceType.LOG_FILE,  # Default
            form=EvidenceForm.DOCUMENT,
            advances_milestones=[],  # Calculated later
            collected_at=datetime.now(timezone.utc),
            collected_by=case.user_id,
            collected_at_turn=turn_number
        )

        return evidence

    def _infer_evidence_category(self, case: Case) -> EvidenceCategory:
        """
        Infer evidence category from investigation state.

        Rules:
        - If verification incomplete → SYMPTOM_EVIDENCE
        - If solution proposed → RESOLUTION_EVIDENCE
        - Otherwise → CAUSAL_EVIDENCE
        """
        if not case.progress.verification_complete:
            return EvidenceCategory.SYMPTOM_EVIDENCE

        if case.progress.solution_proposed:
            return EvidenceCategory.RESOLUTION_EVIDENCE

        return EvidenceCategory.CAUSAL_EVIDENCE

    def _create_turn_record(
        self,
        turn_number: int,
        milestones_completed: List[str],
        evidence_added: List[str],
        hypotheses_generated: List[str],
        hypotheses_validated: List[str],
        solutions_proposed: List[str],
        progress_made: bool,
        outcome: TurnOutcome,
        user_message: str,
        agent_response: str
    ) -> TurnProgress:
        """Create comprehensive turn progress record.

        Enhanced analytics from specification:
        - Detailed action tracking
        - Outcome classification
        - Progress indicators
        - Conversation summaries

        Args:
            turn_number: Turn sequence number
            milestones_completed: Milestones completed this turn
            evidence_added: Evidence IDs added
            hypotheses_generated: Hypothesis IDs generated
            hypotheses_validated: Hypothesis IDs validated
            solutions_proposed: Solution IDs proposed
            progress_made: Whether investigation progressed
            outcome: Turn outcome classification
            user_message: User's message
            agent_response: Agent's response

        Returns:
            TurnProgress record with comprehensive analytics
        """
        # Enhanced action extraction
        actions = self._extract_actions(agent_response)

        # Add milestone-based actions
        if milestones_completed:
            actions.extend([f"completed_{m}" for m in milestones_completed[:3]])

        # Add evidence actions
        if evidence_added:
            actions.append(f"added_{len(evidence_added)}_evidence")

        # Add hypothesis actions
        if hypotheses_generated:
            actions.append(f"generated_{len(hypotheses_generated)}_hypotheses")
        if hypotheses_validated:
            actions.append(f"validated_{len(hypotheses_validated)}_hypotheses")

        # Add solution actions
        if solutions_proposed:
            actions.append(f"proposed_{len(solutions_proposed)}_solutions")

        return TurnProgress(
            turn_number=turn_number,
            timestamp=datetime.now(timezone.utc),
            milestones_completed=milestones_completed,
            evidence_added=evidence_added,
            hypotheses_generated=hypotheses_generated,
            hypotheses_validated=hypotheses_validated,
            solutions_proposed=solutions_proposed,
            progress_made=progress_made,
            actions_taken=actions[:10],  # Limit to 10 most important
            outcome=outcome,
            user_message_summary=self._summarize_text(user_message, 200),
            agent_response_summary=self._summarize_text(agent_response, 500)
        )

    def _extract_actions(self, agent_response: str) -> List[str]:
        """Extract action keywords from agent response."""
        action_keywords = ['verified', 'identified', 'proposed', 'tested', 'confirmed', 'analyzed']
        actions = []

        response_lower = agent_response.lower()
        for keyword in action_keywords:
            if keyword in response_lower:
                actions.append(keyword)

        return actions[:5]  # Limit to 5

    def _summarize_text(self, text: str, max_length: int = 200) -> str:
        """Summarize long text for storage."""
        if len(text) <= max_length:
            return text
        return text[:max_length - 3] + "..."

    # =========================================================================
    # Structured Output Processors
    # =========================================================================

    def _process_milestone_updates(
        self,
        case: Case,
        arguments: Dict[str, Any]
    ) -> List[str]:
        """Process milestone update tool call.

        Updates case progress based on LLM's structured milestone completions.
        Implements all 8 milestone criteria from specification.

        Args:
            case: Current case
            arguments: Parsed tool call arguments

        Returns:
            List of milestone names that were completed
        """
        milestones_completed = []
        milestone_updates = arguments.get("milestones", [])

        for update in milestone_updates:
            milestone_name = update.get("milestone")
            completed = update.get("completed", False)
            confidence = update.get("confidence", 0.0)
            evidence = update.get("evidence", "")
            details = update.get("details", {})

            if not completed:
                continue

            # Update specific milestones based on name
            if milestone_name == "symptom_verified":
                if not case.progress.symptom_verified:
                    case.progress.symptom_verified = True
                    case.problem_verification.symptom_verified = True
                    case.problem_verification.symptom_statement = details.get("symptom_statement", case.description)
                    case.problem_verification.verification_method = details.get("verification_method", "user_report")
                    milestones_completed.append(milestone_name)

            elif milestone_name == "scope_assessed":
                if not case.progress.scope_assessed:
                    case.progress.scope_assessed = True
                    case.problem_verification.scope_statement = details.get("scope_statement", evidence)
                    milestones_completed.append(milestone_name)

            elif milestone_name == "timeline_established":
                if not case.progress.timeline_established:
                    case.progress.timeline_established = True
                    if "first_occurrence" in details:
                        case.problem_verification.timeline_first_occurrence = details["first_occurrence"]
                    if "last_occurrence" in details:
                        case.problem_verification.timeline_last_occurrence = details["last_occurrence"]
                    milestones_completed.append(milestone_name)

            elif milestone_name == "changes_identified":
                if not case.progress.changes_identified:
                    case.progress.changes_identified = True
                    # Store changes in evidence or metadata
                    milestones_completed.append(milestone_name)

            elif milestone_name == "root_cause_identified":
                if not case.progress.root_cause_identified:
                    case.progress.root_cause_identified = True
                    case.progress.root_cause_confidence = confidence
                    case.progress.root_cause_method = details.get("method", "structured_analysis")
                    case.problem_verification.root_cause_statement = details.get("root_cause_statement", evidence)
                    milestones_completed.append(milestone_name)

            elif milestone_name == "solution_proposed":
                if not case.progress.solution_proposed:
                    case.progress.solution_proposed = True
                    # Create solution object if details provided
                    if "solution_description" in details:
                        solution = Solution(
                            solution_id=f"sol_{uuid4().hex[:12]}",
                            title=details.get("solution_title", "Proposed Solution"),
                            description=details["solution_description"],
                            solution_type=SolutionType(details.get("solution_type", "MITIGATION")),
                            implementation_steps=details.get("steps", []),
                            estimated_effort=details.get("estimated_effort", "unknown"),
                            risk_level=details.get("risk_level", "medium"),
                            confidence_level=ConfidenceLevel(int(confidence * 100) // 20),  # Map 0-1 to enum
                            created_at=datetime.now(timezone.utc)
                        )
                        case.solutions.append(solution)
                    milestones_completed.append(milestone_name)

            elif milestone_name == "solution_applied":
                if not case.progress.solution_applied:
                    case.progress.solution_applied = True
                    milestones_completed.append(milestone_name)

            elif milestone_name == "solution_verified":
                if not case.progress.solution_verified:
                    case.progress.solution_verified = True
                    milestones_completed.append(milestone_name)

        # Update completed_milestones list
        for milestone in milestones_completed:
            if milestone not in case.progress.completed_milestones:
                case.progress.completed_milestones.append(milestone)

        # Check if verification complete (first 4 milestones)
        if (case.progress.symptom_verified and
            case.progress.scope_assessed and
            case.progress.timeline_established and
            case.progress.changes_identified):
            case.progress.verification_complete = True
            case.problem_verification.verification_complete = True

            # Invoke path selection when verification completes
            if (case.problem_verification.temporal_state and
                case.problem_verification.urgency_level and
                not case.path_selection):
                path_selection = determine_investigation_path(case.problem_verification)
                case.path_selection = path_selection

                logger.info(
                    f"Path selection after verification: {path_selection.path.value} "
                    f"(auto={path_selection.auto_selected}, "
                    f"rationale={path_selection.rationale})"
                )

        return milestones_completed

    def _process_evidence_analysis(
        self,
        case: Case,
        arguments: Dict[str, Any]
    ) -> Optional[str]:
        """Process evidence analysis tool call.

        Enhanced evidence categorization with system inference.

        Args:
            case: Current case
            arguments: Parsed tool call arguments

        Returns:
            Evidence ID if evidence was created/updated
        """
        evidence_id = arguments.get("evidence_id")
        category = EvidenceCategory(arguments.get("category"))
        confidence = arguments.get("confidence", 0.0)
        key_findings = arguments.get("key_findings", [])
        advances_milestones = arguments.get("advances_milestones", [])
        supports_hypotheses = arguments.get("supports_hypotheses", [])

        # Find existing evidence or create new
        existing_evidence = None
        for ev in case.evidence:
            if ev.evidence_id == evidence_id:
                existing_evidence = ev
                break

        if existing_evidence:
            # Update existing evidence with enhanced categorization
            existing_evidence.category = category
            existing_evidence.advances_milestones = advances_milestones
            # Update hypothesis links
            for hyp_id in supports_hypotheses:
                if hyp_id not in [link.hypothesis_id for link in existing_evidence.hypothesis_links]:
                    existing_evidence.hypothesis_links.append(
                        HypothesisEvidenceLink(
                            hypothesis_id=hyp_id,
                            stance=EvidenceStance.SUPPORTING,
                            relevance=confidence
                        )
                    )
            return evidence_id

        return None

    def _process_hypothesis_generation(
        self,
        case: Case,
        arguments: Dict[str, Any]
    ) -> Optional[str]:
        """Process hypothesis generation tool call.

        Creates new hypothesis with systematic exploration structure.

        Args:
            case: Current case
            arguments: Parsed tool call arguments

        Returns:
            Hypothesis ID if created
        """
        statement = arguments.get("statement")
        category = HypothesisCategory(arguments.get("category", "UNKNOWN"))
        likelihood = arguments.get("likelihood", 0.5)
        reasoning = arguments.get("reasoning", "")
        required_evidence = arguments.get("required_evidence", [])
        testable_predictions = arguments.get("testable_predictions", [])

        if not statement:
            return None

        # Create hypothesis
        hypothesis_id = f"hyp_{uuid4().hex[:12]}"
        hypothesis = Hypothesis(
            hypothesis_id=hypothesis_id,
            statement=statement,
            category=category,
            likelihood=likelihood,
            status=HypothesisStatus.ACTIVE,
            generation_mode=HypothesisGenerationMode.SYSTEMATIC,
            generated_reasoning=reasoning,
            testable_predictions=testable_predictions,
            evidence_links=[],
            created_at=datetime.now(timezone.utc),
            created_at_turn=case.current_turn + 1
        )

        case.hypotheses[hypothesis_id] = hypothesis
        return hypothesis_id

    def _process_hypothesis_evaluation(
        self,
        case: Case,
        arguments: Dict[str, Any]
    ) -> Optional[str]:
        """Process hypothesis evaluation tool call.

        Updates hypothesis status based on evidence validation.

        Args:
            case: Current case
            arguments: Parsed tool call arguments

        Returns:
            Hypothesis ID if evaluated
        """
        hypothesis_id = arguments.get("hypothesis_id")
        status = HypothesisStatus(arguments.get("status"))
        likelihood = arguments.get("likelihood", 0.5)
        supporting_evidence = arguments.get("supporting_evidence", [])
        contradicting_evidence = arguments.get("contradicting_evidence", [])
        validation_reasoning = arguments.get("validation_reasoning", "")
        recommended_action = arguments.get("recommended_action")

        if hypothesis_id not in case.hypotheses:
            logger.warning(f"Hypothesis {hypothesis_id} not found for evaluation")
            return None

        hypothesis = case.hypotheses[hypothesis_id]
        hypothesis.status = status
        hypothesis.likelihood = likelihood

        # Update evidence links
        for ev_id in supporting_evidence:
            if ev_id not in [link.evidence_id for link in hypothesis.evidence_links]:
                hypothesis.evidence_links.append(
                    HypothesisEvidenceLink(
                        hypothesis_id=hypothesis_id,
                        evidence_id=ev_id,
                        stance=EvidenceStance.SUPPORTING,
                        relevance=0.8
                    )
                )

        for ev_id in contradicting_evidence:
            if ev_id not in [link.evidence_id for link in hypothesis.evidence_links]:
                hypothesis.evidence_links.append(
                    HypothesisEvidenceLink(
                        hypothesis_id=hypothesis_id,
                        evidence_id=ev_id,
                        stance=EvidenceStance.CONTRADICTING,
                        relevance=0.8
                    )
                )

        # Check for anchoring bias before accepting as root cause
        anchoring_detected = self._detect_anchoring_bias(case, hypothesis)
        if anchoring_detected:
            logger.warning(
                f"Anchoring bias detected for hypothesis {hypothesis_id}. "
                f"Flagging for additional validation."
            )
            # Don't immediately accept - require additional evidence
            if not contradicting_evidence:
                hypothesis.status = HypothesisStatus.NEEDS_MORE_DATA
                return hypothesis_id

        # If validated as root cause, update progress
        if status == HypothesisStatus.VALIDATED and recommended_action == "ACCEPT_AS_ROOT_CAUSE":
            if not case.progress.root_cause_identified:
                case.progress.root_cause_identified = True
                case.progress.root_cause_confidence = likelihood
                case.progress.root_cause_method = "hypothesis_validation"
                case.problem_verification.root_cause_statement = hypothesis.statement

        return hypothesis_id

    def _detect_anchoring_bias(self, case: Case, hypothesis: Hypothesis) -> bool:
        """Detect anchoring bias in hypothesis evaluation.

        Anchoring bias indicators from specification:
        1. First hypothesis created gets highest likelihood without evidence
        2. All subsequent hypotheses have lower likelihood
        3. Evidence interpretation biased toward first hypothesis
        4. Contradicting evidence dismissed or underweighted

        Args:
            case: Current case
            hypothesis: Hypothesis to check

        Returns:
            True if anchoring bias detected
        """
        if not case.hypotheses:
            return False

        # Get all hypotheses sorted by creation time
        sorted_hypotheses = sorted(
            case.hypotheses.values(),
            key=lambda h: h.created_at
        )

        # Check if this is the first hypothesis
        first_hypothesis = sorted_hypotheses[0]
        if hypothesis.hypothesis_id != first_hypothesis.hypothesis_id:
            return False

        # Indicator 1: First hypothesis has high likelihood without much evidence
        if hypothesis.likelihood > 0.75 and len(hypothesis.evidence_links) < 2:
            logger.info(
                f"Anchoring indicator: First hypothesis {hypothesis.hypothesis_id} "
                f"has high likelihood ({hypothesis.likelihood:.2f}) with "
                f"insufficient evidence ({len(hypothesis.evidence_links)} links)"
            )
            return True

        # Indicator 2: All other hypotheses have significantly lower likelihood
        if len(sorted_hypotheses) > 1:
            other_hypotheses = sorted_hypotheses[1:]
            active_others = [h for h in other_hypotheses if h.status == HypothesisStatus.ACTIVE]

            if active_others:
                max_other_likelihood = max(h.likelihood for h in active_others)
                likelihood_gap = hypothesis.likelihood - max_other_likelihood

                if likelihood_gap > 0.3:  # 30% gap threshold
                    logger.info(
                        f"Anchoring indicator: First hypothesis has {likelihood_gap:.2f} "
                        f"likelihood advantage over alternatives without clear evidence"
                    )
                    return True

        # Indicator 3: Check if contradicting evidence exists but is underweighted
        contradicting = [
            link for link in hypothesis.evidence_links
            if link.stance == EvidenceStance.CONTRADICTING
        ]
        supporting = [
            link for link in hypothesis.evidence_links
            if link.stance == EvidenceStance.SUPPORTING
        ]

        if contradicting and len(supporting) > 0:
            avg_contradicting_relevance = sum(link.relevance for link in contradicting) / len(contradicting)
            avg_supporting_relevance = sum(link.relevance for link in supporting) / len(supporting)

            # If contradicting evidence is systematically weighted lower
            if avg_contradicting_relevance < avg_supporting_relevance - 0.2:
                logger.info(
                    f"Anchoring indicator: Contradicting evidence underweighted "
                    f"({avg_contradicting_relevance:.2f} vs {avg_supporting_relevance:.2f})"
                )
                return True

        return False


# =============================================================================
# Exceptions
# =============================================================================


class MilestoneEngineError(Exception):
    """Base exception for milestone engine errors."""
    pass
