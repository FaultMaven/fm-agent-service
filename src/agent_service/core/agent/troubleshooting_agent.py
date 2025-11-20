"""LangGraph-based Troubleshooting Agent

This module implements the stateful agent using LangGraph for AI-powered troubleshooting.
It orchestrates the MilestoneEngine, prompts, and LLM providers to deliver intelligent
diagnostic conversations.

Architecture:
- LangGraph StateGraph for conversation flow
- MilestoneEngine for investigation tracking
- Multi-provider LLM routing via fm-core-lib
- Adaptive prompt generation based on investigation progress
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

from langgraph.graph import StateGraph, END
from fm_core_lib.models import Case, CaseStatus, InvestigationProgress
from fm_core_lib.infrastructure.llm import LLMRouter

from agent_service.core.investigation import (
    MilestoneEngine,
    HypothesisManager,
    MemoryManager,
    WorkingConclusionGenerator,
)
from agent_service.core.prompts.prompt_manager import PromptManager


class AgentState(Dict[str, Any]):
    """
    Agent conversation state.

    Fields:
    - case: Current case object
    - messages: Conversation history
    - investigation_progress: Milestone tracking
    - working_conclusion: Current diagnostic state
    - next_action: Agent's next step
    """
    pass


class TroubleshootingAgent:
    """
    AI Troubleshooting Agent using MilestoneEngine.

    This agent follows the milestone-based investigation framework (v2.0)
    where milestones complete opportunistically based on data availability.
    """

    def __init__(
        self,
        llm_router: LLMRouter,
        case_repository,
        knowledge_service_url: str,
    ):
        self.llm_router = llm_router
        self.case_repository = case_repository
        self.knowledge_service_url = knowledge_service_url

        # Investigation components
        self.milestone_engine = MilestoneEngine(llm_router)
        self.hypothesis_manager = HypothesisManager()
        self.memory_manager = MemoryManager()
        self.conclusion_generator = WorkingConclusionGenerator(llm_router)

        # Prompt management
        self.prompt_manager = PromptManager()

        # Build LangGraph workflow
        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        """
        Build the LangGraph state machine.

        Flow:
        1. assess_case → Determine case status and strategy
        2. generate_response → Create agent response based on milestones
        3. update_investigation → Update milestone progress
        4. END
        """
        workflow = StateGraph(AgentState)

        # Define nodes
        workflow.add_node("assess_case", self._assess_case)
        workflow.add_node("generate_response", self._generate_response)
        workflow.add_node("update_investigation", self._update_investigation)

        # Define edges
        workflow.set_entry_point("assess_case")
        workflow.add_edge("assess_case", "generate_response")
        workflow.add_edge("generate_response", "update_investigation")
        workflow.add_edge("update_investigation", END)

        return workflow.compile()

    async def _assess_case(self, state: AgentState) -> AgentState:
        """
        Assess current case state and determine investigation strategy.

        Updates:
        - Case status (CONSULTING → INVESTIGATING if needed)
        - Investigation strategy
        - Milestone progress
        """
        case: Case = state["case"]

        # Evaluate milestones using MilestoneEngine
        milestone_status = await self.milestone_engine.evaluate_milestones(
            case=case,
            messages=state["messages"],
        )

        state["milestone_status"] = milestone_status
        return state

    async def _generate_response(self, state: AgentState) -> AgentState:
        """
        Generate agent response based on current investigation state.

        Uses adaptive prompts:
        - CONSULTING mode: Reactive listening
        - INVESTIGATING mode: Proactive problem-solving with milestone guidance
        """
        case: Case = state["case"]
        milestone_status = state["milestone_status"]

        # Generate working conclusion
        conclusion = await self.conclusion_generator.generate(
            case=case,
            milestone_status=milestone_status,
        )

        # Select appropriate prompt template
        if case.status == CaseStatus.CONSULTING:
            prompt = self.prompt_manager.get_consulting_prompt(case, conclusion)
        else:
            prompt = self.prompt_manager.get_investigating_prompt(
                case=case,
                milestone_status=milestone_status,
                conclusion=conclusion,
            )

        # Generate response via LLM
        response = await self.llm_router.generate(
            messages=[{"role": "system", "content": prompt}] + state["messages"],
            temperature=0.7,
        )

        state["agent_response"] = response
        state["working_conclusion"] = conclusion
        return state

    async def _update_investigation(self, state: AgentState) -> AgentState:
        """
        Update investigation progress based on agent response.

        Updates:
        - Milestone completions
        - Hypotheses
        - Memory/context
        """
        case: Case = state["case"]

        # Update milestones
        updated_progress = await self.milestone_engine.update_progress(
            case=case,
            agent_response=state["agent_response"],
        )

        case.investigation_progress = updated_progress

        # Persist case
        await self.case_repository.update(case)

        state["case"] = case
        return state

    async def process_message(
        self,
        case_id: str,
        user_message: str,
    ) -> Dict[str, Any]:
        """
        Process a user message and return agent response.

        Args:
            case_id: Case identifier
            user_message: User's message

        Returns:
            {
                "agent_response": str,
                "working_conclusion": Dict,
                "milestone_status": Dict,
            }
        """
        # Load case
        case = await self.case_repository.get(case_id)

        # Build conversation history
        messages = await self._build_message_history(case, user_message)

        # Execute graph
        initial_state: AgentState = {
            "case": case,
            "messages": messages,
        }

        final_state = await self.graph.ainvoke(initial_state)

        return {
            "agent_response": final_state["agent_response"],
            "working_conclusion": final_state["working_conclusion"],
            "milestone_status": final_state["milestone_status"],
        }

    async def _build_message_history(
        self,
        case: Case,
        new_message: str,
    ) -> List[Dict[str, str]]:
        """Build conversation history for LLM context"""
        # Fetch previous messages from case
        messages = []

        # Add new user message
        messages.append({
            "role": "user",
            "content": new_message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        return messages
