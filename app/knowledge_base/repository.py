from __future__ import annotations

import json
import logging
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Iterator

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.models import (
    KBCitation,
    KBDeadline,
    KBDocumentSection,
    KBEvidenceRequirement,
    KBFailureMode,
    KBFailureModeControlLink,
    KBFailureModeRiskIndicatorLink,
    KBControl,
    KBObligation,
    KBPrecedentCluster,
    KBRiskIndicator,
    KBSourceDocument,
    SourceDataset,
    SourceDatasetItem,
)
from app.db.session import SessionLocal, init_db

logger = logging.getLogger(__name__)


def _json_text(value: object | None) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=True)


@dataclass
class DatabaseStatus:
    available: bool
    error: str | None = None


def initialize_database() -> DatabaseStatus:
    try:
        init_db()
        return DatabaseStatus(available=True)
    except Exception as exc:  # pragma: no cover - environment dependent
        logger.warning("Knowledge-base DB initialization unavailable: %s", exc)
        return DatabaseStatus(available=False, error=str(exc))


@contextmanager
def session_scope() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


class KnowledgeBaseRepository:
    """Persistence helper for knowledge-base ingestion jobs."""

    def __init__(self, *, db_enabled: bool = True) -> None:
        self.db_enabled = db_enabled

    def ensure_source_dataset(
        self,
        *,
        name: str,
        source_type: str,
        description: str,
        version: str,
        stats: dict[str, object] | None = None,
    ) -> str | None:
        if not self.db_enabled:
            return None
        with session_scope() as session:
            existing = session.execute(
                select(SourceDataset).where(SourceDataset.name == name)
            ).scalar_one_or_none()
            if existing:
                existing.source_type = source_type
                existing.description = description
                existing.version = version
                existing.stats_json = _json_text(stats)
                existing.updated_at = datetime.utcnow()
                session.flush()
                return existing.id

            record = SourceDataset(
                name=name,
                source_type=source_type,
                description=description,
                version=version,
                stats_json=_json_text(stats),
            )
            session.add(record)
            session.flush()
            return record.id

    def insert_source_dataset_items(
        self,
        dataset_id: str | None,
        rows: list[dict[str, object]],
    ) -> int:
        if not self.db_enabled or not dataset_id or not rows:
            return 0
        inserted = 0
        with session_scope() as session:
            for row in rows:
                external_id = str(row.get("external_id") or "")
                if not external_id:
                    continue
                existing = session.execute(
                    select(SourceDatasetItem).where(
                        SourceDatasetItem.dataset_id == dataset_id,
                        SourceDatasetItem.external_id == external_id,
                    )
                ).scalar_one_or_none()
                payload = {
                    "dataset_id": dataset_id,
                    "external_id": external_id,
                    "split": str(row.get("split") or "raw"),
                    "consumer_narrative": str(row.get("consumer_narrative") or ""),
                    "product": row.get("product"),
                    "sub_product": row.get("sub_product"),
                    "issue": row.get("issue"),
                    "sub_issue": row.get("sub_issue"),
                    "company": row.get("company"),
                    "state": row.get("state"),
                    "submitted_via": row.get("submitted_via"),
                    "date_received": row.get("date_received"),
                    "company_response": row.get("company_response"),
                    "company_public_response": row.get("company_public_response"),
                    "metadata_json": _json_text(row.get("metadata")),
                }
                if existing:
                    for key, value in payload.items():
                        setattr(existing, key, value)
                else:
                    session.add(SourceDatasetItem(**payload))
                    inserted += 1
        return inserted

    def upsert_source_document(self, payload: dict[str, object]) -> str | None:
        if not self.db_enabled:
            return None
        with session_scope() as session:
            source_url = payload.get("source_url")
            checksum = payload.get("checksum")
            query = select(KBSourceDocument).where(
                KBSourceDocument.source_family_id == str(payload["source_family_id"]),
                KBSourceDocument.title == str(payload["title"]),
            )
            if source_url:
                query = query.where(KBSourceDocument.source_url == str(source_url))
            existing = session.execute(query).scalar_one_or_none()
            if existing:
                self._assign_source_document(existing, payload)
                if checksum:
                    existing.checksum = str(checksum)
                existing.updated_at = datetime.utcnow()
                session.flush()
                return existing.id

            record = KBSourceDocument()
            self._assign_source_document(record, payload)
            session.add(record)
            session.flush()
            return record.id

    def replace_document_sections(
        self,
        *,
        document_id: str | None,
        sections: list[dict[str, object]],
    ) -> int:
        if not self.db_enabled or not document_id:
            return 0
        with session_scope() as session:
            existing = session.execute(
                select(KBDocumentSection).where(KBDocumentSection.document_id == document_id)
            ).scalars().all()
            for row in existing:
                session.delete(row)
            for section in sections:
                session.add(
                    KBDocumentSection(
                        document_id=document_id,
                        section_key=str(section["section_key"]),
                        section_title=str(section["section_title"]),
                        section_path_json=_json_text(section.get("section_path")),
                        citation_anchor=section.get("citation_anchor"),
                        section_text=str(section.get("section_text") or ""),
                        effective_from=section.get("effective_from"),
                        effective_to=section.get("effective_to"),
                        metadata_json=_json_text(section.get("metadata")),
                    )
                )
            return len(sections)

    def upsert_obligation(
        self,
        *,
        payload: dict[str, object],
        evidence_requirements: list[dict[str, object]],
        deadlines: list[dict[str, object]],
        citations: list[dict[str, object]],
    ) -> str | None:
        if not self.db_enabled:
            return None
        with session_scope() as session:
            existing = session.execute(
                select(KBObligation).where(KBObligation.obligation_key == str(payload["obligation_key"]))
            ).scalar_one_or_none()
            if existing is None:
                existing = KBObligation(obligation_key=str(payload["obligation_key"]))
                session.add(existing)
            self._assign_obligation(existing, payload)
            session.flush()
            obligation_id = existing.id

            session.query(KBEvidenceRequirement).filter_by(obligation_id=obligation_id).delete()
            session.query(KBDeadline).filter_by(obligation_id=obligation_id).delete()
            session.query(KBCitation).filter_by(target_table="kb_obligations", target_id=obligation_id).delete()

            for item in evidence_requirements:
                session.add(
                    KBEvidenceRequirement(
                        obligation_id=obligation_id,
                        evidence_key=str(item["evidence_key"]),
                        label=str(item["label"]),
                        description=item.get("description"),
                        evidence_type=item.get("evidence_type"),
                        is_mandatory=bool(item.get("is_mandatory", True)),
                        metadata_json=_json_text(item.get("metadata")),
                    )
                )
            for item in deadlines:
                session.add(
                    KBDeadline(
                        obligation_id=obligation_id,
                        deadline_key=str(item["deadline_key"]),
                        label=str(item["label"]),
                        duration_text=item.get("duration_text"),
                        trigger_event=item.get("trigger_event"),
                        deadline_type=item.get("deadline_type"),
                        rule_text=item.get("rule_text"),
                        metadata_json=_json_text(item.get("metadata")),
                    )
                )
            for item in citations:
                session.add(
                    KBCitation(
                        document_id=str(item["document_id"]),
                        section_id=item.get("section_id"),
                        target_table="kb_obligations",
                        target_id=obligation_id,
                        citation_anchor=item.get("citation_anchor"),
                        quote_text=item.get("quote_text"),
                        notes=item.get("notes"),
                        metadata_json=_json_text(item.get("metadata")),
                    )
                )
            return obligation_id

    def upsert_control(self, payload: dict[str, object]) -> str | None:
        if not self.db_enabled:
            return None
        with session_scope() as session:
            existing = session.execute(
                select(KBControl).where(KBControl.control_key == str(payload["control_key"]))
            ).scalar_one_or_none()
            if existing is None:
                existing = KBControl(control_key=str(payload["control_key"]))
                session.add(existing)
            existing.document_id = payload.get("document_id")
            existing.name = str(payload["name"])
            existing.control_domain = payload.get("control_domain")
            existing.control_type = payload.get("control_type")
            existing.summary = payload.get("summary")
            existing.owning_function = payload.get("owning_function")
            existing.source_tier = int(payload.get("source_tier", 2))
            existing.validation_status = str(payload.get("validation_status", "seeded"))
            existing.metadata_json = _json_text(payload.get("metadata"))
            session.flush()
            return existing.id

    def upsert_failure_mode(self, payload: dict[str, object]) -> str | None:
        if not self.db_enabled:
            return None
        with session_scope() as session:
            existing = session.execute(
                select(KBFailureMode).where(KBFailureMode.failure_mode_key == str(payload["failure_mode_key"]))
            ).scalar_one_or_none()
            if existing is None:
                existing = KBFailureMode(failure_mode_key=str(payload["failure_mode_key"]))
                session.add(existing)
            existing.document_id = payload.get("document_id")
            existing.name = str(payload["name"])
            existing.description = payload.get("description")
            existing.consumer_harm_types_json = _json_text(payload.get("consumer_harm_types"))
            existing.owning_functions_json = _json_text(payload.get("owning_functions"))
            existing.remediation_actions_json = _json_text(payload.get("remediation_actions"))
            existing.source_tier = int(payload.get("source_tier", 2))
            existing.validation_status = str(payload.get("validation_status", "seeded"))
            existing.metadata_json = _json_text(payload.get("metadata"))
            session.flush()
            return existing.id

    def upsert_risk_indicator(self, payload: dict[str, object]) -> str | None:
        if not self.db_enabled:
            return None
        with session_scope() as session:
            existing = session.execute(
                select(KBRiskIndicator).where(KBRiskIndicator.indicator_key == str(payload["indicator_key"]))
            ).scalar_one_or_none()
            if existing is None:
                existing = KBRiskIndicator(indicator_key=str(payload["indicator_key"]))
                session.add(existing)
            existing.name = str(payload["name"])
            existing.description = payload.get("description")
            existing.severity_hint = payload.get("severity_hint")
            existing.metadata_json = _json_text(payload.get("metadata"))
            session.flush()
            return existing.id

    def link_failure_mode_control(self, *, failure_mode_id: str | None, control_id: str | None, relation_type: str = "mitigates") -> None:
        if not self.db_enabled or not failure_mode_id or not control_id:
            return
        with session_scope() as session:
            existing = session.execute(
                select(KBFailureModeControlLink).where(
                    KBFailureModeControlLink.failure_mode_id == failure_mode_id,
                    KBFailureModeControlLink.control_id == control_id,
                )
            ).scalar_one_or_none()
            if existing is None:
                existing = KBFailureModeControlLink(
                    failure_mode_id=failure_mode_id,
                    control_id=control_id,
                )
                session.add(existing)
            existing.relation_type = relation_type

    def link_failure_mode_risk_indicator(
        self,
        *,
        failure_mode_id: str | None,
        risk_indicator_id: str | None,
        relation_type: str = "raises",
    ) -> None:
        if not self.db_enabled or not failure_mode_id or not risk_indicator_id:
            return
        with session_scope() as session:
            existing = session.execute(
                select(KBFailureModeRiskIndicatorLink).where(
                    KBFailureModeRiskIndicatorLink.failure_mode_id == failure_mode_id,
                    KBFailureModeRiskIndicatorLink.risk_indicator_id == risk_indicator_id,
                )
            ).scalar_one_or_none()
            if existing is None:
                existing = KBFailureModeRiskIndicatorLink(
                    failure_mode_id=failure_mode_id,
                    risk_indicator_id=risk_indicator_id,
                )
                session.add(existing)
            existing.relation_type = relation_type

    def upsert_precedent_cluster(self, payload: dict[str, object]) -> str | None:
        if not self.db_enabled:
            return None
        with session_scope() as session:
            existing = session.execute(
                select(KBPrecedentCluster).where(KBPrecedentCluster.cluster_key == str(payload["cluster_key"]))
            ).scalar_one_or_none()
            if existing is None:
                existing = KBPrecedentCluster(cluster_key=str(payload["cluster_key"]))
                session.add(existing)
            existing.document_id = payload.get("document_id")
            existing.name = str(payload["name"])
            existing.product = payload.get("product")
            existing.issue = payload.get("issue")
            existing.narrative_signature = payload.get("narrative_signature")
            existing.failure_mode_id = payload.get("failure_mode_id")
            existing.complaint_count = int(payload.get("complaint_count", 0))
            existing.first_seen_at = payload.get("first_seen_at")
            existing.last_seen_at = payload.get("last_seen_at")
            existing.metadata_json = _json_text(payload.get("metadata"))
            session.flush()
            return existing.id

    @staticmethod
    def _assign_source_document(record: KBSourceDocument, payload: dict[str, object]) -> None:
        record.source_family_id = str(payload["source_family_id"])
        record.source_tier = int(payload.get("source_tier", 1))
        record.source_group = payload.get("source_group")
        record.authority_type = payload.get("authority_type")
        record.source_url = payload.get("source_url")
        record.title = str(payload["title"])
        record.regulator = payload.get("regulator")
        record.document_type = str(payload.get("document_type") or "unknown")
        record.publication_date = payload.get("publication_date")
        record.effective_date = payload.get("effective_date")
        record.version_label = payload.get("version_label")
        record.jurisdiction = str(payload.get("jurisdiction") or "US")
        record.product_scope_json = _json_text(payload.get("product_scope"))
        record.law_scope_json = _json_text(payload.get("law_scope"))
        record.checksum = payload.get("checksum")
        record.retrieval_timestamp = payload.get("retrieval_timestamp")
        record.raw_storage_uri = payload.get("raw_storage_uri")
        record.raw_text = payload.get("raw_text")
        record.metadata_json = _json_text(payload.get("metadata"))
        record.ingestion_status = str(payload.get("ingestion_status", "seeded"))
        record.validation_status = str(payload.get("validation_status", "seeded"))
        record.supersedes_document_id = payload.get("supersedes_document_id")

    @staticmethod
    def _assign_obligation(record: KBObligation, payload: dict[str, object]) -> None:
        record.document_id = payload.get("document_id")
        record.section_id = payload.get("section_id")
        record.title = str(payload["title"])
        record.summary = str(payload["summary"])
        record.layer = str(payload.get("layer", "canonical_regulatory_graph"))
        record.regulation = str(payload["regulation"])
        record.regulation_section = str(payload["regulation_section"])
        record.covered_entity_type = payload.get("covered_entity_type")
        record.trigger_conditions_json = _json_text(payload.get("trigger_conditions"))
        record.exceptions_json = _json_text(payload.get("exceptions"))
        record.consumer_rights_json = _json_text(payload.get("consumer_rights"))
        record.required_communications_json = _json_text(payload.get("required_communications"))
        record.effective_from = payload.get("effective_from")
        record.effective_to = payload.get("effective_to")
        record.source_tier = int(payload.get("source_tier", 1))
        record.validation_status = str(payload.get("validation_status", "seeded"))
        record.metadata_json = _json_text(payload.get("metadata"))
