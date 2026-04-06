"""Risk-assessment agent – evaluates complaint risk level.

Uses tools to autonomously retrieve similar complaints and severity rubric.
"""

from __future__ import annotations

import logging
from pathlib import Path

from app.agents.llm_factory import create_llm
from app.agents.tool_loop import run_agent_with_tools
from app.agents.tools import lookup_severity_rubric, search_similar_complaints
from app.schemas.classification import ClassificationResult
from app.schemas.risk import RiskAssessment

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "risk.md"


def _load_prompt() -> str:
    return _PROMPT_PATH.read_text()


def run_risk_assessment(
    narrative: str,
    classification: ClassificationResult,
    company_id: str = "mock_bank",
    instructions: str = "",
    model_name: str | None = None,
    temperature: float = 0.0,
) -> RiskAssessment:
    """Assess the risk posed by the complaint.

    The agent has access to tools for retrieving similar complaints and
    severity/policy rubrics. It decides autonomously whether to use them.
    """
    logger.info("Risk agent running")

    system_prompt = _load_prompt()

    user_message = (
        f"Narrative: {narrative}\n"
        f"Classification: {classification.model_dump_json()}\n"
        f"Company ID: {company_id}\n"
    )
    if instructions:
        user_message += f"\nSupervisor instructions: {instructions}\n"

    user_message += (
        "\nYou have tools available to search for similar complaints and look up "
        "severity rubrics and policy snippets. Use them to ground your risk assessment. "
        "When done, respond with the risk assessment JSON."
    )

    llm = create_llm(model_name=model_name, temperature=temperature)
    tools = [search_similar_complaints, lookup_severity_rubric]

    result_data = run_agent_with_tools(llm, system_prompt, user_message, tools)
    result = RiskAssessment(**result_data)

    logger.info(
        "Risk assessment complete – level=%s, score=%.1f",
        result.risk_level,
        result.risk_score,
    )
    return result
