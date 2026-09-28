import pytest

from app.database.dialect import Dialect, PostgresDialect


def test_postgres_dialect_conforms_to_the_dialect_contract() -> None:
    dialect: Dialect = PostgresDialect()
    assert dialect.sqlglot_dialect == "postgres"


def test_postgres_introspection_queries_cover_required_catalog_data() -> None:
    queries = PostgresDialect().introspection_queries()
    assert set(queries) == {"tables", "columns", "primary_keys", "foreign_keys", "indexes"}
    assert "pg_class" in queries["tables"]
    assert "information_schema.columns" in queries["columns"]
    assert "PRIMARY KEY" in queries["primary_keys"]
    assert "FOREIGN KEY" in queries["foreign_keys"]
    assert "pg_indexes" in queries["indexes"]
    assert all("%(schemas)s" in query for query in queries.values())


def test_postgres_read_only_session_settings_are_parameterized() -> None:
    settings = PostgresDialect().read_only_session_settings(
        statement_timeout_ms=30_000,
        lock_timeout_ms=5_000,
    )
    assert settings.statements == (
        ("BEGIN READ ONLY", ()),
        ("SET LOCAL statement_timeout = %s", (30_000,)),
        ("SET LOCAL lock_timeout = %s", (5_000,)),
    )


@pytest.mark.parametrize("statement_timeout_ms,lock_timeout_ms", [(0, 1), (1, 0), (-1, 1)])
def test_postgres_read_only_session_settings_reject_non_positive_timeouts(
    statement_timeout_ms: int, lock_timeout_ms: int
) -> None:
    with pytest.raises(ValueError, match="positive"):
        PostgresDialect().read_only_session_settings(
            statement_timeout_ms=statement_timeout_ms,
            lock_timeout_ms=lock_timeout_ms,
        )


def test_postgres_explain_and_safety_queries() -> None:
    dialect = PostgresDialect()
    assert dialect.explain_query("SELECT 1") == "EXPLAIN (FORMAT JSON) SELECT 1"

    safety = dialect.safety_check_queries()
    assert set(safety) == {
        "role_attributes",
        "table_write_privileges",
        "schema_create_privileges",
        "privileged_role_memberships",
        "default_transaction_read_only",
    }
    assert "rolsuper" in safety["role_attributes"]
    assert "has_table_privilege" in safety["table_write_privileges"]
    assert "has_schema_privilege" in safety["schema_create_privileges"]
    assert "pg_auth_members" in safety["privileged_role_memberships"]
    assert safety["default_transaction_read_only"] == "SHOW default_transaction_read_only"
