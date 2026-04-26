from __future__ import annotations

import csv
import logging
from collections import Counter, defaultdict
from pathlib import Path

from app.knowledge_base.ingestion.common import (
    IngestionResult,
    REPO_ROOT,
    ensure_data_dirs,
    local_file_checksum,
    save_manifest,
    slugify,
    write_json,
)
from app.knowledge_base.repository import KnowledgeBaseRepository

logger = logging.getLogger(__name__)

COMPLAINT_DIR = REPO_ROOT / "complaint_data"


def ingest_local_cfpb_complaints(*, repo: KnowledgeBaseRepository, limit_files: int | None = None) -> IngestionResult:
    ensure_data_dirs()
    files = sorted(COMPLAINT_DIR.glob("*.csv"))
    if limit_files is not None:
        files = files[:limit_files]
    if not files:
        raise FileNotFoundError(f"No complaint CSV files found in {COMPLAINT_DIR}")

    dataset_id = repo.ensure_source_dataset(
        name="cfpb_local_complaint_history",
        source_type="cfpb_local_folder",
        description="Local CFPB complaint shard folder reused for precedent ingestion.",
        version="local_shards_v1",
    )

    total_rows = 0
    narratives = 0
    top_products: Counter[str] = Counter()
    top_issues: Counter[str] = Counter()
    cluster_counts: dict[tuple[str, str], int] = defaultdict(int)
    artifact_paths: list[str] = []
    documents = 0

    for csv_path in files:
        rows_for_db: list[dict[str, object]] = []
        row_count = 0
        with csv_path.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                row_count += 1
                total_rows += 1
                narrative = (row.get("Consumer complaint narrative") or "").strip()
                if narrative:
                    narratives += 1
                product = (row.get("Product") or "").strip()
                issue = (row.get("Issue") or "").strip()
                if product:
                    top_products[product] += 1
                if issue:
                    top_issues[issue] += 1
                if product or issue:
                    cluster_counts[(product or "unknown", issue or "unknown")] += 1
                complaint_id = (row.get("Complaint ID") or "").strip()
                rows_for_db.append(
                    {
                        "external_id": complaint_id,
                        "split": "raw",
                        "consumer_narrative": narrative,
                        "product": product or None,
                        "sub_product": (row.get("Sub-product") or "").strip() or None,
                        "issue": issue or None,
                        "sub_issue": (row.get("Sub-issue") or "").strip() or None,
                        "company": (row.get("Company") or "").strip() or None,
                        "state": (row.get("State") or "").strip() or None,
                        "submitted_via": (row.get("Submitted via") or "").strip() or None,
                        "date_received": (row.get("Date received") or "").strip() or None,
                        "company_response": (row.get("Company response to consumer") or "").strip() or None,
                        "company_public_response": (row.get("Company public response") or "").strip() or None,
                        "metadata": {
                            "tags": (row.get("Tags") or "").strip() or None,
                            "timely_response": (row.get("Timely response?") or "").strip() or None,
                            "consumer_disputed": (row.get("Consumer disputed?") or "").strip() or None,
                            "consumer_consent_provided": (row.get("Consumer consent provided?") or "").strip() or None,
                            "source_file": csv_path.name,
                        },
                    }
                )
        repo.insert_source_dataset_items(dataset_id, rows_for_db)

        repo.upsert_source_document(
            {
                "source_family_id": "cfpb_consumer_complaint_database",
                "source_tier": 3,
                "source_group": "cfpb_complaints",
                "authority_type": "official observational source",
                "source_url": str(csv_path.resolve()),
                "title": csv_path.name,
                "regulator": "CFPB",
                "document_type": "csv",
                "version_label": "local_folder",
                "raw_storage_uri": str(csv_path.resolve()),
                "checksum": local_file_checksum(csv_path),
                "metadata": {
                    "row_count": row_count,
                    "local": True,
                },
                "ingestion_status": "loaded",
                "validation_status": "seeded",
            }
        )
        documents += 1

    cluster_records = []
    for index, ((product, issue), count) in enumerate(
        sorted(cluster_counts.items(), key=lambda item: item[1], reverse=True)[:200],
        start=1,
    ):
        cluster_key = f"cfpb_local_{slugify(product)}_{slugify(issue)}"
        cluster_records.append(
            {
                "cluster_key": cluster_key,
                "name": f"{product} / {issue}",
                "product": None if product == "unknown" else product,
                "issue": None if issue == "unknown" else issue,
                "complaint_count": count,
                "metadata": {"rank": index, "source": "local_cfpb_complaints"},
            }
        )
        repo.upsert_precedent_cluster(cluster_records[-1])

    summary = {
        "source": "local_cfpb_complaints",
        "files": len(files),
        "rows": total_rows,
        "narratives_present": narratives,
        "top_products": top_products.most_common(25),
        "top_issues": top_issues.most_common(25),
        "top_clusters": sorted(cluster_records, key=lambda item: item["complaint_count"], reverse=True)[:50],
    }
    summary_path = REPO_ROOT / "knowledge_base" / "data" / "derived" / "manifests" / "local_cfpb_complaints_summary.json"
    write_json(summary_path, summary)
    manifest_path = save_manifest("local_cfpb_complaints", [summary])
    artifact_paths.extend([str(summary_path), str(manifest_path)])

    return IngestionResult(
        name="local_cfpb_complaints",
        documents=documents,
        sections=0,
        rows=total_rows,
        artifacts=artifact_paths,
        notes=[
            f"Loaded {len(files)} local CSV shard files without re-downloading CFPB complaints.",
            "Persisted complaint rows into source_datasets/source_dataset_items when DB was available.",
            "Derived precedent clusters from product/issue co-occurrence.",
        ],
    )

