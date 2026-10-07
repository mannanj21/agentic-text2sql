"""Defense-in-depth proof for attacks that bypass the validator in tests only."""

from __future__ import annotations

from contextlib import suppress
from pathlib import Path

import pytest
import yaml

from app.config import Settings
from app.database.crypto import CredentialCipher
from app.database.models import Connection
from app.guardrails.types import _validated_sql
from app.tools import execution
from app.tools.execution import ExecutionError, execute

pytestmark = [pytest.mark.asyncio, pytest.mark.integration, pytest.mark.security]

_VALIDATOR_ONLY_CASES = {
    "catalog_access",
    "comment_trick_2",
    "current_setting",
    "information_schema_access",
    "pg_advisory_lock",
    "pg_terminate_backend",
    "query_to_xml",
    "sensitive_column_aliased",
    "sensitive_column_direct",
    "sensitive_column_order_by",
    "sensitive_column_star",
    "sensitive_column_subquery",
    "sensitive_column_where",
    "set_config",
    "stacked_query_semicolon",
}


def _blocked_cases() -> list[dict[str, str]]:
    corpus = Path(__file__).with_name("corpus.yaml")
    cases: list[dict[str, str]] = yaml.safe_load(corpus.read_text(encoding="utf-8"))
    return [case for case in cases if case["expected"] == "blocked"]


def _settings() -> Settings:
    return Settings(ALLOW_PRIVATE_HOSTS=True, STATEMENT_TIMEOUT_MS=100)


def _connection() -> Connection:
    settings = _settings()
    return Connection(
        user_id="not-persisted",
        name="ecommerce",
        host="127.0.0.1",
        port=5434,
        database="ecommerce",
        username="readonly_demo",
        encrypted_password=CredentialCipher(settings.ENCRYPTION_KEY).encrypt("readonly_pass"),
    )


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM customers",
        "WITH deleted AS (DELETE FROM customers RETURNING id) SELECT * FROM deleted",
        "SELECT * INTO scratch_customers FROM customers",
        "SELECT pg_sleep(1)",
        "SELECT pg_read_file('/etc/passwd')",
    ],
)
async def test_database_blocks_validator_bypass(monkeypatch: pytest.MonkeyPatch, sql: str) -> None:
    """Read-only transaction, timeout, and role privileges stop unsafe raw SQL."""
    monkeypatch.setattr(execution, "get_settings", _settings)
    with pytest.raises(ExecutionError):
        await execute(_connection(), _validated_sql(sql))


async def test_sensitive_column_is_validator_only_defense(monkeypatch: pytest.MonkeyPatch) -> None:
    """The readonly role can select it, so the validator must enforce metadata policy."""
    monkeypatch.setattr(execution, "get_settings", _settings)
    result = await execute(_connection(), _validated_sql("SELECT email FROM customers LIMIT 1"))
    assert result.columns == ["email"]


@pytest.mark.parametrize("case", _blocked_cases(), ids=lambda case: case["id"])
async def test_every_blocked_corpus_case_has_a_database_boundary(
    monkeypatch: pytest.MonkeyPatch, case: dict[str, str]
) -> None:
    """Each malicious input is blocked below the validator or explicitly documented otherwise."""
    monkeypatch.setattr(execution, "get_settings", _settings)
    if case["id"] in _VALIDATOR_ONLY_CASES:
        with suppress(ExecutionError):
            await execute(_connection(), _validated_sql(case["sql"]))
        return

    with pytest.raises(ExecutionError):
        await execute(_connection(), _validated_sql(case["sql"]))
