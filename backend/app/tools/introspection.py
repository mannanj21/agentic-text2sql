"""Target-database connection checks and schema introspection.

This is one of the two permitted modules for opening target database connections.
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import cast

from sqlalchemy import delete, select, text
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from app.config import get_settings
from app.database.crypto import CredentialCipher
from app.database.dialect import ConnectionSafetyReport, PostgresDialect
from app.database.models import (
    Connection,
    SchemaColumn,
    SchemaIndex,
    SchemaRelationship,
    SchemaTable,
)
from app.guardrails.ssrf import ResolvedTarget, resolve_target


class TargetConnectionError(ValueError):
    """A target database could not be contacted with the supplied credentials."""


class SchemaIntrospectionError(ValueError):
    """Target schema metadata could not be synchronized."""


SENSITIVE_COLUMN_TERMS = (
    "password",
    "passwd",
    "secret",
    "token",
    "ssn",
    "email",
    "phone",
    "card",
    "iban",
    "dob",
)


def is_sensitive_column(name: str, terms: Sequence[str] = SENSITIVE_COLUMN_TERMS) -> bool:
    """Return whether a column name needs a conservative sensitive-data default."""
    normalized = name.lower()
    return any(term.lower() in normalized for term in terms)


def _target_engine(
    *,
    target: ResolvedTarget,
    database: str,
    username: str,
    encrypted_password: str,
    encryption_key: str,
) -> AsyncEngine:
    password = CredentialCipher(encryption_key).decrypt(encrypted_password)
    return create_async_engine(
        URL.create("postgresql+psycopg", database=database, username=username),
        connect_args={
            "host": target.host,
            "hostaddr": target.hostaddr,
            "port": target.port,
            "password": password,
            "connect_timeout": 5,
        },
        pool_pre_ping=True,
    )


async def test_target_connection(
    *,
    target: ResolvedTarget,
    database: str,
    username: str,
    encrypted_password: str,
    encryption_key: str,
    schemas: list[str],
) -> ConnectionSafetyReport:
    """Connect through a previously validated IP and inspect the target role.

    The password is decrypted only in this target-connection module and is never
    included in an exception, response, or persisted object.
    """
    engine = _target_engine(
        target=target,
        database=database,
        username=username,
        encrypted_password=encrypted_password,
        encryption_key=encryption_key,
    )
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
            return await PostgresDialect().check_connection_safety(connection, schemas=schemas)
    except Exception as exc:
        raise TargetConnectionError("Unable to connect to target database.") from exc
    finally:
        await engine.dispose()


async def sync_schema_metadata(connection: Connection, db: AsyncSession) -> None:
    """Read target metadata and make the stored schema mirror it idempotently."""
    settings = get_settings()
    connection.status = "introspecting"
    connection.last_sync_error = None
    await db.commit()
    try:
        target = resolve_target(
            connection.host,
            connection.port,
            allow_private_hosts=settings.ALLOW_PRIVATE_HOSTS,
        )
        engine = _target_engine(
            target=target,
            database=connection.database,
            username=connection.username,
            encrypted_password=connection.encrypted_password,
            encryption_key=settings.ENCRYPTION_KEY.get_secret_value(),
        )
        try:
            metadata = await _read_target_metadata(engine, schemas=connection.allowed_schemas)
        finally:
            await engine.dispose()
        await _store_metadata(connection, db, metadata)
        connection.status = "ready"
        connection.last_sync_error = None
        connection.last_synced_at = datetime.now(UTC)
        await db.commit()
    except Exception as exc:
        await db.rollback()
        stored = await db.get(Connection, connection.id)
        if stored is not None:
            stored.status = "failed"
            stored.last_sync_error = "Schema synchronization failed."
            await db.commit()
        raise SchemaIntrospectionError("Schema synchronization failed.") from exc


async def _read_target_metadata(
    engine: AsyncEngine, *, schemas: list[str]
) -> dict[str, list[dict[str, object]]]:
    dialect = PostgresDialect()
    queries = dialect.introspection_queries()
    try:
        async with engine.connect() as target_connection:
            return {
                name: [
                    dict(row)
                    for row in (
                        await target_connection.execute(text(query), {"schemas": schemas})
                    ).mappings()
                ]
                for name, query in queries.items()
            }
    except Exception as exc:
        raise SchemaIntrospectionError("Schema synchronization failed.") from exc


async def _store_metadata(
    connection: Connection, db: AsyncSession, metadata: dict[str, list[dict[str, object]]]
) -> None:
    source_tables: dict[tuple[str, str], dict[str, object]] = {
        (str(row["schema"]), str(row["name"])): row for row in metadata["tables"]
    }
    stored_tables = (
        await db.scalars(select(SchemaTable).where(SchemaTable.connection_id == connection.id))
    ).all()
    for stored_table in stored_tables:
        if (stored_table.schema, stored_table.name) not in source_tables:
            await db.delete(stored_table)
    await db.flush()

    stored_tables_by_name = {(table.schema, table.name): table for table in stored_tables}
    table_by_name: dict[tuple[str, str], SchemaTable] = {}
    for table_key, row in source_tables.items():
        table: SchemaTable | None = stored_tables_by_name.get(table_key)
        if table is None:
            table = SchemaTable(connection_id=connection.id, schema=table_key[0], name=table_key[1])
            db.add(table)
        row_estimate = row["row_estimate"]
        table.row_estimate = (
            int(cast(int | str, row_estimate)) if row_estimate is not None else None
        )
        table_by_name[table_key] = table
    await db.flush()

    source_columns: dict[tuple[str, str, str], dict[str, object]] = {
        (str(row["schema"]), str(row["table_name"]), str(row["column_name"])): row
        for row in metadata["columns"]
    }
    stored_columns = (
        await db.scalars(
            select(SchemaColumn).join(SchemaTable).where(SchemaTable.connection_id == connection.id)
        )
    ).all()
    column_by_name = {(column.table_id, column.name): column for column in stored_columns}
    primary_keys: set[tuple[str, str, str]] = {
        (str(row["schema"]), str(row["table_name"]), str(row["column_name"]))
        for row in metadata["primary_keys"]
    }
    for stored_column in stored_columns:
        stored_table_key = next(
            (key for key, table in table_by_name.items() if table.id == stored_column.table_id),
            None,
        )
        column_exists = (
            stored_table_key is not None
            and (*stored_table_key, stored_column.name) in source_columns
        )
        if not column_exists:
            await db.delete(stored_column)
    await db.flush()

    for column_key, row in source_columns.items():
        table = table_by_name[(column_key[0], column_key[1])]
        column: SchemaColumn | None = column_by_name.get((table.id, column_key[2]))
        if column is None:
            column = SchemaColumn(
                table_id=table.id,
                name=column_key[2],
                data_type=str(row["data_type"]),
                is_pk=column_key in primary_keys,
                is_sensitive=is_sensitive_column(column_key[2]),
            )
            db.add(column)
        else:
            column.data_type = str(row["data_type"])
            column.is_pk = column_key in primary_keys
            if column.sensitive_override is None:
                column.is_sensitive = is_sensitive_column(column_key[2])
    await db.flush()

    await db.execute(
        delete(SchemaRelationship).where(SchemaRelationship.connection_id == connection.id)
    )
    all_columns = (
        await db.scalars(
            select(SchemaColumn).join(SchemaTable).where(SchemaTable.connection_id == connection.id)
        )
    ).all()
    table_ids = {table.id: (table.schema, table.name) for table in table_by_name.values()}
    column_ids = {
        (*table_ids[column.table_id], column.name): column.id
        for column in all_columns
        if column.table_id in table_ids
    }
    for foreign_key in metadata["foreign_keys"]:
        source = (
            str(foreign_key["from_schema"]),
            str(foreign_key["from_table"]),
            str(foreign_key["from_column"]),
        )
        target = (
            str(foreign_key["to_schema"]),
            str(foreign_key["to_table"]),
            str(foreign_key["to_column"]),
        )
        if source in column_ids and target in column_ids:
            db.add(
                SchemaRelationship(
                    connection_id=connection.id,
                    from_column_id=column_ids[source],
                    to_column_id=column_ids[target],
                )
            )

    source_indexes: dict[tuple[str, str, str], dict[str, object]] = {
        (str(row["schema"]), str(row["table_name"]), str(row["indexname"])): row
        for row in metadata["indexes"]
    }
    stored_indexes = (
        await db.scalars(
            select(SchemaIndex).join(SchemaTable).where(SchemaTable.connection_id == connection.id)
        )
    ).all()
    for stored_index in stored_indexes:
        stored_table_key = table_ids.get(stored_index.table_id)
        if stored_table_key is None or (*stored_table_key, stored_index.name) not in source_indexes:
            await db.delete(stored_index)
    await db.flush()

    indexes_by_name = {(index.table_id, index.name): index for index in stored_indexes}
    for index_key, row in source_indexes.items():
        table = table_by_name[(index_key[0], index_key[1])]
        index: SchemaIndex | None = indexes_by_name.get((table.id, index_key[2]))
        if index is None:
            db.add(
                SchemaIndex(
                    table_id=table.id,
                    name=index_key[2],
                    definition=str(row["indexdef"]),
                )
            )
        else:
            index.definition = str(row["indexdef"])
