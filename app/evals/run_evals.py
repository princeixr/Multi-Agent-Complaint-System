"""Evaluation harness for the complaint-classification pipeline.

Loads labelled datasets from ``datasets/`` and measures accuracy,
precision and recall across the key pipeline outputs.
"""

from __future__ import annotations

import csv
import json
import logging
from pathlib import Path
from typing import Any

from app.agents.classification import run_classification
from app.schemas.case import CaseRead
from app.schemas.classification import ClassificationResult

logger = logging.getLogger(__name__)

DATASETS_DIR = Path(__file__).resolve().parent / "datasets"


# ── Dataset loading ──────────────────────────────────────────────────────────

def load_dataset(filename: str) -> list[dict[str, Any]]:
    """Load a CSV or JSON-lines evaluation dataset.

    Expected columns / keys:
        narrative, expected_product_category, expected_issue_type
    """
    path = DATASETS_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Dataset not found: {path}")

    rows: list[dict[str, Any]] = []

    if path.suffix == ".csv":
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append(dict(row))
    elif path.suffix in (".jsonl", ".json"):
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    rows.append(json.loads(line))
    else:
        raise ValueError(f"Unsupported dataset format: {path.suffix}")

    logger.info("Loaded %d rows from %s", len(rows), filename)
    return rows


# ── Evaluation runner ────────────────────────────────────────────────────────

def _row_slice_tags(row: dict[str, Any]) -> list[str]:
    """Heuristic eval slices (see docs/CLASSIFICATION_EVAL_SLICES.md)."""
    tags: list[str] = []
    nar = (row.get("narrative") or "").strip()
    if len(nar) < 10:
        tags.append("narrative_absent")
    else:
        tags.append("long_narrative")
    low = nar.lower()
    if any(
        x in low
        for x in (" and also ", "another issue", "second problem", "in addition")
    ):
        tags.append("multi_issue_heuristic")
    if row.get("cfpb_product") and row.get("cfpb_issue") and len(nar) >= 10:
        tags.append("structured_plus_narrative")
    return tags


def evaluate_classification(
    dataset_file: str = "classification_eval.csv",
    model_name: str | None = None,
) -> dict[str, float]:
    """Run classification evaluation and return metric summary.

    Returns
    -------
    dict with keys: total, correct_product, correct_issue,
                    product_accuracy, issue_accuracy, avg_confidence,
                    slice_counts (JSON-serializable)
    """
    rows = load_dataset(dataset_file)

    total = len(rows)
    correct_product = 0
    correct_issue = 0
    confidence_sum = 0.0
    slice_counts: dict[str, dict[str, int]] = {}

    for row in rows:
        narrative = (row.get("narrative") or "").strip()
        case = CaseRead(
            consumer_narrative=narrative,
            product=row.get("product") or None,
            sub_product=row.get("sub_product") or None,
            cfpb_product=row.get("cfpb_product") or None,
            cfpb_sub_product=row.get("cfpb_sub_product") or None,
            cfpb_issue=row.get("cfpb_issue") or None,
            cfpb_sub_issue=row.get("cfpb_sub_issue") or None,
        )
        pipeline_out = run_classification(case=case, model_name=model_name)
        result: ClassificationResult = pipeline_out.result

        for tag in _row_slice_tags(row):
            bucket = slice_counts.setdefault(tag, {"n": 0, "correct_product": 0, "correct_issue": 0})
            bucket["n"] += 1
            if result.product_category.value == row["expected_product_category"]:
                bucket["correct_product"] += 1
            if result.issue_type.value == row["expected_issue_type"]:
                bucket["correct_issue"] += 1

        if result.product_category.value == row["expected_product_category"]:
            correct_product += 1
        if result.issue_type.value == row["expected_issue_type"]:
            correct_issue += 1
        confidence_sum += result.confidence

    metrics = {
        "total": total,
        "correct_product": correct_product,
        "correct_issue": correct_issue,
        "product_accuracy": correct_product / total if total else 0.0,
        "issue_accuracy": correct_issue / total if total else 0.0,
        "avg_confidence": confidence_sum / total if total else 0.0,
        "slice_counts": slice_counts,
    }

    logger.info("Evaluation results: %s", metrics)
    return metrics


# ── CLI entry point ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run complaint pipeline evals")
    parser.add_argument(
        "--dataset",
        default="classification_eval.csv",
        help="Dataset filename inside datasets/",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Model name (defaults to provider's default)",
    )
    args = parser.parse_args()

    from app.observability.logging import setup_logging

    setup_logging("INFO")

    results = evaluate_classification(
        dataset_file=args.dataset, model_name=args.model
    )
    print(json.dumps(results, indent=2))
