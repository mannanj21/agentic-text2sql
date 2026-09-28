import hashlib
import importlib.util
import os
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


# Pytest fixture for db engines
@pytest.fixture(scope="module")
def ecommerce_url():
    # Use environment variables if in CI, else default localhost mapping
    host = os.environ.get("DEMO_HOST", "localhost")
    return f"postgresql+psycopg://postgres:changeme@{host}:5434/ecommerce"


@pytest.fixture(scope="module")
def pagila_url():
    host = os.environ.get("DEMO_HOST", "localhost")
    return f"postgresql+psycopg://postgres:changeme@{host}:5435/pagila"


@pytest.fixture(scope="module")
def ecommerce_readonly_url():
    host = os.environ.get("DEMO_HOST", "localhost")
    return f"postgresql+psycopg://readonly_demo:readonly_pass@{host}:5434/ecommerce"


@pytest.fixture(scope="module")
def ecommerce_writer_url():
    host = os.environ.get("DEMO_HOST", "localhost")
    return f"postgresql+psycopg://writer_demo:writer_pass@{host}:5434/ecommerce"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_ecommerce_row_counts(ecommerce_url: str):
    """Verify that ecommerce seed data generated rows > thresholds."""
    engine = create_async_engine(ecommerce_url)
    async with engine.connect() as conn:
        users = (await conn.execute(text("SELECT count(*) FROM customers"))).scalar()
        assert users >= 50
        products = (await conn.execute(text("SELECT count(*) FROM products"))).scalar()
        assert products >= 20
        orders = (await conn.execute(text("SELECT count(*) FROM orders"))).scalar()
        assert orders >= 200
    await engine.dispose()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_pagila_row_counts(pagila_url: str):
    """Verify that pagila seed data loaded correctly."""
    engine = create_async_engine(pagila_url)
    async with engine.connect() as conn:
        actors = (await conn.execute(text("SELECT count(*) FROM actor"))).scalar()
        assert actors > 100
        films = (await conn.execute(text("SELECT count(*) FROM film"))).scalar()
        assert films > 500
    await engine.dispose()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_readonly_role_permissions(
    ecommerce_readonly_url: str, ecommerce_writer_url: str
) -> None:
    """The safety-check role can read but cannot opt out of read-only safeguards."""
    ro_engine = create_async_engine(ecommerce_readonly_url)
    async with ro_engine.connect() as conn:
        can_select = (
            await conn.execute(
                text("SELECT has_table_privilege('readonly_demo', 'customers', 'SELECT')")
            )
        ).scalar()
        assert can_select is True
        can_insert = (
            await conn.execute(
                text("SELECT has_table_privilege('readonly_demo', 'customers', 'INSERT')")
            )
        ).scalar()
        assert can_insert is False
        read_only_setting = (
            await conn.execute(text("SHOW default_transaction_read_only"))
        ).scalar()
        assert read_only_setting == "on"
        await conn.execute(text("SET default_transaction_read_only = off"))
        assert (await conn.execute(text("SHOW default_transaction_read_only"))).scalar() == "off"
        await conn.commit()
        with pytest.raises(Exception) as excinfo:
            await conn.execute(text("INSERT INTO categories (name) VALUES ('Hacked')"))
        assert "permission denied" in str(excinfo.value)
        await conn.rollback()
        with pytest.raises(Exception, match="permission denied for schema public"):
            await conn.execute(text("CREATE TABLE not_allowed (id integer)"))
    await ro_engine.dispose()

    writer_engine = create_async_engine(ecommerce_writer_url)
    async with writer_engine.connect() as conn:
        can_insert_writer = (
            await conn.execute(
                text("SELECT has_table_privilege('writer_demo', 'customers', 'INSERT')")
            )
        ).scalar()
        assert can_insert_writer is True
    await writer_engine.dispose()


def test_ecommerce_generator_is_deterministic(tmp_path: Path) -> None:
    """Two fresh generator runs produce byte-identical seed SQL."""
    generator = Path(__file__).parents[3] / "seeds" / "ecommerce" / "generate.py"
    spec = importlib.util.spec_from_file_location("ecommerce_generator", generator)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    first = tmp_path / "first"
    second = tmp_path / "second"
    for output_dir in (first, second):
        module.generate_ecommerce(output_dir)
    assert (
        hashlib.sha256((first / "02_data.sql").read_bytes()).digest()
        == hashlib.sha256((second / "02_data.sql").read_bytes()).digest()
    )
