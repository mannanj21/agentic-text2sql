import pytest

from app.guardrails.types import ValidatedSQL, _validated_sql
from app.tools.execution import classify_error


def test_validated_sql_is_not_publicly_constructible() -> None:
    with pytest.raises(TypeError):
        ValidatedSQL("SELECT 1")
    assert _validated_sql("SELECT 1").sql == "SELECT 1"


@pytest.mark.parametrize(
    ("code", "kind"),
    [
        ("42601", "syntax"),
        ("42703", "unknown_identifier"),
        ("42P01", "unknown_identifier"),
        ("57014", "timeout"),
        ("42501", "permission"),
        ("XX000", "other"),
    ],
)
def test_error_classification(code: str, kind: str) -> None:
    error = type("DatabaseError", (Exception,), {"sqlstate": code})()
    assert classify_error(error) == kind
