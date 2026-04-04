# Single-row pipeline test: load one CFPB-style CSV row and run ``process_complaint``.

from __future__ import annotations

import json
import os
from datetime import datetime

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    load_dotenv = None  # type: ignore[assignment, misc]

if load_dotenv:
    load_dotenv()

try:
    import pandas as pd
except ModuleNotFoundError as e:
    raise RuntimeError(
        "pandas is required. Install in this environment, e.g. "
        "'./.venv/bin/python -m pip install pandas'"
    ) from e

from app.orchestrator.workflow import process_complaint

CSV_PATH = os.getenv("TEST_CSV_PATH", "complaint_data/split_file_0.csv")
DEFAULT_COMPANY_ID = os.getenv("COMPANY_ID", "mock_bank")
OUTPUT_CSV = os.getenv(
    "TEST_PIPELINE_OUTPUT_CSV",
    "testing_sample_pipeline_output.csv",
)


def get_first_existing(df: pd.DataFrame, col_candidates: list[str]) -> str | None:
    for c in col_candidates:
        if c in df.columns:
            return c
    return None


def _safe_json(obj: object) -> str:
    if obj is None:
        return ""
    if isinstance(obj, str):
        return obj
    try:
        return json.dumps(obj, default=str)
    except TypeError:
        return str(obj)


def build_row_record(
    payload: dict,
    case: object,
    *,
    source_csv: str,
) -> dict[str, str | None]:
    """Flatten CaseRead (or dict) into one CSV row."""
    if hasattr(case, "model_dump"):
        c = case.model_dump()
    elif isinstance(case, dict):
        c = case
    else:
        c = {}

    cls = c.get("classification") or {}
    risk = c.get("risk_assessment") or {}
    res = c.get("proposed_resolution") or {}
    rc = c.get("root_cause_hypothesis") or {}

    st = c.get("status", "")
    if hasattr(st, "value"):
        st = st.value

    return {
        "run_at_utc": datetime.utcnow().isoformat() + "Z",
        "source_csv": source_csv,
        "company_id": payload.get("company_id"),
        "consumer_narrative": (c.get("consumer_narrative") or payload.get("consumer_narrative")),
        "routed_to": c.get("routed_to"),
        "status": str(st) if st is not None else "",
        "classification_product_category": cls.get("product_category"),
        "classification_issue_type": cls.get("issue_type"),
        "classification_confidence": cls.get("confidence"),
        "risk_level": (risk.get("risk_level") if isinstance(risk, dict) else None),
        "risk_score": risk.get("risk_score") if isinstance(risk, dict) else None,
        "root_cause_summary": rc.get("summary") if isinstance(rc, dict) else _safe_json(rc),
        "resolution_action": res.get("recommended_action") if isinstance(res, dict) else None,
        "resolution_confidence": res.get("confidence") if isinstance(res, dict) else None,
        "compliance_flags_json": _safe_json(c.get("compliance_flags")),
        "review_notes": c.get("review_notes"),
        "classification_json": _safe_json(cls),
        "risk_assessment_json": _safe_json(risk),
        "proposed_resolution_json": _safe_json(res),
        "root_cause_json": _safe_json(rc),
        "evidence_trace_json": _safe_json(c.get("evidence_trace")),
    }


def main() -> None:
    openai_key = os.getenv("OPENAI_API_KEY")
    print("OPENAI_API_KEY set:", bool(openai_key))
    print("CSV_PATH:", CSV_PATH)
    print("DEFAULT_COMPANY_ID:", DEFAULT_COMPANY_ID)
    print("Pipeline output CSV:", OUTPUT_CSV)

    df = pd.read_csv(CSV_PATH)
    print("Loaded row columns:")
    print(list(df.columns))

    col_narrative = get_first_existing(
        df,
        [
            "Consumer complaint narrative",
            "consumer_narrative",
            "narrative",
        ],
    )
    col_product = get_first_existing(df, ["Product", "product"])
    col_sub_product = get_first_existing(df, ["Sub-product", "sub_product"])
    col_company = get_first_existing(df, ["Company", "company"])
    col_state = get_first_existing(df, ["State", "state"])
    col_zip = get_first_existing(df, ["ZIP code", "Zip code", "zip_code", "ZIP"])
    col_channel = get_first_existing(df, ["Submitted via", "Channel", "channel"])
    col_response = get_first_existing(
        df, ["Company response to consumer", "Company response"]
    )
    col_date_received = get_first_existing(df, ["Date received", "date_received"])
    col_issue = get_first_existing(df, ["Issue", "issue"])

    missing = [
        name
        for name, val in [
            ("narrative", col_narrative),
            ("issue", col_issue),
        ]
        if val is None
    ]
    if missing:
        raise RuntimeError(
            "CSV is missing required columns for the test: " + ", ".join(missing)
        )

    print("Using columns:")
    print(
        {
            "narrative": col_narrative,
            "issue": col_issue,
            "product": col_product,
            "sub_product": col_sub_product,
            "company": col_company,
            "state": col_state,
            "zip_code": col_zip,
            "channel": col_channel,
            "date_received": col_date_received,
            "requested_resolution": col_response,
        }
    )

    valid_mask = (
        df[col_narrative].notna()
        & (df[col_narrative].astype(str).str.len() >= 10)
    )
    if not valid_mask.any():
        raise RuntimeError(
            "No rows in the CSV have a narrative with at least 10 characters."
        )

    row = df.loc[valid_mask].iloc[0]

    channel_raw = (
        str(row[col_channel]).strip() if col_channel else "web"
    ).lower()
    channel_map = {
        "web": "web",
        "online": "web",
        "phone": "phone",
        "email": "email",
        "fax": "fax",
        "postal": "postal",
        "mail": "postal",
        "referral": "referral",
    }
    channel = channel_map.get(channel_raw, "web")

    submitted_at = None
    if col_date_received:
        val = row[col_date_received]
        if pd.notna(val):
            try:
                submitted_at = pd.to_datetime(val, errors="coerce").to_pydatetime()
            except Exception:
                submitted_at = None

    narrative_val = row[col_narrative]
    if pd.isna(narrative_val) or len(str(narrative_val).strip()) < 10:
        raise RuntimeError("Selected row has an invalid narrative.")

    payload = {
        "company_id": DEFAULT_COMPANY_ID,
        "consumer_narrative": str(narrative_val),
        "product": (str(row[col_product]).strip() if col_product else None) or None,
        "sub_product": (str(row[col_sub_product]).strip() if col_sub_product else None)
        or None,
        "company": (str(row[col_company]).strip() if col_company else None) or None,
        "state": (str(row[col_state]).strip() if col_state else None) or None,
        "zip_code": (str(row[col_zip]).strip() if col_zip else None) or None,
        "channel": channel,
        "submitted_at": submitted_at.isoformat() if submitted_at else None,
        "external_product_category": (str(row[col_product]).strip() if col_product else None)
        or None,
        "external_issue_type": (str(row[col_issue]).strip() if col_issue else None)
        or None,
        "requested_resolution": (str(row[col_response]).strip() if col_response else None)
        or None,
    }

    print("\nConstructed CaseCreate payload (trimmed):")
    print(
        {
            k: (str(v)[:120] + "..." if isinstance(v, str) and len(v) > 120 else v)
            for k, v in payload.items()
        }
    )

    if not openai_key:
        print(
            "\nOPENAI_API_KEY is not set; skipping the LLM-powered pipeline run."
        )
        return

    final_state = process_complaint(payload)
    case = final_state["case"]

    print("\nPipeline completed.")
    print("Routed to:", getattr(case, "routed_to", None) or case.get("routed_to"))

    cls = getattr(case, "classification", None) or (
        case.get("classification") if isinstance(case, dict) else None
    )
    print("\nClassification:")
    print(json.dumps(cls, indent=2, default=str))

    risk = getattr(case, "risk_assessment", None) or (
        case.get("risk_assessment") if isinstance(case, dict) else None
    )
    print("\nRisk assessment:")
    print(json.dumps(risk, indent=2, default=str))

    rc = getattr(case, "root_cause_hypothesis", None) or (
        case.get("root_cause_hypothesis") if isinstance(case, dict) else None
    )
    print("\nRoot-cause hypothesis:")
    print(json.dumps(rc, indent=2, default=str))

    pr = getattr(case, "proposed_resolution", None) or (
        case.get("proposed_resolution") if isinstance(case, dict) else None
    )
    print("\nProposed resolution:")
    print(json.dumps(pr, indent=2, default=str))

    cf = getattr(case, "compliance_flags", None) or (
        case.get("compliance_flags") if isinstance(case, dict) else None
    )
    print("\nCompliance flags:")
    print(json.dumps(cf, indent=2, default=str))

    et = getattr(case, "evidence_trace", None) or (
        case.get("evidence_trace") if isinstance(case, dict) else None
    )
    print("\nEvidence trace (first 3 items if present):")
    if isinstance(et, dict) and isinstance(et.get("items"), list):
        print(json.dumps({"items": et["items"][:3]}, indent=2, default=str))
    else:
        print(json.dumps(et, indent=2, default=str))

    out_row = build_row_record(payload, case, source_csv=CSV_PATH)
    pd.DataFrame([out_row]).to_csv("testing_sample_pipeline_output.csv", index=False)
    print(f"\nWrote pipeline summary row to testing_sample_pipeline_output.csv")


if __name__ == "__main__":
    main()
