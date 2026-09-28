import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.api import connections as connections_api
from app.api.main import app
from app.auth import create_access_token
from app.config import Settings
from app.database.core import AsyncSessionLocal
from app.database.crypto import CredentialCipher
from app.database.dialect import ConnectionSafetyReport
from app.database.models import Connection, User
from app.tools.introspection import TargetConnectionError

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def _client_for_user() -> AsyncClient:
    async with AsyncSessionLocal() as session:
        user = User(email=f"connection-{uuid.uuid4()}@example.com", password_hash="hash")
        session.add(user)
        await session.commit()
        await session.refresh(user)
    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        cookies={"session": create_access_token(user.id)},
    )


def _connection_payload(password: str = "target-password") -> dict[str, object]:  # noqa: S107
    return {
        "name": "Analytics",
        "host": "8.8.8.8",
        "port": 5432,
        "database": "analytics",
        "username": "readonly",
        "password": password,
        "schemas": ["public"],
    }


async def test_create_list_and_delete_connection_without_credential_leaks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    password = "target-password-never-returned"  # noqa: S105

    async def safe_target_check(**kwargs: object) -> ConnectionSafetyReport:
        encrypted = str(kwargs["encrypted_password"])
        key = str(kwargs["encryption_key"])
        assert password not in encrypted
        assert CredentialCipher(key).decrypt(encrypted) == password
        return ConnectionSafetyReport(reasons=(), default_transaction_read_only=True)

    monkeypatch.setattr(connections_api, "test_target_connection", safe_target_check)
    async with await _client_for_user() as client:
        created = await client.post("/connections", json=_connection_payload(password))
        assert created.status_code == 201
        assert password not in created.text
        assert "encrypted_password" not in created.text
        connection_id = created.json()["id"]

        listed = await client.get("/connections")
        assert listed.status_code == 200
        assert [item["id"] for item in listed.json()] == [connection_id]
        assert password not in listed.text

        async with AsyncSessionLocal() as session:
            stored = await session.scalar(select(Connection).where(Connection.id == connection_id))
            assert stored is not None
            assert password not in stored.encrypted_password

        deleted = await client.delete(f"/connections/{connection_id}")
        assert deleted.status_code == 204
        assert (await client.get("/connections")).json() == []


async def test_connection_creation_rejects_ssrf_unsafe_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    async def target_check_should_not_run(**_: object) -> ConnectionSafetyReport:
        nonlocal called
        called = True
        return ConnectionSafetyReport(reasons=(), default_transaction_read_only=True)

    monkeypatch.setattr(connections_api, "test_target_connection", target_check_should_not_run)
    payload = _connection_payload()
    payload["host"] = "127.0.0.1"
    async with await _client_for_user() as client:
        response = await client.post("/connections", json=payload)
    assert response.status_code == 400
    assert called is False


async def test_connection_creation_rejects_unsafe_role_with_setup_link(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def unsafe_target_check(**_: object) -> ConnectionSafetyReport:
        return ConnectionSafetyReport(
            reasons=("role has write privilege on table public.orders",),
            default_transaction_read_only=False,
        )

    monkeypatch.setattr(connections_api, "test_target_connection", unsafe_target_check)
    async with await _client_for_user() as client:
        response = await client.post("/connections", json=_connection_payload())
    assert response.status_code == 400
    assert response.json()["detail"]["readonly_role_setup"] == "/docs/readonly-role.sql"


async def test_connection_creation_reports_bad_target_credentials_without_leaking_password(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    password = "bad-target-password"  # noqa: S105

    async def failed_target_check(**_: object) -> ConnectionSafetyReport:
        raise TargetConnectionError("Unable to connect to target database.")

    monkeypatch.setattr(connections_api, "test_target_connection", failed_target_check)
    async with await _client_for_user() as client:
        response = await client.post("/connections", json=_connection_payload(password))
    assert response.status_code == 400
    assert password not in response.text


async def test_connection_resource_routes_hide_other_users_connections(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def safe_target_check(**_: object) -> ConnectionSafetyReport:
        return ConnectionSafetyReport(reasons=(), default_transaction_read_only=True)

    monkeypatch.setattr(connections_api, "test_target_connection", safe_target_check)
    async with await _client_for_user() as client_a, await _client_for_user() as client_b:
        created = await client_a.post("/connections", json=_connection_payload())
        connection_id = created.json()["id"]
        assert (await client_b.delete(f"/connections/{connection_id}")).status_code == 404
        assert (await client_b.post(f"/connections/{connection_id}/sync")).status_code == 404


async def test_connection_creation_checks_a_real_readonly_demo_role(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exercise the encrypted-password, pinned-host, and safety-check path together."""
    monkeypatch.setattr(
        connections_api,
        "get_settings",
        lambda: Settings(ALLOW_PRIVATE_HOSTS=True),
    )
    payload = _connection_payload("readonly_pass")
    payload.update(
        {
            "host": "127.0.0.1",
            "port": 5434,
            "database": "ecommerce",
            "username": "readonly_demo",
        }
    )
    async with await _client_for_user() as client:
        response = await client.post("/connections", json=payload)
    assert response.status_code == 201
