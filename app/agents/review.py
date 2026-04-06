"""Review agent – performs a final quality-assurance pass on the case.

Enhanced with structured feedback: when the decision is "revise", the
review agent produces a ``review_feedback`` dict that the supervisor uses
to route feedback to the appropriate upstream agent.
"""

from __future__ import annotations

import logging

from langchain_core.prompts import ChatPromptTemplate

from app.agents.llm_factory import create_llm
from app.agents.llm_json import parse_llm_json

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a senior quality-assurance reviewer in a consumer-complaint pipeline.

You receive the **full case dossier** (narrative, classification, risk,
resolution, and compliance flags). Your task is to:

1. Verify internal consistency – does the resolution match the risk level
   and classification?
2. Check for gaps – is any required information missing?
3. Assess fairness – is the resolution reasonable for the consumer?
4. Provide a final recommendation: **approve**, **revise**, or **escalate**.

Return a JSON object:
{{
  "decision": "approve" | "revise" | "escalate",
  "notes": "<brief explanation>",
  "suggested_changes": ["<change_1>", ...] or [],
  "review_feedback": {{
    "target_agent": "<which agent should redo its work: classify, risk, root_cause, or resolve>",
    "issues": ["<issue_1>", ...],
    "suggested_changes": ["<change_1>", ...]
  }} or null
}}

The ``review_feedback`` field is **required** when decision is "revise" — it
tells the supervisor which upstream agent needs to redo its work and why.
Set it to null for "approve" or "escalate" decisions.
"""


def run_review(
    narrative: str,
    classification_json: str,
    risk_json: str,
    resolution_json: str,
    compliance_json: str,
    instructions: str = "",
    model_name: str | None = None,
    temperature: float = 0.0,
) -> dict:
    """Run the QA review and return a decision with optional feedback."""
    logger.info("Review agent running")

    user_message = (
        f"Narrative: {narrative}\n"
        f"Classification: {classification_json}\n"
        f"Risk Assessment: {risk_json}\n"
        f"Resolution: {resolution_json}\n"
        f"Compliance: {compliance_json}\n"
    )
    if instructions:
        user_message += f"\nSupervisor instructions: {instructions}\n"

    prompt = ChatPromptTemplate.from_messages(
        [("system", _SYSTEM_PROMPT), ("human", "{input}")]
    )

    llm = create_llm(model_name=model_name, temperature=temperature)
    chain = prompt | llm

    response = chain.invoke({"input": user_message})
    result = parse_llm_json(getattr(response, "content", None))

    logger.info("Review complete – decision=%s", result.get("decision"))
    return result
