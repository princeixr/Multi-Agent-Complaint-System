"""Per-request context for tracing (run_id, case_id, sequence, trace_id)."""

from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass


@dataclass
class ActiveRun:
    run_id: str
    company_id: str
    trace_id: str | None = None
    case_id: str | None = None
    sequence: int = 0

    def next_sequence(self) -> int:
        self.sequence += 1
        return self.sequence


_active: ContextVar[ActiveRun | None] = ContextVar("workflow_active_run", default=None)


def get_active_run() -> ActiveRun | None:
    return _active.get()


def set_active_run(active: ActiveRun) -> Token:
    return _active.set(active)


def reset_active_run(token: Token) -> None:
    _active.reset(token)


def set_case_id(case_id: str) -> None:
    ar = _active.get()
    if ar is not None:
        ar.case_id = case_id


def set_trace_id(trace_id: str) -> None:
    ar = _active.get()
    if ar is not None:
        ar.trace_id = trace_id
