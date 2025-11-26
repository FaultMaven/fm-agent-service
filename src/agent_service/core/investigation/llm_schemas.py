"""LLM Structured Output Schemas for Milestone-Based Investigation

This module defines the structured output schemas used by the LLM to provide
machine-parseable responses for milestone detection, evidence analysis, and
hypothesis evaluation.

Design Reference:
- docs/architecture/milestone-based-investigation-framework.md (Section: Structured Output)
"""

from typing import List, Optional, Dict, Any
from enum import Enum


# =============================================================================
# Milestone Detection Schema
# =============================================================================

class MilestoneUpdate(Dict[str, Any]):
    """Schema for milestone completion updates from LLM.

    Example:
    {
        "milestone": "symptom_verified",
        "completed": true,
        "confidence": 0.95,
        "evidence": "User reported 500 errors in logs, confirmed by log analysis",
        "details": {
            "symptom_statement": "Application returns 500 errors on POST /api/users",
            "verification_method": "log_analysis"
        }
    }
    """
    pass


class MilestoneDetectionResponse(Dict[str, Any]):
    """Complete milestone detection response from LLM.

    Example:
    {
        "milestones": [
            {
                "milestone": "symptom_verified",
                "completed": true,
                "confidence": 0.95,
                "evidence": "...",
                "details": {...}
            },
            {
                "milestone": "timeline_established",
                "completed": true,
                "confidence": 0.85,
                "evidence": "...",
                "details": {...}
            }
        ],
        "reasoning": "Based on the logs provided, I can confirm the symptom and establish timeline..."
    }
    """
    pass


# =============================================================================
# Evidence Analysis Schema
# =============================================================================

class EvidenceAnalysis(Dict[str, Any]):
    """Schema for evidence categorization and analysis.

    Example:
    {
        "evidence_id": "ev_abc123",
        "category": "CAUSAL_EVIDENCE",
        "form": "LOG_SNIPPET",
        "confidence": 0.85,
        "key_findings": [
            "Database connection pool exhausted",
            "Max connections: 100, Active: 100"
        ],
        "advances_milestones": ["root_cause_identified"],
        "supports_hypotheses": ["hyp_db_pool"],
        "temporal_markers": {
            "first_occurrence": "2024-01-15T10:30:00Z",
            "last_occurrence": "2024-01-15T11:45:00Z"
        }
    }
    """
    pass


# =============================================================================
# Hypothesis Evaluation Schema
# =============================================================================

class HypothesisEvaluation(Dict[str, Any]):
    """Schema for hypothesis evaluation from LLM.

    Example:
    {
        "hypothesis_id": "hyp_abc123",
        "status": "VALIDATED",
        "likelihood": 0.92,
        "supporting_evidence": ["ev_001", "ev_002"],
        "contradicting_evidence": [],
        "validation_reasoning": "Database connection pool exhaustion explains all symptoms",
        "recommended_action": "ACCEPT_AS_ROOT_CAUSE",
        "alternative_explanations": []
    }
    """
    pass


class HypothesisGeneration(Dict[str, Any]):
    """Schema for generating new hypotheses.

    Example:
    {
        "statement": "Database connection pool is exhausted",
        "category": "RESOURCE_EXHAUSTION",
        "likelihood": 0.75,
        "reasoning": "Logs show max connections reached during incident",
        "required_evidence": [
            "Database connection metrics",
            "Application connection pool configuration"
        ],
        "testable_predictions": [
            "Connection pool metrics will show 100% utilization",
            "Application logs will show connection timeout errors"
        ]
    }
    """
    pass


# =============================================================================
# Path Selection Schema
# =============================================================================

class PathSelectionRecommendation(Dict[str, Any]):
    """Schema for investigation path recommendation.

    Example:
    {
        "recommended_path": "MITIGATION_FIRST",
        "confidence": 0.90,
        "reasoning": "Production outage with high severity requires immediate mitigation",
        "temporal_state": "ONGOING",
        "urgency_level": "CRITICAL",
        "alternate_path": "ROOT_CAUSE",
        "conditions_for_alternate": "After service is restored"
    }
    """
    pass


# =============================================================================
# Function Calling Schemas (OpenAI/Anthropic Format)
# =============================================================================

MILESTONE_UPDATE_TOOL = {
    "type": "function",
    "function": {
        "name": "update_milestones",
        "description": "Update investigation milestone completion status based on evidence and analysis",
        "parameters": {
            "type": "object",
            "properties": {
                "milestones": {
                    "type": "array",
                    "description": "List of milestone updates",
                    "items": {
                        "type": "object",
                        "properties": {
                            "milestone": {
                                "type": "string",
                                "enum": [
                                    "symptom_verified",
                                    "scope_assessed",
                                    "timeline_established",
                                    "changes_identified",
                                    "root_cause_identified",
                                    "solution_proposed",
                                    "solution_applied",
                                    "solution_verified"
                                ],
                                "description": "Milestone identifier"
                            },
                            "completed": {
                                "type": "boolean",
                                "description": "Whether milestone is now complete"
                            },
                            "confidence": {
                                "type": "number",
                                "minimum": 0.0,
                                "maximum": 1.0,
                                "description": "Confidence in milestone completion (0.0-1.0)"
                            },
                            "evidence": {
                                "type": "string",
                                "description": "Evidence supporting milestone completion"
                            },
                            "details": {
                                "type": "object",
                                "description": "Milestone-specific details",
                                "additionalProperties": True
                            }
                        },
                        "required": ["milestone", "completed", "confidence", "evidence"]
                    }
                },
                "reasoning": {
                    "type": "string",
                    "description": "Overall reasoning for milestone updates"
                }
            },
            "required": ["milestones", "reasoning"]
        }
    }
}

EVIDENCE_ANALYSIS_TOOL = {
    "type": "function",
    "function": {
        "name": "analyze_evidence",
        "description": "Analyze and categorize evidence for investigation",
        "parameters": {
            "type": "object",
            "properties": {
                "evidence_id": {
                    "type": "string",
                    "description": "Unique evidence identifier"
                },
                "category": {
                    "type": "string",
                    "enum": ["SYMPTOM_EVIDENCE", "CAUSAL_EVIDENCE", "RESOLUTION_EVIDENCE"],
                    "description": "Evidence category"
                },
                "form": {
                    "type": "string",
                    "enum": ["LOG_SNIPPET", "METRIC_SNAPSHOT", "TRACE", "SCREENSHOT", "DOCUMENT"],
                    "description": "Form of evidence"
                },
                "confidence": {
                    "type": "number",
                    "minimum": 0.0,
                    "maximum": 1.0,
                    "description": "Confidence in categorization"
                },
                "key_findings": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Key findings from evidence"
                },
                "advances_milestones": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Milestones this evidence helps complete"
                },
                "supports_hypotheses": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Hypotheses supported by this evidence"
                },
                "temporal_markers": {
                    "type": "object",
                    "properties": {
                        "first_occurrence": {"type": "string"},
                        "last_occurrence": {"type": "string"}
                    },
                    "description": "Temporal information from evidence"
                }
            },
            "required": ["evidence_id", "category", "confidence", "key_findings"]
        }
    }
}

HYPOTHESIS_EVALUATION_TOOL = {
    "type": "function",
    "function": {
        "name": "evaluate_hypothesis",
        "description": "Evaluate hypothesis against evidence and determine validity",
        "parameters": {
            "type": "object",
            "properties": {
                "hypothesis_id": {
                    "type": "string",
                    "description": "Hypothesis identifier"
                },
                "status": {
                    "type": "string",
                    "enum": ["VALIDATED", "INVALIDATED", "NEEDS_MORE_DATA", "ACTIVE"],
                    "description": "Updated hypothesis status"
                },
                "likelihood": {
                    "type": "number",
                    "minimum": 0.0,
                    "maximum": 1.0,
                    "description": "Likelihood this is the root cause"
                },
                "supporting_evidence": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Evidence IDs supporting hypothesis"
                },
                "contradicting_evidence": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Evidence IDs contradicting hypothesis"
                },
                "validation_reasoning": {
                    "type": "string",
                    "description": "Reasoning for evaluation"
                },
                "recommended_action": {
                    "type": "string",
                    "enum": [
                        "ACCEPT_AS_ROOT_CAUSE",
                        "REJECT",
                        "GATHER_MORE_EVIDENCE",
                        "TEST_PREDICTION",
                        "EXPLORE_ALTERNATIVE"
                    ],
                    "description": "Recommended next action"
                },
                "alternative_explanations": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Alternative explanations to consider"
                }
            },
            "required": ["hypothesis_id", "status", "likelihood", "validation_reasoning", "recommended_action"]
        }
    }
}

HYPOTHESIS_GENERATION_TOOL = {
    "type": "function",
    "function": {
        "name": "generate_hypothesis",
        "description": "Generate new hypothesis about root cause",
        "parameters": {
            "type": "object",
            "properties": {
                "statement": {
                    "type": "string",
                    "description": "Clear hypothesis statement"
                },
                "category": {
                    "type": "string",
                    "enum": [
                        "RESOURCE_EXHAUSTION",
                        "CONFIGURATION_ERROR",
                        "CODE_DEFECT",
                        "DEPENDENCY_FAILURE",
                        "INFRASTRUCTURE_ISSUE",
                        "DATA_CORRUPTION",
                        "EXTERNAL_FACTOR"
                    ],
                    "description": "Hypothesis category"
                },
                "likelihood": {
                    "type": "number",
                    "minimum": 0.0,
                    "maximum": 1.0,
                    "description": "Initial likelihood estimate"
                },
                "reasoning": {
                    "type": "string",
                    "description": "Reasoning behind hypothesis"
                },
                "required_evidence": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Evidence needed to validate"
                },
                "testable_predictions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Testable predictions if hypothesis is true"
                }
            },
            "required": ["statement", "category", "likelihood", "reasoning", "testable_predictions"]
        }
    }
}

PATH_SELECTION_TOOL = {
    "type": "function",
    "function": {
        "name": "recommend_investigation_path",
        "description": "Recommend investigation path (MITIGATION_FIRST vs ROOT_CAUSE) based on problem characteristics",
        "parameters": {
            "type": "object",
            "properties": {
                "recommended_path": {
                    "type": "string",
                    "enum": ["MITIGATION_FIRST", "ROOT_CAUSE"],
                    "description": "Recommended investigation path"
                },
                "confidence": {
                    "type": "number",
                    "minimum": 0.0,
                    "maximum": 1.0,
                    "description": "Confidence in recommendation"
                },
                "reasoning": {
                    "type": "string",
                    "description": "Reasoning for path selection"
                },
                "temporal_state": {
                    "type": "string",
                    "enum": ["ONGOING", "HISTORICAL", "INTERMITTENT"],
                    "description": "Temporal state of problem"
                },
                "urgency_level": {
                    "type": "string",
                    "enum": ["CRITICAL", "HIGH", "MEDIUM", "LOW"],
                    "description": "Problem urgency"
                },
                "alternate_path": {
                    "type": "string",
                    "enum": ["MITIGATION_FIRST", "ROOT_CAUSE"],
                    "description": "Alternate path to consider"
                },
                "conditions_for_alternate": {
                    "type": "string",
                    "description": "Conditions when alternate path should be used"
                }
            },
            "required": ["recommended_path", "confidence", "reasoning", "temporal_state", "urgency_level"]
        }
    }
}


# =============================================================================
# Tool Selection by Context
# =============================================================================

def get_tools_for_status(case_status: str) -> List[Dict[str, Any]]:
    """Get appropriate tool schemas based on case status.

    Args:
        case_status: Current case status (CONSULTING, INVESTIGATING, etc.)

    Returns:
        List of tool schemas appropriate for this status
    """
    if case_status == "CONSULTING":
        return [PATH_SELECTION_TOOL]

    elif case_status == "INVESTIGATING":
        return [
            MILESTONE_UPDATE_TOOL,
            EVIDENCE_ANALYSIS_TOOL,
            HYPOTHESIS_EVALUATION_TOOL,
            HYPOTHESIS_GENERATION_TOOL
        ]

    else:  # RESOLVED, CLOSED
        return []


def get_tools_for_milestone_stage(milestone_stage: str) -> List[Dict[str, Any]]:
    """Get tools appropriate for current milestone stage.

    Args:
        milestone_stage: Current investigation stage

    Returns:
        List of tool schemas appropriate for this stage
    """
    base_tools = [MILESTONE_UPDATE_TOOL, EVIDENCE_ANALYSIS_TOOL]

    if milestone_stage in ["PROBLEM_VERIFICATION", "INVESTIGATION"]:
        base_tools.append(HYPOTHESIS_GENERATION_TOOL)
        base_tools.append(HYPOTHESIS_EVALUATION_TOOL)

    return base_tools
