"""Version strings stamped onto traces and workflow_runs."""

from __future__ import annotations

import os


def workflow_version() -> str:
    return os.getenv("WORKFLOW_VERSION", "1.0.0")


def prompt_bundle_version() -> str:
    return os.getenv("PROMPT_BUNDLE_VERSION", "default")


def knowledge_pack_version(company_id: str) -> str:
    return os.getenv("KNOWLEDGE_PACK_VERSION") or f"company:{company_id}"


def default_chat_model() -> str:
    return os.getenv("OPENAI_CHAT_MODEL", "gpt-4o")
