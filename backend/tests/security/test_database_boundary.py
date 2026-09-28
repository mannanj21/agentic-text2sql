"""Defense-in-depth proof for attacks that bypass the validator in tests only."""

from __future__ import annotations

import pytest

from app.config import Settings
from app.database.crypto import CredentialCipher
from app.database.models import Connection
from app.guardrails.types import _validated_sql
from app.tools import execution
from app.tools.execution import ExecutionError, execute

pytestmark = [pytest.mark.asyncio, pytest.mark.integration, pytest.mark.security]


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
