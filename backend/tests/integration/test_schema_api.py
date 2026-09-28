import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.main import app
from app.auth import create_access_token
from app.database.core import AsyncSessionLocal
from app.database.models import Connection, SchemaColumn, SchemaTable, User
from app.tools.introspection import _store_metadata

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def _client_with_schema() -> tuple[AsyncClient, str, str, str]:
    async with AsyncSessionLocal() as db:
        user = User(email=f"schema-{uuid.uuid4()}@example.com", password_hash="hash")
        db.add(user)
        await db.flush()
        connection = Connection(
            user_id=user.id,
            name="Schema test",
            host="db.example.test",
            port=5432,
            database="analytics",
            username="readonly",
            encrypted_password="ciphertext",
        )
        db.add(connection)
        await db.flush()
        table = SchemaTable(
            connection_id=connection.id,
            schema="public",
            name="customers",
            description="Original description",
        )
        db.add(table)
        await db.flush()
        column = SchemaColumn(
            table_id=table.id,
            name="email",
            data_type="text",
            is_sensitive=True,
            description="Customer email",
        )
        db.add(column)
        await db.commit()
    client = AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        cookies={"session": create_access_token(user.id)},
    )
    return client, connection.id, table.id, column.id


async def _cleanup_connection(connection_id: str) -> None:
    async with AsyncSessionLocal() as db:
        connection = await db.get(Connection, connection_id)
        if connection is not None:
            await db.delete(connection)
            await db.commit()


async def test_schema_get_patch_and_resync_preserves_sensitive_override() -> None:
    client, connection_id, table_id, column_id = await _client_with_schema()
    try:
        schema = await client.get(f"/connections/{connection_id}/schema")
        assert schema.status_code == 200
        assert schema.json()["tables"][0]["columns"][0]["is_sensitive"] is True

        patched = await client.patch(
            f"/connections/{connection_id}/schema",
            json={
                "tables": [{"id": table_id, "description": "Edited table description"}],
                "columns": [{"id": column_id, "is_sensitive": False}],
            },
        )
        assert patched.status_code == 200
        assert patched.json()["tables"][0]["description"] == "Edited table description"
        assert patched.json()["tables"][0]["columns"][0]["is_sensitive"] is False

        async with AsyncSessionLocal() as db:
            connection = await db.get(Connection, connection_id)
            assert connection is not None
            await _store_metadata(
                connection,
                db,
                {
                    "tables": [{"schema": "public", "name": "customers", "row_estimate": 1}],
                    "columns": [
                        {
                            "schema": "public",
                            "table_name": "customers",
                            "column_name": "email",
                            "data_type": "text",
                        }
                    ],
                    "primary_keys": [],
                    "foreign_keys": [],
                    "indexes": [],
                },
            )
            await db.commit()
            column = await db.get(SchemaColumn, column_id)
            assert column is not None
            assert column.is_sensitive is False
    finally:
        await client.aclose()
        await _cleanup_connection(connection_id)


async def test_glossary_crud_and_validation() -> None:
    client, connection_id, _, _ = await _client_with_schema()
    try:
        invalid = await client.post(f"/connections/{connection_id}/glossary", json={"term": ""})
        assert invalid.status_code == 422

        created = await client.post(
            f"/connections/{connection_id}/glossary",
            json={"term": "customer", "definition": "A buyer."},
        )
        assert created.status_code == 201
        term_id = created.json()["id"]
        assert (await client.get(f"/connections/{connection_id}/glossary")).json() == [
            {"id": term_id, "term": "customer", "definition": "A buyer."}
        ]
        deleted = await client.delete(f"/connections/{connection_id}/glossary/{term_id}")
        assert deleted.status_code == 204
        assert (await client.get(f"/connections/{connection_id}/glossary")).json() == []
    finally:
        await client.aclose()
        await _cleanup_connection(connection_id)


async def test_schema_and_glossary_routes_hide_other_users_data() -> None:
    client_a, connection_id, _, _ = await _client_with_schema()
    client_b, connection_b_id, _, _ = await _client_with_schema()
    try:
        assert (await client_b.get(f"/connections/{connection_id}/schema")).status_code == 404
        patched = await client_b.patch(f"/connections/{connection_id}/schema", json={})
        assert patched.status_code == 404
        assert (await client_b.get(f"/connections/{connection_id}/glossary")).status_code == 404
        assert (
            await client_b.post(
                f"/connections/{connection_id}/glossary",
                json={"term": "customer", "definition": "A buyer."},
            )
        ).status_code == 404
    finally:
        await client_a.aclose()
        await client_b.aclose()
        await _cleanup_connection(connection_id)
        await _cleanup_connection(connection_b_id)
