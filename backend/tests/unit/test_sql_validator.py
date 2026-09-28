from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Connection
from app.guardrails.sql_validator import ValidationError, validate_sql


@pytest.fixture
def mock_db() -> AsyncMock:
    from unittest.mock import MagicMock

    db = AsyncMock(spec=AsyncSession)
    # mock db.execute().all() to return no sensitive columns
    db.execute.return_value.all = MagicMock(return_value=[])
    return db


@pytest.fixture
def mock_connection() -> Connection:
    return Connection(
        id="test_conn",
        host="localhost",
        port=5432,
        username="test",
        encrypted_password=b"encrypted",
        database="testdb",
        allowed_schemas=["public"],
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "sql",
    [
        "SELECT id, first_name FROM customers",
        "WITH active AS (SELECT id FROM customers) SELECT id FROM active",
        "select 1;",
    ],
)
@patch("app.guardrails.sql_validator.explain")
async def test_accepts_select_statements(
    mock_explain: AsyncMock, sql: str, mock_connection: Connection, mock_db: AsyncMock
) -> None:
    validated = await validate_sql(sql, mock_connection, mock_db)
    assert validated.sql.upper().startswith(("SELECT", "WITH"))
    mock_explain.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("sql", "kind"),
    [
        ("", "empty"),
        ("   ", "empty"),
        ("SELECT 1; SELECT 2", "multi_statement"),
        ("INSERT INTO customers (first_name) VALUES ('A')", "unauthorized_node"),
        ("UPDATE customers SET first_name = 'A'", "unauthorized_node"),
        ("DELETE FROM customers", "unauthorized_node"),
        ("SELECT FROM", "syntax"),
    ],
)
@patch("app.guardrails.sql_validator.explain")
async def test_rejects_non_readonly_or_invalid_sql(
    mock_explain: AsyncMock, sql: str, kind: str, mock_connection: Connection, mock_db: AsyncMock
) -> None:
    with pytest.raises(ValidationError) as raised:
        await validate_sql(sql, mock_connection, mock_db)
    assert raised.value.kind == kind
    mock_explain.assert_not_called()
