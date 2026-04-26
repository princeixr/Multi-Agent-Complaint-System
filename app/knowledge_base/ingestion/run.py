from __future__ import annotations

import argparse
import logging

from app.knowledge_base.ingestion.local_cfpb_complaints import ingest_local_cfpb_complaints
from app.knowledge_base.ingestion.remote_sources import ingest_remote_source_group
from app.knowledge_base.ingestion.seed_extractions import seed_bootstrap_extractions
from app.knowledge_base.repository import KnowledgeBaseRepository, initialize_database

logger = logging.getLogger(__name__)


PHASE_TO_GROUPS = {
    "phase1": ["cfpb_regulations", "federal_regulatory_feeds"],
    "phase2": ["supervision_and_exams"],
    "phase3": ["agreements_and_disclosures"],
    "phase4": ["internal_sources"],
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Knowledge-base ingestion runner")
    parser.add_argument(
        "--phase",
        choices=["local-complaints", "phase1", "phase2", "phase3", "phase4", "all", "seed"],
        required=True,
    )
    parser.add_argument("--limit-files", type=int, default=None)
    parser.add_argument("--limit-urls-per-family", type=int, default=None)
    parser.add_argument("--skip-db", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")

    db_status = initialize_database() if not args.skip_db else None
    repo = KnowledgeBaseRepository(db_enabled=bool(db_status.available) if db_status else False)

    results = []
    if args.phase in {"local-complaints", "all"}:
        results.append(
            ingest_local_cfpb_complaints(repo=repo, limit_files=args.limit_files).as_dict()
        )
    if args.phase in {"seed", "all"}:
        results.append(seed_bootstrap_extractions(repo=repo).as_dict())
    for phase, groups in PHASE_TO_GROUPS.items():
        if args.phase not in {phase, "all"}:
            continue
        for group in groups:
            results.append(
                ingest_remote_source_group(
                    source_group_id=group,
                    repo=repo,
                    limit_urls_per_family=args.limit_urls_per_family,
                ).as_dict()
            )

    for item in results:
        print(item)


if __name__ == "__main__":
    main()
