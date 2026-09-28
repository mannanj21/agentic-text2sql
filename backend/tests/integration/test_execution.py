import pytest

from app.config import Settings
from app.database.crypto import CredentialCipher
from app.database.models import Connection
from app.guardrails.types import _validated_sql
from app.tools import execution
from app.tools.execution import ExecutionError, execute

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


def target_connection(username: str, password: str) -> Connection:
    settings = Settings(ALLOW_PRIVATE_HOSTS=True, MAX_RESULT_ROWS=2, STATEMENT_TIMEOUT_MS=100)
    return Connection(
        user_id="not-persisted",
        name="demo",
        host="127.0.0.1",
        port=5434,
        database="ecommerce",
        username=username,
        encrypted_password=CredentialCipher(settings.ENCRYPTION_KEY).encrypt(password),
    )


def local_settings() -> Settings:
    return Settings(ALLOW_PRIVATE_HOSTS=True, MAX_RESULT_ROWS=2, STATEMENT_TIMEOUT_MS=100)


async def test_execute_select_and_truncates(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(execution, "get_settings", local_settings)
    result = await execute(
        target_connection("readonly_demo", "readonly_pass"),
        _validated_sql("SELECT id FROM customers ORDER BY id"),
    )
    assert result.columns == ["id"]
    assert result.row_count == 2
    assert result.truncated is True


@pytest.mark.parametrize(
    ("sql", "kind"),
    [
        ("SELEC 1", "syntax"),
        ("SELECT missing_column FROM customers", "unknown_identifier"),
        ("SELECT pg_sleep(1)", "timeout"),
    ],
)
async def test_execute_classifies_postgres_errors(
    monkeypatch: pytest.MonkeyPatch, sql: str, kind: str
) -> None:
    monkeypatch.setattr(execution, "get_settings", local_settings)
    with pytest.raises(ExecutionError) as raised:
        await execute(target_connection("readonly_demo", "readonly_pass"), _validated_sql(sql))
    assert raised.value.kind == kind


async def test_execute_forces_read_only_for_writer_role(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(execution, "get_settings", local_settings)
    with pytest.raises(ExecutionError) as raised:
        await execute(
            target_connection("writer_demo", "writer_pass"),
            _validated_sql("UPDATE customers SET first_name = first_name"),
        )
    assert raised.value.kind == "other"
