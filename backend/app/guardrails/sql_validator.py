"""Stage-3 structural SQL validation; the full policy is added in Stage 4."""

from __future__ import annotations

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

from app.guardrails.types import ValidatedSQL, _validated_sql


class ValidationError(ValueError):
    """A SQL statement failed deterministic structural validation."""

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind


def validate_sql(sql: str) -> ValidatedSQL:
    """Parse one PostgreSQL SELECT statement and return its opaque safe value."""
    if not isinstance(sql, str) or not sql.strip():
        raise ValidationError("empty", "SQL must not be empty.")
    try:
        statements = sqlglot.parse(sql, read="postgres")
    except ParseError as exc:
        raise ValidationError("syntax", "SQL could not be parsed.") from exc
    if len(statements) != 1:
        raise ValidationError("multi_statement", "Exactly one SQL statement is required.")
    statement = statements[0]
    if not isinstance(statement, exp.Select):
        raise ValidationError(
            "statement_type", "Only SELECT or WITH SELECT statements are allowed."
        )
    return _validated_sql(statement.sql(dialect="postgres"))
