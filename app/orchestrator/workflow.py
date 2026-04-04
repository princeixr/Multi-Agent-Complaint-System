"""LangGraph workflow that orchestrates all complaint‑processing agents."""

from __future__ import annotations

import json
import logging
import uuid

from langgraph.graph import END, StateGraph
from opentelemetry.trace import Status, StatusCode

from app.agents.classification import run_classification
from app.agents.compliance import run_compliance_check
from app.agents.intake import run_intake
from app.agents.root_cause import run_root_cause_hypothesis
from app.agents.resolution import run_resolution
from app.agents.review import run_review
from app.agents.risk import run_risk_assessment
from app.agents.routing import run_routing
from app.knowledge import CompanyKnowledgeService
from app.orchestrator.rules import (
    low_confidence_gate,
    needs_compliance_review,
    review_decision_router,
)
from app.orchestrator.retrieval_gate import vector_db_available
from app.observability.context import ActiveRun, reset_active_run, set_active_run, set_trace_id
from app.observability.events import log_workflow_event
from app.observability.instrumentation import wrap_node
from app.observability.persistence import (
    derive_run_outcome,
    finalize_workflow_run,
    insert_workflow_run,
)
from app.observability.tracing import get_workflow_tracer, setup_tracing, trace_id_hex_from_span
from app.observability.versions import workflow_version
from app.orchestrator.state import WorkflowState
from app.retrieval.complaint_index import ComplaintIndex
from app.retrieval.resolution_index import ResolutionIndex
from app.schemas.case import CaseCreate, CaseStatus
from app.schemas.evidence import EvidenceItem, EvidenceTrace
from app.schemas.root_cause import RootCauseHypothesis

logger = logging.getLogger(__name__)

# ── Lazy retrieval indices (avoid loading embedding models at import time) ──
_complaint_index: ComplaintIndex | None = None
_resolution_index: ResolutionIndex | None = None
_company_knowledge_by_id: dict[str, CompanyKnowledgeService] = {}


def _complaint_index_singleton() -> ComplaintIndex | None:
    global _complaint_index
    if not vector_db_available():
        return None
    if _complaint_index is None:
        _complaint_index = ComplaintIndex()
    return _complaint_index


def _resolution_index_singleton() -> ResolutionIndex | None:
    global _resolution_index
    if not vector_db_available():
        return None
    if _resolution_index is None:
        _resolution_index = ResolutionIndex()
    return _resolution_index


def _company_knowledge_singleton(company_id: str) -> CompanyKnowledgeService:
    if company_id not in _company_knowledge_by_id:
        _company_knowledge_by_id[company_id] = CompanyKnowledgeService(
            company_id=company_id
        )
    return _company_knowledge_by_id[company_id]


# ── Node functions ───────────────────────────────────────────────────────────

def intake_node(state: WorkflowState) -> WorkflowState:
    payload = CaseCreate(**state["raw_payload"])
    case = run_intake(payload)
    return {**state, "case": case}


def company_context_node(state: WorkflowState) -> WorkflowState:
    case = state["case"]
    company_id = state["company_id"]

    company_knowledge = _company_knowledge_singleton(company_id)
    context = company_knowledge.build_company_context(case.consumer_narrative)

    # Evidence trace begins with the company knowledge slices we retrieved.
    evidence_trace = EvidenceTrace(
        items=[
            EvidenceItem(
                evidence_type="company_taxonomy_candidates",
                summary="Operational taxonomy slices selected for this narrative",
                source_ref=company_id,
                metadata=context.taxonomy_candidates,
            ),
            EvidenceItem(
                evidence_type="company_severity_candidates",
                summary="Company severity rubric snippets selected for this narrative",
                source_ref=company_id,
                metadata={"severity_candidates": context.severity_candidates},
            ),
            EvidenceItem(
                evidence_type="company_policy_candidates",
                summary="Company policy snippets selected for this narrative",
                source_ref=company_id,
                metadata={"policy_candidates": context.policy_candidates},
            ),
            EvidenceItem(
                evidence_type="company_root_cause_controls",
                summary="Control knowledge selected for root-cause inference",
                source_ref=company_id,
                metadata={"controls": context.root_cause_controls},
            ),
        ]
    )

    case.evidence_trace = evidence_trace.model_dump()
    return {
        **state,
        "company_context": {
            "company_id": company_id,
            "taxonomy_candidates": context.taxonomy_candidates,
            "severity_candidates": context.severity_candidates,
            "policy_candidates": context.policy_candidates,
            "routing_candidates": context.routing_candidates,
            "root_cause_controls": context.root_cause_controls,
        },
        "evidence_trace": evidence_trace,
        "case": case,
    }


def classify_node(state: WorkflowState) -> WorkflowState:
    case = state["case"]
    retry = state.get("classification") is not None
    if retry:
        # Fix retry-counter progression: when we loop back to classification,
        # increment the counter so downstream gates can stop after MAX_RETRIES.
        state["retry_count"] = state.get("retry_count", 0) + 1  # type: ignore[misc]
    result = run_classification(
        narrative=case.consumer_narrative,
        product=case.product,
        sub_product=case.sub_product,
        company=case.company,
        state=case.state,
        complaint_index=_complaint_index_singleton(),
        company_context=state.get("company_context"),
    )
    case.classification = result.model_dump()
    case.status = CaseStatus.CLASSIFIED
    case.operational_mapping = {
        "product_category": result.product_category.value,
        "issue_type": result.issue_type.value,
        "sub_issue": result.sub_issue,
    }
    return {**state, "case": case, "classification": result}


def risk_node(state: WorkflowState) -> WorkflowState:
    case = state["case"]
    result = run_risk_assessment(
        narrative=case.consumer_narrative,
        classification=state["classification"],
        complaint_index=_complaint_index_singleton(),
        company_context=state.get("company_context"),
    )
    case.risk_assessment = result.model_dump()
    case.severity_class = result.risk_level.value
    case.status = CaseStatus.RISK_ASSESSED
    return {**state, "case": case, "risk_assessment": result}


def root_cause_node(state: WorkflowState) -> WorkflowState:
    case = state["case"]
    company_context = state.get("company_context", {})

    result: RootCauseHypothesis = run_root_cause_hypothesis(
        narrative=case.consumer_narrative,
        classification=state["classification"],
        risk=state["risk_assessment"],
        company_root_cause_controls=company_context.get("root_cause_controls", []),
        evidence_trace=state.get("evidence_trace"),
    )
    case.root_cause_hypothesis = result.model_dump()
    case.status = CaseStatus.RISK_ASSESSED  # root-cause doesn't change main stage enum yet
    return {**state, "case": case, "root_cause_hypothesis": result}


def resolution_node(state: WorkflowState) -> WorkflowState:
    case = state["case"]
    if state.get("resolution") is not None:
        state["retry_count"] = state.get("retry_count", 0) + 1  # type: ignore[misc]
    result = run_resolution(
        narrative=case.consumer_narrative,
        classification=state["classification"],
        risk=state["risk_assessment"],
        resolution_index=_resolution_index_singleton(),
        root_cause_hypothesis=state.get("root_cause_hypothesis"),
        company_context=state.get("company_context"),
    )
    case.proposed_resolution = result.model_dump()
    case.status = CaseStatus.RESOLUTION_PROPOSED
    return {**state, "case": case, "resolution": result}


def compliance_node(state: WorkflowState) -> WorkflowState:
    case = state["case"]
    result = run_compliance_check(
        narrative=case.consumer_narrative,
        classification=state["classification"],
        risk=state["risk_assessment"],
        resolution=state["resolution"],
        company_context=state.get("company_context"),
    )
    case.compliance_flags = result.get("flags", [])
    case.evidence_trace = (
        state.get("evidence_trace").model_dump() if state.get("evidence_trace") else None
    )
    case.status = CaseStatus.COMPLIANCE_CHECKED
    return {**state, "case": case, "compliance": result}


def review_node(state: WorkflowState) -> WorkflowState:
    case = state["case"]
    result = run_review(
        narrative=case.consumer_narrative,
        classification_json=json.dumps(state["classification"].model_dump()),
        risk_json=json.dumps(state["risk_assessment"].model_dump()),
        resolution_json=json.dumps(state["resolution"].model_dump()),
        compliance_json=json.dumps(state.get("compliance", {})),
    )
    case.review_notes = result.get("notes", "")
    case.status = CaseStatus.REVIEWED
    return {**state, "case": case, "review": result}


def routing_node(state: WorkflowState) -> WorkflowState:
    case = state["case"]
    destination = run_routing(
        case=case,
        classification=state["classification"],
        risk=state["risk_assessment"],
        root_cause_hypothesis=state.get("root_cause_hypothesis"),
        review_decision=state.get("review", {}).get("decision", "approve"),
        company_context=state.get("company_context"),
    )
    case.routed_to = destination
    case.team_assignment = destination
    case.status = CaseStatus.ROUTED
    return {**state, "case": case, "routed_to": destination}


# ── Conditional‑edge helpers (must return node names) ────────────────────────

def _confidence_router(state: WorkflowState) -> str:
    return low_confidence_gate(state)


def _compliance_router(state: WorkflowState) -> str:
    if needs_compliance_review(state):
        return "compliance"
    return "review"


def _review_router(state: WorkflowState) -> str:
    return review_decision_router(state)


# ── Build the graph ──────────────────────────────────────────────────────────

def build_workflow() -> StateGraph:
    """Construct and return the compiled LangGraph workflow."""

    graph = StateGraph(WorkflowState)

    # Add nodes (wrapped for OTel spans, JSON logs, and workflow_steps audit rows)
    graph.add_node("intake", wrap_node("intake", intake_node))
    graph.add_node(
        "retrieve_company_context",
        wrap_node("retrieve_company_context", company_context_node),
    )
    graph.add_node("classify", wrap_node("classify", classify_node))
    graph.add_node("risk", wrap_node("risk", risk_node))
    graph.add_node("root_cause", wrap_node("root_cause", root_cause_node))
    graph.add_node("propose_resolution", wrap_node("propose_resolution", resolution_node))
    graph.add_node("run_compliance", wrap_node("run_compliance", compliance_node))
    graph.add_node("review_gate", wrap_node("review_gate", review_node))
    graph.add_node("route", wrap_node("route", routing_node))

    # Set entry point
    graph.set_entry_point("intake")

    # Linear edges
    graph.add_edge("intake", "retrieve_company_context")
    graph.add_edge("retrieve_company_context", "classify")

    # Conditional: after classification, check confidence
    graph.add_conditional_edges(
        "classify",
        _confidence_router,
        {"continue": "risk", "reclassify": "classify"},
    )

    graph.add_edge("risk", "root_cause")
    graph.add_edge("root_cause", "propose_resolution")

    # Conditional: after resolution, decide if compliance check is needed
    graph.add_conditional_edges(
        "propose_resolution",
        _compliance_router,
        {"compliance": "run_compliance", "review": "review_gate"},
    )

    graph.add_edge("run_compliance", "review_gate")

    # Conditional: after review, decide next step
    graph.add_conditional_edges(
        "review_gate",
        _review_router,
        {"route": "route", "revise": "propose_resolution", "escalate": "route"},
    )

    graph.add_edge("route", END)

    return graph.compile()


# ── Convenience runner ───────────────────────────────────────────────────────

workflow = build_workflow()


def process_complaint(payload: dict) -> WorkflowState:
    """Run the full complaint pipeline and return the final state."""
    setup_tracing()

    run_id = uuid.uuid4().hex
    company_id = payload.get("company_id") or "mock_bank"
    ar = ActiveRun(run_id=run_id, company_id=company_id)
    ctx_token = set_active_run(ar)
    tracer = get_workflow_tracer()

    initial_state: WorkflowState = {
        "raw_payload": payload,
        "retry_count": 0,
        "company_id": company_id,
    }

    invoke_config = {
        "run_name": f"complaint-{run_id}",
        "tags": [f"company_id:{company_id}", f"run_id:{run_id}"],
        "metadata": {
            "run_id": run_id,
            "company_id": company_id,
            "workflow_version": workflow_version(),
        },
    }

    final_state: WorkflowState | None = None
    try:
        with tracer.start_as_current_span("process_complaint") as root:
            tid = trace_id_hex_from_span(root)
            if tid:
                set_trace_id(tid)
            root.set_attribute("complaint.run_id", run_id)
            root.set_attribute("complaint.company_id", company_id)

            log_workflow_event(
                "workflow_started",
                run_id=run_id,
                company_id=company_id,
                trace_id=tid or "",
            )
            insert_workflow_run(run_id, company_id, tid or None)

            try:
                final_state = workflow.invoke(initial_state, config=invoke_config)
            except Exception as exc:
                root.record_exception(exc)
                root.set_status(Status(StatusCode.ERROR, str(exc)))
                log_workflow_event(
                    "workflow_failed",
                    run_id=run_id,
                    node_name="process_complaint",
                    error_type=type(exc).__name__,
                    error_message=str(exc)[:500],
                )
                finalize_workflow_run(
                    run_id,
                    run_status="failed",
                    final_route=None,
                    final_severity=None,
                    manual_review_required=False,
                    retry_count_total=int(initial_state.get("retry_count") or 0),
                )
                raise

            root.set_status(Status(StatusCode.OK))

        assert final_state is not None
        status, route, sev, manual, retries = derive_run_outcome(final_state)
        finalize_workflow_run(
            run_id,
            run_status=status,
            final_route=route,
            final_severity=sev,
            manual_review_required=manual,
            retry_count_total=retries,
        )
        log_workflow_event(
            "workflow_completed",
            run_id=run_id,
            final_route=route,
            run_status=status,
            total_retry_count=retries,
        )
        logger.info("Workflow complete – routed to %s", final_state.get("routed_to"))
        return final_state
    finally:
        reset_active_run(ctx_token)
