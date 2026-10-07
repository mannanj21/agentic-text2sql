"""Generate and answer nodes for the Text-to-SQL agent graph (Stage 3)."""

from __future__ import annotations

import datetime
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from app.llm.client import FakeLLM, LLMClient, TokenUsage

# ---------------------------------------------------------------------------
# Prompt loading
# ---------------------------------------------------------------------------

_PROMPTS_DIR = Path(__file__).parent / "prompts"
_MAX_CELL_CHARS = 200
_PREVIEW_ROWS = 20


def load_prompt(name: str) -> str:
    """Load a versioned prompt template from the prompts/ directory."""
    path = _PROMPTS_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"Prompt template not found: {path}")
    return path.read_text(encoding="utf-8")


def _render(template_text: str, **context: object) -> str:
    """Simple {{ key }} substitution; missing keys raise KeyError."""
    # Two-pass: first handle optional {% if key %} … {% endif %} blocks,
    # then substitute {{ key }} placeholders.
    rendered = _render_conditionals(template_text, context)
    for key, value in context.items():
        rendered = rendered.replace("{{ " + key + " }}", str(value) if value is not None else "")
    # Verify no leftover placeholders (catches typos in tests).
    remaining = re.findall(r"\{\{[^}]+\}\}", rendered)
    # Allow leftover only for keys that were absent (optional slots).
    if remaining:
        # strip whitespace and recheck against provided keys
        unresolved = [r for r in remaining if r.strip("{ }") not in context]
        if unresolved:
            raise ValueError(f"Unresolved prompt placeholders: {unresolved}")
    return rendered


def _render_conditionals(text: str, context: dict[str, Any]) -> str:
    """Remove {% if key %} … {% endif %} blocks whose key is falsy."""

    def replacer(m: re.Match[str]) -> str:
        key = m.group(1).strip()
        body = m.group(2)
        return body if context.get(key) else ""

    pattern = re.compile(r"\{%\s*if\s+(\w+)\s*%\}(.*?)\{%\s*endif\s*%\}", re.DOTALL)
    return pattern.sub(replacer, text)


# ---------------------------------------------------------------------------
# Result summary builder
# ---------------------------------------------------------------------------


class ResultSummary(BaseModel):
    """Compact, LLM-safe representation of a query result."""

    columns: list[str]
    row_count: int
    truncated: bool
    stats: str  # compact per-column stats block
    rows_preview: str  # TSV-like, capped at PREVIEW_ROWS rows


def _truncate_cell(value: Any, max_chars: int = _MAX_CELL_CHARS) -> str:
    """Stringify a cell value and truncate if necessary."""
    text = str(value) if value is not None else "NULL"
    if len(text) > max_chars:
        return text[:max_chars] + "…"
    return text


def _col_stats(values: list[Any]) -> str:
    """Return a compact stat string for one column."""
    non_null = [v for v in values if v is not None]
    null_count = len(values) - len(non_null)
    parts: list[str] = [f"nulls={null_count}"]
    if not non_null:
        return ", ".join(parts)
    # Try numeric stats
    try:
        nums = [float(v) for v in non_null]
        parts += [
            f"min={min(nums):.4g}",
            f"max={max(nums):.4g}",
            f"mean={sum(nums) / len(nums):.4g}",
        ]
    except (TypeError, ValueError):
        # String stats: distinct count
        distinct = len(set(str(v) for v in non_null))
        parts.append(f"distinct={distinct}")
    return ", ".join(parts)


def build_result_summary(
    columns: Sequence[str],
    rows: Sequence[Sequence[Any]],
    *,
    max_rows: int = _PREVIEW_ROWS,
) -> ResultSummary:
    """Build a compact, injection-safe summary of a query result.

    Rows beyond *max_rows* are omitted; cell values are truncated.
    No raw rows beyond the preview cap are included in the output.
    """
    col_list = list(columns)
    row_list = list(rows)
    truncated = len(row_list) > max_rows
    preview = row_list[:max_rows]

    # Per-column stats (computed over the preview rows only in stage 3)
    col_values: list[list[Any]] = [[] for _ in col_list]
    for row in preview:
        for i, val in enumerate(row):
            if i < len(col_list):
                col_values[i].append(val)

    stats_lines = [f"  {col}: {_col_stats(col_values[i])}" for i, col in enumerate(col_list)]
    stats_block = "\n".join(stats_lines)

    # TSV rows preview (each cell truncated)
    tsv_lines = ["\t".join(_truncate_cell(v) for v in row) for row in preview]
    rows_preview = "\n".join(tsv_lines) if tsv_lines else "(no rows)"

    return ResultSummary(
        columns=col_list,
        row_count=len(row_list),
        truncated=truncated,
        stats=stats_block,
        rows_preview=rows_preview,
    )


# ---------------------------------------------------------------------------
# Pydantic output schemas
# ---------------------------------------------------------------------------


class GenerateOutput(BaseModel):
    sql: str
    tables_used: list[str]
    assumptions: list[str]


class AnswerOutput(BaseModel):
    answer: str
    assumptions: list[str]


class RepairOutput(BaseModel):
    sql: str
    tables_used: list[str]
    assumptions: list[str]


# ---------------------------------------------------------------------------
# Shared LLM type alias (duck-typed: both LLMClient and FakeLLM work)
# ---------------------------------------------------------------------------

AnyLLM = LLMClient | FakeLLM


# ---------------------------------------------------------------------------
# Generate node
# ---------------------------------------------------------------------------

_GENERATE_PROMPT_NAME = "generate_v1.txt"


async def run_generate_node(
    *,
    llm: AnyLLM,
    question: str,
    schema_ddl: str,
    dialect: str = "postgresql",
    current_date: str | None = None,
    glossary: str | None = None,
    plan: str | None = None,
) -> tuple[GenerateOutput, TokenUsage]:
    """Call the LLM to generate SQL for *question* given *schema_ddl*.

    Returns (GenerateOutput, TokenUsage).  Raises LLMProviderError on failure.
    """
    if current_date is None:
        current_date = datetime.date.today().isoformat()

    template = load_prompt(_GENERATE_PROMPT_NAME)
    prompt = _render(
        template,
        dialect=dialect,
        current_date=current_date,
        schema_ddl=schema_ddl,
        glossary=glossary or "",
        plan=plan or "",
        question=question,
    )
    messages = [{"role": "user", "content": prompt}]
    return await llm.complete_structured("strong", messages, GenerateOutput, node="generate")


# ---------------------------------------------------------------------------
# Answer node
# ---------------------------------------------------------------------------

_ANSWER_PROMPT_NAME = "answer_v1.txt"


async def run_answer_node(
    *,
    llm: AnyLLM,
    question: str,
    sql: str,
    summary: ResultSummary,
    preview_rows: int = _PREVIEW_ROWS,
) -> tuple[AnswerOutput, TokenUsage]:
    """Call the LLM to produce a user-facing answer from a *summary*.

    The result rows are wrapped in <QUERY_RESULT> delimiters inside the
    prompt so injection strings inside cells are treated as untrusted data.
    """
    template = load_prompt(_ANSWER_PROMPT_NAME)
    prompt = _render(
        template,
        question=question,
        sql=sql,
        columns=", ".join(summary.columns),
        row_count=summary.row_count,
        truncated="true" if summary.truncated else "",
        preview_rows=preview_rows,
        stats=summary.stats,
        rows_preview=summary.rows_preview,
    )
    messages = [{"role": "user", "content": prompt}]
    return await llm.complete_structured("fast", messages, AnswerOutput, node="answer")


# ---------------------------------------------------------------------------
# Repair node
# ---------------------------------------------------------------------------

_REPAIR_PROMPT_NAME = "repair_v1.txt"


async def run_repair_node(
    *,
    llm: AnyLLM,
    question: str,
    schema_ddl: str,
    dialect: str = "postgresql",
    current_date: str | None = None,
    glossary: str | None = None,
    previous_sqls: list[str],
    failure_type: str,
    error_message: str,
) -> tuple[RepairOutput, TokenUsage]:
    """Call the LLM to produce a repaired SQL statement.

    Returns (RepairOutput, TokenUsage).  Raises LLMProviderError on failure.
    """
    if current_date is None:
        current_date = datetime.date.today().isoformat()

    previous_sqls_block = (
        "\n".join(f"{i + 1}. {sql}" for i, sql in enumerate(previous_sqls)) or "(none yet)"
    )

    template = load_prompt(_REPAIR_PROMPT_NAME)
    prompt = _render(
        template,
        dialect=dialect,
        current_date=current_date,
        schema_ddl=schema_ddl,
        glossary=glossary or "",
        question=question,
        previous_sqls=previous_sqls_block,
        failure_type=failure_type,
        error_message=error_message,
    )
    messages = [{"role": "user", "content": prompt}]
    return await llm.complete_structured("strong", messages, RepairOutput, node="repair")
