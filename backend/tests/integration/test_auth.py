"""Integration tests for /auth routes: register, login, logout."""

import asyncio
import sys
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.main import app
from app.database.core import AsyncSessionLocal

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

BASE = "http://test"


def unique_email(prefix: str = "user") -> str:
    """Generate a unique email for each test to avoid conflicts across runs."""
    return f"{prefix}-{uuid.uuid4().hex[:8]}@example.com"


async def get_client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url=BASE)


# --- Helpers ---


async def register_user(client: AsyncClient, email: str, password: str):
    return await client.post("/auth/register", json={"email": email, "password": password})


async def login_user(client: AsyncClient, email: str, password: str):
    return await client.post("/auth/login", json={"email": email, "password": password})


# --- Tests ---


async def test_register_success() -> None:
    async with await get_client() as client:
        resp = await register_user(client, unique_email("newuser"), "securepassword1")
        assert resp.status_code == 200
        data = resp.json()
        assert "id" in data
        assert "message" in data


async def test_register_duplicate_email() -> None:
    email = unique_email("dupe")
    async with await get_client() as client:
        resp1 = await register_user(client, email, "securepassword1")
        assert resp1.status_code == 200
        # Second attempt with same email (domain casing differs — still same after normalization)
        same_email_diff_domain_case = email.replace("@example.com", "@EXAMPLE.COM")
        resp = await register_user(client, same_email_diff_domain_case, "anotherpassword")
        assert resp.status_code == 400
        # Generic message — no user enumeration
        assert resp.json()["detail"] == "Invalid email or password"


async def test_register_invalid_email() -> None:
    async with await get_client() as client:
        resp = await register_user(client, "not-an-email", "securepassword1")
        assert resp.status_code == 400


async def test_register_password_too_short() -> None:
    async with await get_client() as client:
        resp = await register_user(client, unique_email("short"), "short")
        assert resp.status_code == 400
        assert "8" in resp.json()["detail"]


async def test_login_success_and_sets_cookie() -> None:
    email = unique_email("logintest")
    async with await get_client() as client:
        await register_user(client, email, "securepassword1")
        resp = await login_user(client, email, "securepassword1")
        assert resp.status_code == 200
        assert "session" in resp.cookies


async def test_login_wrong_password() -> None:
    email = unique_email("wrongpw")
    async with await get_client() as client:
        await register_user(client, email, "correctpassword1")
        resp = await login_user(client, email, "wrongpassword!!")
        assert resp.status_code == 401
        assert resp.json()["detail"] == "Invalid credentials"


async def test_login_nonexistent_user() -> None:
    async with await get_client() as client:
        resp = await login_user(client, "nobody@example.com", "doesnotmatter1")
        assert resp.status_code == 401
        # Same message as wrong password — no user enumeration
        assert resp.json()["detail"] == "Invalid credentials"


async def test_logout_clears_cookie() -> None:
    email = unique_email("logoutme")
    async with await get_client() as client:
        await register_user(client, email, "securepassword1")
        await login_user(client, email, "securepassword1")
        resp = await client.post("/auth/logout")
        assert resp.status_code == 200
        # After logout the cookie's max-age should be 0 or the cookie is deleted
        assert "session" not in resp.cookies or resp.cookies["session"] == ""


async def test_password_never_in_response() -> None:
    email = unique_email("noleak")
    async with await get_client() as client:
        resp = await register_user(client, email, "supersecretpassword1")
        assert "supersecretpassword1" not in resp.text
        assert "password_hash" not in resp.text


async def test_password_never_in_db_plaintext() -> None:
    """Verify the password is stored hashed, never as plaintext."""
    from sqlalchemy import text

    email = unique_email("dbcheck")
    async with await get_client() as client:
        await register_user(client, email, "checkthishash1!")

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("SELECT password_hash FROM users WHERE email = :email"),
            {"email": email},
        )
        row = result.fetchone()
        if row:
            assert "checkthishash1!" not in row[0]
            assert row[0].startswith("$argon2")
