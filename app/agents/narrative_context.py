"""Build narrative (or fallback) text for downstream LLM agents."""

from __future__ import annotations

from app.schemas.case import CaseRead

RICH_NARRATIVE_MIN = 10

NO_NARRATIVE_BOILERPLATE = (
    "[No consumer narrative was submitted (or text is too short for free-text analysis). "
    "Rely on the operational classification, CFPB portal selections, and tools.]"
)


def narrative_for_agent_prompt(case: CaseRead) -> str:
    """Primary narrative for risk/resolution/compliance prompts."""
    nar = (case.consumer_narrative or "").strip()
    if len(nar) >= RICH_NARRATIVE_MIN:
        return nar
    lines = [NO_NARRATIVE_BOILERPLATE]
    if case.cfpb_product:
        lines.append(f"CFPB portal product: {case.cfpb_product}")
    if case.cfpb_sub_product:
        lines.append(f"CFPB portal sub-product: {case.cfpb_sub_product}")
    if case.cfpb_issue:
        lines.append(f"CFPB portal issue: {case.cfpb_issue}")
    if case.cfpb_sub_issue:
        lines.append(f"CFPB portal sub-issue: {case.cfpb_sub_issue}")
    if case.product and not case.cfpb_product:
        lines.append(f"Reported product (legacy field): {case.product}")
    if case.sub_product:
        lines.append(f"Reported sub-product: {case.sub_product}")
    return "\n".join(lines)
