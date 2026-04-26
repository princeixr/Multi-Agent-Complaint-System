from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from pypdf import PdfReader

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[3]
KB_ROOT = REPO_ROOT / "knowledge_base"
RAW_ROOT = KB_ROOT / "data" / "raw"
NORMALIZED_ROOT = KB_ROOT / "data" / "normalized"
DERIVED_ROOT = KB_ROOT / "data" / "derived"


def ensure_data_dirs() -> None:
    for path in (
        RAW_ROOT,
        NORMALIZED_ROOT / "docs",
        NORMALIZED_ROOT / "sections",
        DERIVED_ROOT / "manifests",
    ):
        path.mkdir(parents=True, exist_ok=True)


def slugify(text: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", text.strip().lower()).strip("_")
    return cleaned or "item"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")


def read_text_from_pdf(path: Path) -> str:
    reader = PdfReader(str(path))
    pages = []
    for page in reader.pages:
        pages.append(page.extract_text() or "")
    return "\n\n".join(pages).strip()


def strip_html_to_text(html: str) -> str:
    text = re.sub(r"(?is)<script.*?>.*?</script>", " ", html)
    text = re.sub(r"(?is)<style.*?>.*?</style>", " ", text)
    text = re.sub(r"(?i)</(p|div|section|article|li|h1|h2|h3|h4|h5|h6|br)>", "\n", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = unescape(text)
    text = re.sub(r"\r", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def simple_sectionize_text(text: str, *, prefix: str) -> list[dict[str, object]]:
    lines = [line.strip() for line in text.splitlines()]
    sections: list[dict[str, object]] = []
    current_title = "Introduction"
    current_lines: list[str] = []
    section_index = 0

    def flush() -> None:
        nonlocal section_index, current_lines, current_title
        body = "\n".join(line for line in current_lines if line).strip()
        if not body:
            return
        section_index += 1
        sections.append(
            {
                "section_key": f"{prefix}_section_{section_index}",
                "section_title": current_title,
                "section_path": [current_title],
                "citation_anchor": current_title[:255],
                "section_text": body,
                "metadata": {"line_count": len(current_lines)},
            }
        )
        current_lines = []

    for line in lines:
        if not line:
            current_lines.append("")
            continue
        if (
            len(line) < 140
            and len(line.split()) <= 18
            and not line.endswith(".")
            and sum(char.isalpha() for char in line) > 3
        ):
            flush()
            current_title = line
            continue
        current_lines.append(line)
    flush()
    return sections or [
        {
            "section_key": f"{prefix}_section_1",
            "section_title": "Full Text",
            "section_path": ["Full Text"],
            "citation_anchor": "Full Text",
            "section_text": text,
            "metadata": {},
        }
    ]


def fetch_url(url: str, destination: Path, *, timeout: int = 30) -> dict[str, object]:
    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; TriageAIKnowledgeIngest/1.0; +https://example.invalid)",
        },
    )
    with urlopen(request, timeout=timeout) as response:
        data = response.read()
        content_type = response.headers.get("Content-Type", "")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(data)
    return {
        "path": str(destination),
        "checksum": sha256_bytes(data),
        "bytes": len(data),
        "content_type": content_type,
        "retrieval_timestamp": utc_now().isoformat(),
    }


def local_file_checksum(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def dataset_slug_from_url(url: str) -> str:
    parsed = urlparse(url)
    host = slugify(parsed.netloc)
    tail = slugify(parsed.path or "root")
    return f"{host}_{tail}"


@dataclass
class IngestionResult:
    name: str
    documents: int = 0
    sections: int = 0
    rows: int = 0
    artifacts: list[str] | None = None
    notes: list[str] | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "documents": self.documents,
            "sections": self.sections,
            "rows": self.rows,
            "artifacts": self.artifacts or [],
            "notes": self.notes or [],
        }


def save_manifest(name: str, results: Iterable[dict[str, object]]) -> Path:
    ensure_data_dirs()
    path = DERIVED_ROOT / "manifests" / f"{slugify(name)}.json"
    write_json(path, {"generated_at": utc_now().isoformat(), "results": list(results)})
    return path

