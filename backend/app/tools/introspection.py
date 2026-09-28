"""Target-database connection checks and, later, schema introspection.

This is one of the two permitted modules for opening target database connections.
"""

from sqlalchemy import text
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import create_async_engine

from app.database.crypto import CredentialCipher
from app.database.dialect import ConnectionSafetyReport, PostgresDialect
from app.guardrails.ssrf import ResolvedTarget


class TargetConnectionError(ValueError):
    """A target database could not be contacted with the supplied credentials."""


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
    password = CredentialCipher(encryption_key).decrypt(encrypted_password)
    engine = create_async_engine(
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
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
            return await PostgresDialect().check_connection_safety(connection, schemas=schemas)
    except Exception as exc:
        raise TargetConnectionError("Unable to connect to target database.") from exc
    finally:
        await engine.dispose()
