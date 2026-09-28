"""Database-dialect contract used by target-database tools.

Only PostgreSQL is supported today.  Keeping its target-database SQL here makes
the eventual addition of another dialect explicit rather than scattered across
introspection, safety checks, and execution.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection


@dataclass(frozen=True)
class SessionSettings:
    """Statements and bind values required for a read-only target DB session."""

    statements: Sequence[tuple[str, tuple[int, ...]]]


@dataclass(frozen=True)
class ConnectionSafetyReport:
    """Structured outcome of a target database role safety inspection."""

    reasons: tuple[str, ...]
    default_transaction_read_only: bool

    @property
    def is_safe(self) -> bool:
        return not self.reasons


class Dialect(Protocol):
    """SQL and settings that the target-database tools require from a dialect."""

    sqlglot_dialect: str

    def introspection_queries(self) -> Mapping[str, str]: ...

    def read_only_session_settings(
        self, *, statement_timeout_ms: int, lock_timeout_ms: int
    ) -> SessionSettings: ...

    def explain_query(self, sql: str) -> str: ...

    def safety_check_queries(self) -> Mapping[str, str]: ...

    async def check_connection_safety(
        self, connection: AsyncConnection, *, schemas: Sequence[str]
    ) -> ConnectionSafetyReport: ...


@dataclass(frozen=True)
class PostgresDialect:
    """PostgreSQL implementation of the supported target-database operations."""

    sqlglot_dialect: str = "postgres"

    def introspection_queries(self) -> Mapping[str, str]:
        return {
            "tables": """
                SELECT n.nspname AS schema, c.relname AS name, c.reltuples::bigint AS row_estimate
                FROM pg_class AS c
                JOIN pg_namespace AS n ON n.oid = c.relnamespace
                WHERE c.relkind IN ('r', 'p', 'v', 'm')
                  AND n.nspname = ANY(:schemas)
                ORDER BY n.nspname, c.relname
            """,
            "columns": """
                SELECT table_schema AS schema, table_name, column_name, data_type,
                       udt_name, ordinal_position, is_nullable
                FROM information_schema.columns
                WHERE table_schema = ANY(:schemas)
                ORDER BY table_schema, table_name, ordinal_position
            """,
            "primary_keys": """
                SELECT tc.table_schema AS schema, tc.table_name, kcu.column_name,
                       kcu.ordinal_position
                FROM information_schema.table_constraints AS tc
                JOIN information_schema.key_column_usage AS kcu
                  ON tc.constraint_name = kcu.constraint_name
                 AND tc.table_schema = kcu.table_schema
                WHERE tc.constraint_type = 'PRIMARY KEY'
                  AND tc.table_schema = ANY(:schemas)
                ORDER BY tc.table_schema, tc.table_name, kcu.ordinal_position
            """,
            "foreign_keys": """
                SELECT tc.table_schema AS from_schema, tc.table_name AS from_table,
                       kcu.column_name AS from_column,
                       ccu.table_schema AS to_schema, ccu.table_name AS to_table,
                       ccu.column_name AS to_column
                FROM information_schema.table_constraints AS tc
                JOIN information_schema.key_column_usage AS kcu
                  ON tc.constraint_name = kcu.constraint_name
                 AND tc.table_schema = kcu.table_schema
                JOIN information_schema.constraint_column_usage AS ccu
                  ON ccu.constraint_name = tc.constraint_name
                 AND ccu.table_schema = tc.table_schema
                WHERE tc.constraint_type = 'FOREIGN KEY'
                  AND tc.table_schema = ANY(:schemas)
            """,
            "indexes": """
                SELECT schemaname AS schema, tablename AS table_name, indexname,
                       indexdef
                FROM pg_indexes
                WHERE schemaname = ANY(:schemas)
                ORDER BY schemaname, tablename, indexname
            """,
        }

    def read_only_session_settings(
        self, *, statement_timeout_ms: int, lock_timeout_ms: int
    ) -> SessionSettings:
        if statement_timeout_ms <= 0 or lock_timeout_ms <= 0:
            raise ValueError("Target database timeouts must be positive.")
        return SessionSettings(
            statements=(
                ("BEGIN READ ONLY", ()),
                ("SET LOCAL statement_timeout = %s", (statement_timeout_ms,)),
                ("SET LOCAL lock_timeout = %s", (lock_timeout_ms,)),
            )
        )

    def explain_query(self, sql: str) -> str:
        return f"EXPLAIN (FORMAT JSON) {sql}"

    def safety_check_queries(self) -> Mapping[str, str]:
        return {
            "role_attributes": """
                SELECT rolsuper, rolcreatedb, rolcreaterole
                FROM pg_roles
                WHERE rolname = current_user
            """,
            "table_write_privileges": """
                SELECT n.nspname AS schema, c.relname AS table_name
                FROM pg_class AS c
                JOIN pg_namespace AS n ON n.oid = c.relnamespace
                WHERE c.relkind IN ('r', 'p', 'v', 'm')
                  AND n.nspname = ANY(:schemas)
                  AND has_table_privilege(
                      current_user, c.oid, 'INSERT, UPDATE, DELETE, TRUNCATE'
                  )
            """,
            "schema_create_privileges": """
                SELECT nspname AS schema
                FROM pg_namespace
                WHERE nspname = ANY(:schemas)
                  AND has_schema_privilege(current_user, oid, 'CREATE')
            """,
            "privileged_role_memberships": """
                SELECT parent.rolname AS role_name
                FROM pg_auth_members AS membership
                JOIN pg_roles AS member ON member.oid = membership.member
                JOIN pg_roles AS parent ON parent.oid = membership.roleid
                WHERE member.rolname = current_user
                  AND (parent.rolsuper OR parent.rolcreatedb OR parent.rolcreaterole)
            """,
            "default_transaction_read_only": "SHOW default_transaction_read_only",
        }

    async def check_connection_safety(
        self, connection: AsyncConnection, *, schemas: Sequence[str]
    ) -> ConnectionSafetyReport:
        """Inspect the connected role and report whether it is safe to use.

        This method consumes an existing connection; it never creates a target
        connection itself, preserving the target-connection boundary.
        """
        if not schemas:
            raise ValueError("At least one allowed schema is required for a safety check.")
        queries = self.safety_check_queries()
        role = (await connection.execute(text(queries["role_attributes"]))).mappings().one()
        write_tables = (
            (
                await connection.execute(
                    text(queries["table_write_privileges"]), {"schemas": list(schemas)}
                )
            )
            .mappings()
            .all()
        )
        create_schemas = (
            (
                await connection.execute(
                    text(queries["schema_create_privileges"]), {"schemas": list(schemas)}
                )
            )
            .mappings()
            .all()
        )
        memberships = (
            (await connection.execute(text(queries["privileged_role_memberships"])))
            .mappings()
            .all()
        )
        read_only = str(
            (await connection.execute(text(queries["default_transaction_read_only"]))).scalar_one()
        )
        return assess_connection_safety(
            is_superuser=bool(role["rolsuper"]),
            can_create_database=bool(role["rolcreatedb"]),
            can_create_role=bool(role["rolcreaterole"]),
            write_tables=[f"{row['schema']}.{row['table_name']}" for row in write_tables],
            create_schemas=[str(row["schema"]) for row in create_schemas],
            privileged_roles=[str(row["role_name"]) for row in memberships],
            default_transaction_read_only=read_only.lower() == "on",
        )


def assess_connection_safety(
    *,
    is_superuser: bool,
    can_create_database: bool,
    can_create_role: bool,
    write_tables: Sequence[str],
    create_schemas: Sequence[str],
    privileged_roles: Sequence[str],
    default_transaction_read_only: bool,
) -> ConnectionSafetyReport:
    """Build a deterministic safety report from PostgreSQL catalog facts."""
    reasons: list[str] = []
    if is_superuser:
        reasons.append("role is a superuser")
    if can_create_database:
        reasons.append("role can create databases")
    if can_create_role:
        reasons.append("role can create roles")
    reasons.extend(f"role has write privilege on table {table}" for table in sorted(write_tables))
    reasons.extend(f"role can CREATE in schema {schema}" for schema in sorted(create_schemas))
    reasons.extend(
        f"role is a member of privileged role {role}" for role in sorted(privileged_roles)
    )
    return ConnectionSafetyReport(
        reasons=tuple(reasons),
        default_transaction_read_only=default_transaction_read_only,
    )
