from __future__ import annotations

import logging
from pathlib import Path
from urllib.parse import urlparse

from app.knowledge_base.ingestion.common import (
    IngestionResult,
    NORMALIZED_ROOT,
    RAW_ROOT,
    dataset_slug_from_url,
    ensure_data_dirs,
    fetch_url,
    read_text_from_pdf,
    save_manifest,
    simple_sectionize_text,
    strip_html_to_text,
    write_json,
)
from app.knowledge_base.repository import KnowledgeBaseRepository
from app.knowledge_base.source_inventory import SOURCE_GROUPS

logger = logging.getLogger(__name__)


def _extension_for_url(url: str, content_type: str) -> str:
    path = urlparse(url).path.lower()
    if path.endswith(".pdf") or "pdf" in content_type:
        return ".pdf"
    if path.endswith(".xml") or "xml" in content_type:
        return ".xml"
    if path.endswith(".json") or "json" in content_type:
        return ".json"
    return ".html"


def ingest_remote_source_group(
    *,
    source_group_id: str,
    repo: KnowledgeBaseRepository,
    limit_urls_per_family: int | None = None,
) -> IngestionResult:
    ensure_data_dirs()
    group = next((item for item in SOURCE_GROUPS if item.id == source_group_id), None)
    if group is None:
        raise KeyError(f"Unknown source group: {source_group_id}")

    results: list[dict[str, object]] = []
    documents = 0
    sections = 0
    artifact_paths: list[str] = []

    for family in group.families:
        urls = list(family.urls)
        if limit_urls_per_family is not None:
            urls = urls[:limit_urls_per_family]
        for url in urls:
            slug = dataset_slug_from_url(url)
            raw_dir = RAW_ROOT / group.id / family.id
            raw_dir.mkdir(parents=True, exist_ok=True)
            fetch_meta = fetch_url(url, raw_dir / f"{slug}")
            path = Path(fetch_meta["path"])
            ext = _extension_for_url(url, str(fetch_meta.get("content_type") or ""))
            if path.suffix != ext:
                renamed = path.with_suffix(ext)
                path.rename(renamed)
                path = renamed
                fetch_meta["path"] = str(path)

            if ext == ".pdf":
                raw_text = read_text_from_pdf(path)
            else:
                raw_text = strip_html_to_text(path.read_text(encoding="utf-8", errors="ignore"))
            section_payload = simple_sectionize_text(raw_text, prefix=slug)
            normalized_doc_dir = NORMALIZED_ROOT / "docs" / group.id / family.id
            normalized_section_dir = NORMALIZED_ROOT / "sections" / group.id / family.id
            normalized_doc_dir.mkdir(parents=True, exist_ok=True)
            normalized_section_dir.mkdir(parents=True, exist_ok=True)
            normalized_doc_path = normalized_doc_dir / f"{slug}.json"
            normalized_sections_path = normalized_section_dir / f"{slug}.json"
            write_json(
                normalized_doc_path,
                {
                    "source_family_id": family.id,
                    "source_group_id": group.id,
                    "source_url": url,
                    "title": family.label,
                    "document_type": ext.lstrip("."),
                    "raw_path": str(path),
                    "checksum": fetch_meta["checksum"],
                    "raw_text": raw_text,
                    "supports_layers": list(family.supports_layers),
                    "outputs": list(family.outputs),
                },
            )
            write_json(normalized_sections_path, section_payload)

            document_id = repo.upsert_source_document(
                {
                    "source_family_id": family.id,
                    "source_tier": family.tier,
                    "source_group": group.id,
                    "authority_type": family.authority_type,
                    "source_url": url,
                    "title": family.label,
                    "regulator": _infer_regulator(group.id, family.label),
                    "document_type": ext.lstrip("."),
                    "version_label": "fetched",
                    "raw_storage_uri": str(path),
                    "checksum": fetch_meta["checksum"],
                    "retrieval_timestamp": None,
                    "raw_text": raw_text,
                    "metadata": {
                        "content_type": fetch_meta.get("content_type"),
                        "bytes": fetch_meta.get("bytes"),
                        "supports_layers": list(family.supports_layers),
                        "outputs": list(family.outputs),
                    },
                    "ingestion_status": "parsed",
                    "validation_status": "seeded",
                }
            )
            repo.replace_document_sections(document_id=document_id, sections=section_payload)
            section_count = len(section_payload)
            documents += 1
            sections += section_count
            results.append(
                {
                    "family": family.id,
                    "url": url,
                    "raw_path": str(path),
                    "normalized_doc_path": str(normalized_doc_path),
                    "normalized_sections_path": str(normalized_sections_path),
                    "document_id": document_id,
                    "sections": section_count,
                }
            )
            artifact_paths.extend([str(path), str(normalized_doc_path), str(normalized_sections_path)])

    manifest_path = save_manifest(f"{source_group_id}_remote_ingest", results)
    artifact_paths.append(str(manifest_path))
    return IngestionResult(
        name=source_group_id,
        documents=documents,
        sections=sections,
        rows=0,
        artifacts=artifact_paths,
        notes=[f"Fetched and normalized source group {source_group_id}."],
    )


def _infer_regulator(group_id: str, label: str) -> str | None:
    if group_id.startswith("cfpb"):
        return "CFPB"
    if "govinfo" in group_id or "federal" in group_id:
        return "GovInfo/Federal Register"
    if "occ" in label.lower():
        return "OCC"
    if "fdic" in label.lower():
        return "FDIC"
    if "ffiec" in label.lower():
        return "FFIEC"
    if "fincen" in label.lower():
        return "FinCEN"
    return None
