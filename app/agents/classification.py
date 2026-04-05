"""Classification agent – assigns product category and issue type.

Uses tools to autonomously retrieve similar complaints and company taxonomy.
"""

from __future__ import annotations

import logging
from pathlib import Path

from app.agents.llm_factory import create_llm
from app.agents.tool_loop import run_agent_with_tools
from app.agents.tools import lookup_company_taxonomy, search_similar_complaints
from app.schemas.classification import ClassificationResult

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "classification.md"


def _load_prompt() -> str:
    return _PROMPT_PATH.read_text()


def run_classification(
    narrative: str,
    product: str | None = None,
    sub_product: str | None = None,
    company: str | None = None,
    state: str | None = None,
    company_id: str = "mock_bank",
    instructions: str = "",
    model_name: str | None = None,
    temperature: float = 0.0,
) -> ClassificationResult:
    """Classify the complaint and return a structured result.

    The agent has access to tools for retrieving similar complaints and
    company taxonomy candidates. It decides autonomously whether and how
    to use them.
    """
    logger.info("Classification agent running")

    system_prompt = _load_prompt()

    user_message = (
        f"Narrative: {narrative}\n"
        f"Product (if provided): {product or 'N/A'}\n"
        f"Sub-product (if provided): {sub_product or 'N/A'}\n"
        f"Company: {company or 'N/A'}\n"
        f"State: {state or 'N/A'}\n"
        f"Company ID: {company_id}\n"
    )
    if instructions:
        user_message += f"\nSupervisor instructions: {instructions}\n"

    user_message += (
        "\nYou have tools available to search for similar complaints and look up "
        "the company's product/issue taxonomy. Use them to ground your classification. "
        "When done, respond with the classification JSON."
    )

    llm = create_llm(model_name=model_name, temperature=temperature)
    tools = [search_similar_complaints, lookup_company_taxonomy]

    result_data = run_agent_with_tools(llm, system_prompt, user_message, tools)
    result = ClassificationResult(**result_data)

    logger.info(
        "Classification complete – category=%s, confidence=%.2f",
        result.product_category,
        result.confidence,
    )
    return result
