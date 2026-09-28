"""Validator-level regression coverage for the Stage 4 security corpus."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Connection
from app.guardrails.sql_validator import ValidationError, validate_sql


def _corpus() -> list[dict[str, str | None]]:
    corpus_path = Path(__file__).with_name("corpus.yaml")
    return yaml.safe_load(corpus_path.read_text(encoding="utf-8"))


def _connection() -> Connection:
    return Connection(
        id="conn-test",
        host="localhost",
        port=5432,
        username="readonly",
        encrypted_password="encrypted",
        database="demo",
        allowed_schemas=["public"],
    )


def _db(case_id: str) -> AsyncMock:
    db = AsyncMock(spec=AsyncSession)
    result = MagicMock()
    result.all.return_value = (
        [("public", "customers", "email")] if case_id.startswith("sensitive_column") else []
    )
    db.execute.return_value = result
    return db


@pytest.mark.asyncio
@pytest.mark.security
@pytest.mark.parametrize("case", _corpus(), ids=lambda case: str(case["id"]))
@patch("app.guardrails.sql_validator.explain", new_callable=AsyncMock)
async def test_validator_security_corpus(
    mock_explain: AsyncMock, case: dict[str, str | None]
) -> None:
    """Every malicious corpus statement is blocked with its declared error kind."""
    if case["expected"] == "pass":
        validated = await validate_sql(str(case["sql"]), _connection(), _db(str(case["id"])))
        assert validated.sql
        mock_explain.assert_awaited_once()
        return

    with pytest.raises(ValidationError) as raised:
        await validate_sql(str(case["sql"]), _connection(), _db(str(case["id"])))
    assert raised.value.kind == case["kind"]
    mock_explain.assert_not_awaited()
