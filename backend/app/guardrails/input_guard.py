"""Pre-LLM input guardrail (S4.4).

Deterministic checks run before any LLM call:
  1. Empty / whitespace-only input
  2. Maximum length (configurable, default 2000 characters)
  3. Control characters (non-printable, non-whitespace)
  4. Suspicious injection heuristics (flag; we do NOT claim to be a robust
     defense — these are weak speed bumps; the real defense is the SQL
     validator and DB role boundaries)

Rejections are returned as a structured ``GuardrailError`` with a *kind*
field that the graph turns into a controlled user-facing failure.

SECURITY NOTE: The heuristic checks below are intentionally weak.  They
catch the most obvious prompt-injection attempts and provide a first line
of logging.  They are **not** a substitute for the SQL-level validator or
the database read-only role enforcement.  This is documented in
``docs/security.md``.
"""

from __future__ import annotations

import re
import unicodedata

from app.config import get_settings

# Compiled once at import time so repeated calls are cheap.
_CONTROL_CHAR_RE = re.compile(
    r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]"  # C0 controls minus tab/newline/CR
)

# Patterns that strongly suggest prompt-injection attempts.  We normalise
# to lower-case before matching.
_INJECTION_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "ignore_instructions",
        re.compile(r"\bignore\s+(previous|above|all)\s+(instructions?|rules?|prompts?)", re.I),
    ),
    ("jailbreak_bypass", re.compile(r"\bdisregard\s+(all\s+)?(previous|prior|above)\b", re.I)),
    (
        "role_override",
        re.compile(r"\byou\s+are\s+now\s+(a\s+)?(different|new|unrestricted|free)\b", re.I),
    ),
    ("system_prompt_leak", re.compile(r"\brepeat\s+(your|the)\s+(system\s+)?prompt\b", re.I)),
    ("privilege_escalation", re.compile(r"\bact\s+as\s+(admin|root|superuser|dba)\b", re.I)),
]


class GuardrailError(ValueError):
    """An input failed the deterministic pre-LLM guardrail check."""

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind


def _has_control_chars(text: str) -> bool:
    return bool(_CONTROL_CHAR_RE.search(text))


def _has_suspicious_unicode(text: str) -> bool:
    """Reject strings with Unicode control / format / private-use characters."""
    for ch in text:
        cat = unicodedata.category(ch)
        # Cf = format, Cc = control (beyond ASCII), Co = private use
        if cat in {"Cf", "Co"} or (cat == "Cc" and ch not in "\t\n\r"):
            return True
    return False


def check_input(question: str) -> None:
    """Validate a raw user question before it reaches the LLM.

    Raises ``GuardrailError`` on any failed check.  Returns ``None`` on
    success.

    This function is intentionally synchronous — it is cheap and must not
    block on any I/O.
    """
    if not question or not question.strip():
        raise GuardrailError("empty_input", "Question must not be empty.")

    settings = get_settings()
    max_len: int = getattr(settings, "MAX_QUESTION_LENGTH", 2000)
    if len(question) > max_len:
        raise GuardrailError(
            "input_too_long",
            f"Question exceeds the maximum allowed length of {max_len} characters.",
        )

    if _has_control_chars(question):
        raise GuardrailError(
            "control_characters",
            "Question contains disallowed control characters.",
        )

    if _has_suspicious_unicode(question):
        raise GuardrailError(
            "suspicious_unicode",
            "Question contains suspicious Unicode characters.",
        )

    for _kind, pattern in _INJECTION_PATTERNS:
        if pattern.search(question):
            raise GuardrailError(
                "injection_heuristic",
                # Deliberately vague user-facing message; log the specific
                # pattern server-side via structured logging (caller's job).
                "Question was flagged by the input safety check.",
            )
