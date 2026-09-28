import pytest

from app.guardrails.sql_validator import ValidationError, validate_sql


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT id, first_name FROM customers",
        "WITH active AS (SELECT id FROM customers) SELECT id FROM active",
        "select 1;",
    ],
)
def test_accepts_select_statements(sql: str) -> None:
    validated = validate_sql(sql)
    assert validated.sql.upper().startswith(("SELECT", "WITH"))


@pytest.mark.parametrize(
    ("sql", "kind"),
    [
        ("", "empty"),
        ("   ", "empty"),
        ("SELECT 1; SELECT 2", "multi_statement"),
        ("INSERT INTO customers (first_name) VALUES ('A')", "statement_type"),
        ("UPDATE customers SET first_name = 'A'", "statement_type"),
        ("DELETE FROM customers", "statement_type"),
        ("SELECT FROM", "syntax"),
    ],
)
def test_rejects_non_readonly_or_invalid_sql(sql: str, kind: str) -> None:
    with pytest.raises(ValidationError) as raised:
        validate_sql(sql)
    assert raised.value.kind == kind
