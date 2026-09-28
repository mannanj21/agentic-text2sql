import pytest

from app.tools.introspection import SENSITIVE_COLUMN_TERMS, is_sensitive_column


@pytest.mark.parametrize(
    "column_name, expected",
    [
        ("password_hash", True),
        ("customer_email", True),
        ("billing_phone_number", True),
        ("date_of_birth", False),
        ("order_total", False),
        ("customer_id", False),
    ],
)
def test_sensitive_column_heuristic(column_name: str, expected: bool) -> None:
    assert is_sensitive_column(column_name) is expected


def test_sensitive_column_heuristic_accepts_configured_terms() -> None:
    assert is_sensitive_column("employee_number", terms=("employee",))
    assert not is_sensitive_column("employee_number", terms=SENSITIVE_COLUMN_TERMS)
