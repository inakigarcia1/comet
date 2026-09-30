import re
from contextvars import ContextVar

_TRACE = re.compile(r"^[A-Za-z0-9_-]{6,40}$")
_trace_id: ContextVar[str] = ContextVar("apachiy_trace", default="-")


def set_trace(value: str | None) -> str:
    text = (value or "").strip()
    current = text if _TRACE.fullmatch(text) else "-"
    _trace_id.set(current)
    return current


def current_trace() -> str:
    return _trace_id.get()
