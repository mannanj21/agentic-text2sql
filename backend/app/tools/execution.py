"""Read-only target database execution. This is an authorized target DB connector."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import psycopg

from app.config import get_settings
from app.database.crypto import CredentialCipher
from app.database.models import Connection
from app.guardrails.ssrf import resolve_target
from app.guardrails.types import ValidatedSQL

ErrorKind = Literal["syntax", "unknown_identifier", "timeout", "permission", "other"]


@dataclass(frozen=True)
class ExecutionResult:
    columns: list[str]
    rows: list[list[object]]
    row_count: int
    truncated: bool


class ExecutionError(RuntimeError):
    def __init__(self, kind: ErrorKind, message: str) -> None:
        super().__init__(message)
        self.kind = kind


def classify_error(exc: BaseException) -> ErrorKind:
    code = getattr(exc, "sqlstate", None)
    if code == "42601":
        return "syntax"
    if code in {"42703", "42P01"}:
        return "unknown_identifier"
    if code == "57014":
        return "timeout"
    if code == "42501":
        return "permission"
    return "other"


async def execute(connection: Connection, sql: ValidatedSQL) -> ExecutionResult:
    """Execute validated SQL in a read-only transaction with a bounded result set."""
    if not isinstance(sql, ValidatedSQL):
        raise TypeError("execute accepts only ValidatedSQL.")
    settings = get_settings()
    target = resolve_target(
        connection.host, connection.port, allow_private_hosts=settings.ALLOW_PRIVATE_HOSTS
    )
    password = CredentialCipher(settings.ENCRYPTION_KEY).decrypt(connection.encrypted_password)
    try:
        async with (
            await psycopg.AsyncConnection.connect(
                host=target.host,
                hostaddr=target.hostaddr,
                port=target.port,
                dbname=connection.database,
                user=connection.username,
                password=password,
                connect_timeout=5,
            ) as db,
            db.transaction(),
            db.cursor() as cursor,
        ):
            await cursor.execute("SET TRANSACTION READ ONLY")
            await cursor.execute(f"SET LOCAL statement_timeout = {settings.STATEMENT_TIMEOUT_MS}")
            await cursor.execute(f"SET LOCAL lock_timeout = {settings.LOCK_TIMEOUT_MS}")
            await cursor.execute(sql.sql)
            fetched = await cursor.fetchmany(settings.MAX_RESULT_ROWS + 1)
            columns = [column.name for column in cursor.description or []]
    except psycopg.Error as exc:
        raise ExecutionError(classify_error(exc), "Target database query failed.") from exc
    rows = [list(row) for row in fetched[: settings.MAX_RESULT_ROWS]]
    return ExecutionResult(columns, rows, len(rows), len(fetched) > settings.MAX_RESULT_ROWS)


async def explain(connection: Connection, sql: str) -> None:
    """Run EXPLAIN on unvalidated SQL to catch database-level errors safely.

    This is intended to be called by the validator before emitting ValidatedSQL.
    """
    settings = get_settings()
    target = resolve_target(
        connection.host, connection.port, allow_private_hosts=settings.ALLOW_PRIVATE_HOSTS
    )
    password = CredentialCipher(settings.ENCRYPTION_KEY).decrypt(connection.encrypted_password)
    try:
        async with (
            await psycopg.AsyncConnection.connect(
                host=target.host,
                hostaddr=target.hostaddr,
                port=target.port,
                dbname=connection.database,
                user=connection.username,
                password=password,
                connect_timeout=5,
            ) as db,
            db.transaction(),
            db.cursor() as cursor,
        ):
            await cursor.execute("SET TRANSACTION READ ONLY")
            await cursor.execute(f"SET LOCAL statement_timeout = {settings.STATEMENT_TIMEOUT_MS}")
            await cursor.execute(f"SET LOCAL lock_timeout = {settings.LOCK_TIMEOUT_MS}")
            await cursor.execute(f"EXPLAIN {sql}")
    except psycopg.Error as exc:
        raise ExecutionError(classify_error(exc), f"Target database EXPLAIN failed: {exc}") from exc
