"""Validator-level regression coverage for the Stage 4 security corpus."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml
from hypothesis import given, settings
from hypothesis import strategies as st
from sqlalchemy.ext.asyncio import AsyncSession
from sqlglot import exp

from app.database.models import Connection
from app.guardrails.sql_validator import FORBIDDEN_NODES, ValidationError, validate_sql


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


@pytest.mark.asyncio
@pytest.mark.security
@settings(max_examples=25)
@given(
    sql=st.sampled_from(
        [
            "SELECT id FROM public.products",
            "SELECT count(*) FROM public.products",
            "SELECT id FROM public.products WHERE id = 1",
        ]
    ),
    leading_space=st.text(alphabet=" \t\n", min_size=0, max_size=4),
    trailing_space=st.text(alphabet=" \t\n", min_size=0, max_size=4),
)
async def test_whitespace_mutations_never_validate_forbidden_ast(
    sql: str, leading_space: str, trailing_space: str
) -> None:
    """Fuzz-lite: accepted benign mutations contain no forbidden AST nodes."""
    with patch("app.guardrails.sql_validator.explain", new_callable=AsyncMock):
        validated = await validate_sql(
            f"{leading_space}{sql}{trailing_space}", _connection(), _db("benign")
        )
    parsed = exp.maybe_parse(validated.sql, dialect="postgres")
    assert not any(isinstance(node, FORBIDDEN_NODES) for node in parsed.walk())
