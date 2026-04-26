from __future__ import annotations

from app.knowledge_base.bootstrap import (
    build_phase1_seed_obligations,
    build_phase2_seed_failure_modes,
)
from app.knowledge_base.ingestion.common import IngestionResult, save_manifest
from app.knowledge_base.repository import KnowledgeBaseRepository


def seed_bootstrap_extractions(*, repo: KnowledgeBaseRepository) -> IngestionResult:
    obligation_count = 0
    failure_mode_count = 0
    artifacts: list[str] = []

    for obligation in build_phase1_seed_obligations():
        obligation_id = repo.upsert_obligation(
            payload={
                "obligation_key": obligation.obligation_id,
                "title": obligation.label,
                "summary": obligation.summary,
                "regulation": obligation.regulation,
                "regulation_section": obligation.regulation_section,
                "trigger_conditions": obligation.trigger_conditions,
                "consumer_rights": obligation.consumer_rights,
                "effective_from": obligation.effective_period.valid_from,
                "effective_to": obligation.effective_period.valid_to,
                "source_tier": min(citation.tier for citation in obligation.citations),
                "validation_status": obligation.validation_status,
                "metadata": {"seed": True},
            },
            evidence_requirements=[
                {
                    "evidence_key": f"{obligation.obligation_id}_{index}",
                    "label": label,
                    "description": label,
                    "evidence_type": "record",
                }
                for index, label in enumerate(obligation.evidence_requirements, start=1)
            ],
            deadlines=[
                {
                    "deadline_key": f"{obligation.obligation_id}_{index}",
                    "label": label,
                    "duration_text": label,
                    "deadline_type": "seed",
                    "rule_text": label,
                }
                for index, label in enumerate(obligation.deadlines, start=1)
            ],
            citations=[],
        )
        if obligation_id:
            obligation_count += 1

    for failure_mode in build_phase2_seed_failure_modes():
        failure_mode_id = repo.upsert_failure_mode(
            {
                "failure_mode_key": failure_mode.failure_mode_id,
                "name": failure_mode.label,
                "description": failure_mode.label,
                "consumer_harm_types": failure_mode.consumer_harm_types,
                "owning_functions": failure_mode.owning_functions,
                "remediation_actions": failure_mode.remediation_actions,
                "source_tier": min(citation.tier for citation in failure_mode.citations),
                "validation_status": failure_mode.validation_status,
                "metadata": {"seed": True},
            }
        )
        if not failure_mode_id:
            continue
        failure_mode_count += 1
        for index, control_name in enumerate(failure_mode.controls, start=1):
            control_id = repo.upsert_control(
                {
                    "control_key": f"{failure_mode.failure_mode_id}_control_{index}",
                    "name": control_name,
                    "control_domain": failure_mode.control_domains[min(index - 1, len(failure_mode.control_domains) - 1)]
                    if failure_mode.control_domains
                    else None,
                    "control_type": "seed",
                    "source_tier": 2,
                    "validation_status": "seeded",
                    "metadata": {"seed": True},
                }
            )
            repo.link_failure_mode_control(failure_mode_id=failure_mode_id, control_id=control_id)
        for index, indicator_name in enumerate(failure_mode.risk_indicators, start=1):
            risk_indicator_id = repo.upsert_risk_indicator(
                {
                    "indicator_key": f"{failure_mode.failure_mode_id}_risk_{index}",
                    "name": indicator_name,
                    "description": indicator_name,
                    "severity_hint": "unknown",
                    "metadata": {"seed": True},
                }
            )
            repo.link_failure_mode_risk_indicator(
                failure_mode_id=failure_mode_id,
                risk_indicator_id=risk_indicator_id,
            )

    manifest_path = save_manifest(
        "seed_bootstrap_extractions",
        [
            {
                "obligations": obligation_count,
                "failure_modes": failure_mode_count,
            }
        ],
    )
    artifacts.append(str(manifest_path))
    return IngestionResult(
        name="seed_bootstrap_extractions",
        documents=0,
        sections=0,
        rows=obligation_count + failure_mode_count,
        artifacts=artifacts,
        notes=["Loaded seed obligations and supervisory mappings into the DB when available."],
    )

