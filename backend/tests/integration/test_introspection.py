import uuid

import pytest
from sqlalchemy import select

from app.config import Settings
from app.database.core import AsyncSessionLocal
from app.database.crypto import CredentialCipher
from app.database.models import (
    Connection,
    GlossaryTerm,
    SchemaColumn,
    SchemaIndex,
    SchemaRelationship,
    SchemaTable,
    User,
)
from app.tools import introspection

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def _connection_for_demo(database: str, port: int) -> tuple[Connection, str]:
    settings = Settings(ALLOW_PRIVATE_HOSTS=True)
    async with AsyncSessionLocal() as db:
        user = User(email=f"introspection-{uuid.uuid4()}@example.com", password_hash="hash")
        db.add(user)
        await db.flush()
        connection = Connection(
            user_id=user.id,
            name=f"{database} metadata",
            host="127.0.0.1",
            port=port,
            database=database,
            username="readonly_demo",
            encrypted_password=CredentialCipher(settings.ENCRYPTION_KEY).encrypt("readonly_pass"),
            allowed_schemas=["public"],
        )
        db.add(connection)
        await db.commit()
        return connection, connection.id


@pytest.mark.parametrize(
    ("database", "port", "expected_tables"),
    [
        ("ecommerce", 5434, {"customers", "orders", "order_items"}),
        ("pagila", 5435, {"actor", "film", "rental"}),
    ],
)
async def test_sync_reads_demo_metadata(
    monkeypatch: pytest.MonkeyPatch,
    database: str,
    port: int,
    expected_tables: set[str],
) -> None:
    monkeypatch.setattr(introspection, "get_settings", lambda: Settings(ALLOW_PRIVATE_HOSTS=True))
    _, connection_id = await _connection_for_demo(database, port)
    try:
        async with AsyncSessionLocal() as db:
            connection = await db.get(Connection, connection_id)
            assert connection is not None
            await introspection.sync_schema_metadata(connection, db)

            tables = (
                await db.scalars(
                    select(SchemaTable).where(SchemaTable.connection_id == connection_id)
                )
            ).all()
            relationships = (
                await db.scalars(
                    select(SchemaRelationship).where(
                        SchemaRelationship.connection_id == connection_id
                    )
                )
            ).all()
            indexes = (
                await db.scalars(
                    select(SchemaIndex)
                    .join(SchemaTable)
                    .where(SchemaTable.connection_id == connection_id)
                )
            ).all()

            assert expected_tables <= {table.name for table in tables}
            assert relationships
            assert indexes
            assert connection.status == "ready"
            assert connection.last_synced_at is not None
    finally:
        async with AsyncSessionLocal() as db:
            connection = await db.get(Connection, connection_id)
            if connection is not None:
                await db.delete(connection)
                await db.commit()


async def test_resync_preserves_edits_and_applies_sensitive_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(introspection, "get_settings", lambda: Settings(ALLOW_PRIVATE_HOSTS=True))
    _, connection_id = await _connection_for_demo("ecommerce", 5434)
    try:
        async with AsyncSessionLocal() as db:
            connection = await db.get(Connection, connection_id)
            assert connection is not None
            await introspection.sync_schema_metadata(connection, db)
            customers = await db.scalar(
                select(SchemaTable).where(
                    SchemaTable.connection_id == connection_id, SchemaTable.name == "customers"
                )
            )
            assert customers is not None
            customers.description = "Customer master data"
            email = await db.scalar(
                select(SchemaColumn).where(
                    SchemaColumn.table_id == customers.id, SchemaColumn.name == "email"
                )
            )
            assert email is not None
            email.sensitive_override = False
            email.is_sensitive = False
            db.add(
                GlossaryTerm(
                    connection_id=connection_id,
                    term="customer",
                    definition="A buyer.",
                )
            )
            await db.commit()

            await introspection.sync_schema_metadata(connection, db)
            await db.refresh(customers)
            await db.refresh(email)
            glossary = await db.scalar(
                select(GlossaryTerm).where(GlossaryTerm.connection_id == connection_id)
            )
            assert customers.description == "Customer master data"
            assert email.is_sensitive is False
            assert glossary is not None
    finally:
        async with AsyncSessionLocal() as db:
            connection = await db.get(Connection, connection_id)
            if connection is not None:
                await db.delete(connection)
                await db.commit()


async def test_sync_failure_records_safe_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(introspection, "get_settings", lambda: Settings(ALLOW_PRIVATE_HOSTS=True))
    _, connection_id = await _connection_for_demo("ecommerce", 59999)
    try:
        async with AsyncSessionLocal() as db:
            connection = await db.get(Connection, connection_id)
            assert connection is not None
            with pytest.raises(introspection.SchemaIntrospectionError):
                await introspection.sync_schema_metadata(connection, db)
            await db.refresh(connection)
            assert connection.status == "failed"
            assert connection.last_sync_error == "Schema synchronization failed."
    finally:
        async with AsyncSessionLocal() as db:
            connection = await db.get(Connection, connection_id)
            if connection is not None:
                await db.delete(connection)
                await db.commit()
