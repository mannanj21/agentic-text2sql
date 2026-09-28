"""Stage 4 full structural and semantic SQL validation."""

from __future__ import annotations

import sqlglot
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlglot import exp
from sqlglot.errors import ParseError

from app.config import get_settings
from app.database.models import Connection, SchemaColumn, SchemaTable
from app.guardrails.types import ValidatedSQL, _validated_sql
from app.tools.execution import ExecutionError, explain


class ValidationError(ValueError):
    """A SQL statement failed deterministic validation."""

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind


# Nodes that are explicitly forbidden
FORBIDDEN_NODES = (
    exp.Command,
    exp.Into,
    exp.Lock,
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Drop,
    exp.Create,
    exp.Alter,
    exp.Commit,
    exp.Rollback,
    exp.Grant,
    exp.Merge,
    exp.TruncateTable,
    exp.Use,
)

# Functions that are explicitly forbidden
FORBIDDEN_FUNCTIONS = {
    "pg_sleep",
    "pg_read_file",
    "pg_read_binary_file",
    "pg_ls_dir",
    "pg_stat_file",
    "lo_import",
    "lo_export",
    "lo_unlink",
    "dblink_connect",
    "dblink_exec",
    "dblink_open",
    "dblink_fetch",
    "dblink_close",
    "dblink_get_connections",
    "dblink_disconnect",
    "set_config",
    "current_setting",
    "pg_terminate_backend",
    "pg_cancel_backend",
    "pg_advisory_lock",
    "pg_advisory_xact_lock",
    "pg_advisory_unlock",
    "txid_current",
    "pg_reload_conf",
    "query_to_xml",
    "copy_table",
}

# This deliberately small policy is enabled for evaluation and production by
# default.  PostgreSQL built-ins not listed here should be added deliberately,
# rather than becoming executable merely because sqlglot can parse them.
ALLOWED_FUNCTIONS = {
    "abs",
    "age",
    "array_agg",
    "avg",
    "ceil",
    "coalesce",
    "concat",
    "count",
    "current_date",
    "current_timestamp",
    "date_part",
    "date_trunc",
    "extract",
    "floor",
    "greatest",
    "least",
    "length",
    "lower",
    "max",
    "min",
    "now",
    "nullif",
    "power",
    "round",
    "sqrt",
    "string_agg",
    "sum",
    "substring",
    "to_char",
    "trim",
    "upper",
}

# Schemas that are explicitly forbidden
FORBIDDEN_SCHEMAS = {
    "pg_catalog",
    "information_schema",
    "pg_toast",
}


def _function_name(node: exp.Func) -> str:
    """Return a normalized function name, including a qualified call's leaf."""
    name = node.name.lower().split(".")[-1]
    return node.key.lower() if not name or name == "*" else name


def _check_ast(statement: exp.Expression) -> None:
    """Walk the AST and reject unauthorized nodes and functions."""
    for node in statement.walk():
        # Check node types
        if isinstance(node, FORBIDDEN_NODES):
            raise ValidationError(
                "unauthorized_node", f"Unauthorized SQL construct used: {node.key}"
            )

        # Check function names
        if isinstance(node, exp.Func):
            func_name = _function_name(node)
            if func_name in FORBIDDEN_FUNCTIONS:
                raise ValidationError("forbidden_function", f"Forbidden function used: {func_name}")
            if get_settings().FUNCTION_ALLOWLIST_MODE and func_name not in ALLOWED_FUNCTIONS:
                raise ValidationError(
                    "function_not_allowed", f"Function is not allowlisted: {func_name}"
                )


async def _check_schema_and_columns(
    statement: exp.Expression, connection: Connection, db: AsyncSession
) -> None:
    """Check table and column usage against the allowed schemas and sensitive column definitions."""
    allowed_schemas = set(connection.allowed_schemas or ["public"])

    # Extract all tables used
    for table_node in statement.find_all(exp.Table):
        schema = table_node.db.lower() if table_node.db else "public"
        name = table_node.name.lower()

        if schema in FORBIDDEN_SCHEMAS:
            raise ValidationError(
                "forbidden_schema", f"Access to restricted schema '{schema}' is forbidden."
            )

        if schema not in allowed_schemas:
            raise ValidationError(
                "forbidden_schema",
                f"Schema '{schema}' is not in the allowed schemas for this connection.",
            )

    # We want to catch sensitive columns.
    # We need to know what columns are sensitive for the tables in this connection.
    # Load all sensitive columns for this connection.
    sensitive_cols = (
        await db.execute(
            select(SchemaTable.schema, SchemaTable.name, SchemaColumn.name)
            .join(SchemaColumn, SchemaTable.id == SchemaColumn.table_id)
            .where(
                SchemaTable.connection_id == connection.id,
                # Sensitive if override is true, or (override null and is_sensitive true)
                SchemaColumn.sensitive_override.is_(True)
                | (SchemaColumn.sensitive_override.is_(None) & SchemaColumn.is_sensitive.is_(True)),
            )
        )
    ).all()

    sensitive_by_table: dict[tuple[str, str], set[str]] = {
        (col[0].lower(), col[1].lower()): set() for col in sensitive_cols
    }
    for schema, table, column in sensitive_cols:
        sensitive_by_table[(schema.lower(), table.lower())].add(column.lower())
    sensitive_tables: set[tuple[str, str]] = {
        (col[0].lower(), col[1].lower()) for col in sensitive_cols
    }

    # Alias resolution is intentionally conservative: an unqualified sensitive
    # name is rejected whenever it could refer to a sensitive source table.
    table_aliases: dict[str, tuple[str, str]] = {}
    for table_node in statement.find_all(exp.Table):
        schema = table_node.db.lower() if table_node.db else "public"
        table = table_node.name.lower()
        table_aliases[table] = (schema, table)
        if table_node.alias:
            table_aliases[table_node.alias.lower()] = (schema, table)

    # 1. Reject 'SELECT *' if any table in the query contains a sensitive column.
    has_star = False
    for _star_node in statement.find_all(exp.Star):
        has_star = True
        break

    if has_star:
        # If there's a star, and the query touches ANY sensitive table, we reject it.
        # This is the safest approach for SELECT *
        for table_node in statement.find_all(exp.Table):
            schema = table_node.db.lower() if table_node.db else "public"
            name = table_node.name.lower()
            if (schema, name) in sensitive_tables:
                raise ValidationError(
                    "sensitive_column",
                    f"SELECT * is not allowed on tables with sensitive columns ({schema}.{name}).",
                )

    # 2. Reject direct references to sensitive columns, including aliases,
    # predicates, ordering, and nested subqueries (all are exp.Column nodes).
    for column_node in statement.find_all(exp.Column):
        col_name = column_node.name.lower()
        qualifier = column_node.table.lower() if column_node.table else None
        source = table_aliases.get(qualifier) if qualifier else None
        if source and col_name in sensitive_by_table.get(source, set()):
            raise ValidationError(
                "sensitive_column", f"Access to sensitive column '{col_name}' is forbidden."
            )
        if not qualifier and any(col_name in columns for columns in sensitive_by_table.values()):
            raise ValidationError(
                "sensitive_column", f"Access to sensitive column '{col_name}' is forbidden."
            )


async def validate_sql(sql: str, connection: Connection, db: AsyncSession) -> ValidatedSQL:
    """Parse, structurally validate, semantically check, and EXPLAIN-check a SQL statement."""
    if not isinstance(sql, str) or not sql.strip():
        raise ValidationError("empty", "SQL must not be empty.")

    try:
        statements = sqlglot.parse(sql, read="postgres")
    except ParseError as exc:
        raise ValidationError("syntax", "SQL could not be parsed.") from exc

    if len(statements) != 1:
        raise ValidationError("multi_statement", "Exactly one SQL statement is required.")

    statement = statements[0]
    if not isinstance(statement, exp.Query):
        raise ValidationError(
            "statement_type", "Only SELECT or WITH SELECT statements are allowed."
        )

    # 1. AST Structural Checks
    _check_ast(statement)

    # 2. Semantic Checks (Schemas, Sensitive Columns)
    await _check_schema_and_columns(statement, connection, db)

    # 3. EXPLAIN Check (Defense in depth at the database level)
    # The normalized SQL string
    normalized_sql = statement.sql(dialect="postgres")

    try:
        await explain(connection, normalized_sql)
    except ExecutionError as exc:
        raise ValidationError(exc.kind, f"Database EXPLAIN check failed: {exc}") from exc

    return _validated_sql(normalized_sql)
