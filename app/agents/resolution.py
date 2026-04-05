"""Resolution agent – recommends a resolution based on precedent.

Uses tools to autonomously search similar resolutions and look up policies.
"""

from __future__ import annotations

import logging
from pathlib import Path

from app.agents.llm_factory import create_llm
from app.agents.tool_loop import run_agent_with_tools
from app.agents.tools import lookup_routing_rules, lookup_severity_rubric, search_similar_resolutions
from app.schemas.classification import ClassificationResult
from app.schemas.resolution import ResolutionRecommendation
from app.schemas.risk import RiskAssessment

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "resolution.md"


def _load_prompt() -> str:
    return _PROMPT_PATH.read_text()


def run_resolution(
    narrative: str,
    classification: ClassificationResult,
    risk: RiskAssessment,
    root_cause_hypothesis: object | None = None,
    company_id: str = "mock_bank",
    instructions: str = "",
    model_name: str | None = None,
    temperature: float = 0.0,
) -> ResolutionRecommendation:
    """Propose a resolution for the complaint.

    The agent has access to tools for searching similar resolutions and
    looking up severity/policy rubrics and routing rules.
    """
    logger.info("Resolution agent running")

    system_prompt = _load_prompt()

    user_message = (
        f"Narrative: {narrative}\n"
        f"Classification: {classification.model_dump_json()}\n"
        f"Risk Assessment: {risk.model_dump_json()}\n"
        f"Company ID: {company_id}\n"
    )
    if root_cause_hypothesis is not None:
        user_message += (
            f"Root-cause hypothesis (grounding context): {root_cause_hypothesis}\n"
        )
    if instructions:
        user_message += f"\nSupervisor instructions: {instructions}\n"

    user_message += (
        "\nYou have tools available to search for similar resolutions and look up "
        "severity rubrics, policies, and routing rules. Use them to ground your "
        "resolution recommendation. When done, respond with the resolution JSON."
    )

    llm = create_llm(model_name=model_name, temperature=temperature)
    tools = [search_similar_resolutions, lookup_severity_rubric, lookup_routing_rules]

    result_data = run_agent_with_tools(llm, system_prompt, user_message, tools)
    result = ResolutionRecommendation(**result_data)

    logger.info(
        "Resolution complete – action=%s, confidence=%.2f",
        result.recommended_action,
        result.confidence,
    )
    return result
