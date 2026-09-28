"""Opaque values that may only be produced by deterministic guardrails."""


class ValidatedSQL:
    """SQL accepted by the validator; construction is intentionally internal."""

    def __init__(self, sql: str, *, _validator_token: object | None = None) -> None:
        if _validator_token is not _TOKEN:
            raise TypeError("ValidatedSQL may only be constructed by the SQL validator.")
        self.sql = sql


_TOKEN = object()


def _validated_sql(sql: str) -> ValidatedSQL:
    """Internal bridge for the validator introduced in S3.4."""
    return ValidatedSQL(sql, _validator_token=_TOKEN)
