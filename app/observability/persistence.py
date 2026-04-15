"""Persist workflow_runs / workflow_steps to Postgres (best-effort if DB up)."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy.exc import SQLAlchemyError

from app.db.models import ComplaintCase, WorkflowRun, WorkflowStep
from app.db.session import SessionLocal
from app.observability.context import get_active_run
from app.knowledge.mock_company_pack import deployment_label
from app.observability.versions import (
    default_chat_model,
    knowledge_pack_version,
    prompt_bundle_version,
    workflow_version,
)

logger = logging.getLogger(__name__)


def insert_workflow_run(
    run_id: str,
    trace_id: str | None,
) -> bool:
    try:
        session = SessionLocal()
        try:
            label = deployment_label()
            row = WorkflowRun(
                run_id=run_id,
                company_id=label,
                trace_id=trace_id,
                started_at=datetime.utcnow(),
                run_status="running",
                workflow_version=workflow_version(),
                prompt_version=prompt_bundle_version(),
                knowledge_pack_version=knowledge_pack_version(),
                model_version=default_chat_model(),
            )
            session.add(row)
            session.commit()
            return True
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
    except SQLAlchemyError as e:
        logger.warning("workflow_runs insert skipped: %s", e)
        return False


def update_workflow_run_case_id(run_id: str, case_id: str) -> None:
    try:
        session = SessionLocal()
        try:
            row = session.get(WorkflowRun, run_id)
            if row:
                row.case_id = case_id
                session.commit()
        finally:
            session.close()
    except SQLAlchemyError as e:
        logger.warning("workflow_runs case_id update skipped: %s", e)


def insert_workflow_step(
    *,
    run_id: str,
    node_name: str,
    sequence_number: int,
    started_at: datetime,
    ended_at: datetime,
    latency_ms: float,
    status: str,
    retry_number: int,
    model_name: str | None,
    input_snapshot_json: str | None,
    output_snapshot_json: str | None,
    state_diff_json: str | None,
    confidence: float | None,
    error_type: str | None = None,
    error_message: str | None = None,
) -> None:
    try:
        session = SessionLocal()
        try:
            step = WorkflowStep(
                run_id=run_id,
                node_name=node_name,
                sequence_number=sequence_number,
                started_at=started_at,
                ended_at=ended_at,
                latency_ms=latency_ms,
                status=status,
                retry_number=retry_number,
                model_name=model_name,
                input_snapshot_json=input_snapshot_json,
                output_snapshot_json=output_snapshot_json,
                state_diff_json=state_diff_json,
                confidence=confidence,
                error_type=error_type,
                error_message=error_message,
            )
            session.add(step)
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
    except SQLAlchemyError as e:
        logger.warning("workflow_steps insert skipped: %s", e)


def finalize_workflow_run(
    run_id: str,
    *,
    run_status: str,
    final_route: str | None,
    final_severity: str | None,
    manual_review_required: bool,
    retry_count_total: int,
    token_total: int | None = None,
    cost_estimate_usd: float | None = None,
) -> None:
    try:
        session = SessionLocal()
        try:
            row = session.get(WorkflowRun, run_id)
            if not row:
                return
            row.ended_at = datetime.utcnow()
            row.run_status = run_status
            row.final_route = final_route
            row.final_severity = final_severity
            row.manual_review_required = manual_review_required
            row.retry_count_total = retry_count_total
            if token_total is not None:
                row.token_total = token_total
            if cost_estimate_usd is not None:
                row.cost_estimate_total = cost_estimate_usd
            # Read case_id before commit so it's available after session state changes
            linked_case_id = row.case_id
            session.commit()

            # Propagate cost to the linked complaint case
            if linked_case_id and (token_total is not None or cost_estimate_usd is not None):
                _update_case_cost(session, linked_case_id, token_total, cost_estimate_usd)
        finally:
            session.close()
    except SQLAlchemyError as e:
        logger.warning("workflow_runs finalize skipped: %s", e)


def _update_case_cost(
    session,
    case_id: str,
    token_total: int | None,
    cost_estimate_usd: float | None,
) -> None:
    """Write token/cost totals back to the complaint_cases row."""
    try:
        case = session.get(ComplaintCase, case_id)
        if not case:
            return
        if token_total is not None:
            case.token_total = token_total
        if cost_estimate_usd is not None:
            case.cost_estimate_usd = cost_estimate_usd
        session.commit()
    except SQLAlchemyError as e:
        logger.warning("complaint_cases cost update skipped (case=%s): %s", case_id, e)


def derive_run_outcome(final_state: dict[str, Any]) -> tuple[str, str | None, str | None, bool, int]:
    """run_status, final_route, final_severity, manual_review_required, retry_count."""
    retry_count = int(final_state.get("retry_count") or 0)
    routed = final_state.get("routed_to")
    review = final_state.get("review") or {}
    decision = review.get("decision") if isinstance(review, dict) else None

    risk = final_state.get("risk_assessment")
    sev = None
    if risk is not None:
        rd = risk.model_dump() if hasattr(risk, "model_dump") else dict(risk)
        sev = str(rd.get("risk_level", ""))

    manual = decision in ("escalate", "revise")
    if decision == "escalate":
        status = "escalated"
    elif decision == "revise":
        status = "needs_follow_up"
    else:
        status = "completed"

    return status, routed if isinstance(routed, str) else None, sev, manual, retry_count
