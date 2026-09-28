import os

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from app.database.dialect import PostgresDialect


def _demo_url(role: str, password: str) -> str:
    host = os.environ.get("DEMO_HOST", "localhost")
    return f"postgresql+psycopg://{role}:{password}@{host}:5434/ecommerce"


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.parametrize(
    ("role", "password", "expected_reason"),
    [
        ("readonly_demo", "readonly_pass", None),
        ("writer_demo", "writer_pass", "role has write privilege on table public.categories"),
        ("postgres", "changeme", "role is a superuser"),
    ],
)
async def test_postgres_connection_safety_check(
    role: str, password: str, expected_reason: str | None
) -> None:
    engine = create_async_engine(_demo_url(role, password))
    try:
        async with engine.connect() as connection:
            report = await PostgresDialect().check_connection_safety(connection, schemas=["public"])
    finally:
        await engine.dispose()

    if expected_reason is None:
        assert report.is_safe
        assert report.default_transaction_read_only is True
    else:
        assert not report.is_safe
        assert expected_reason in report.reasons
