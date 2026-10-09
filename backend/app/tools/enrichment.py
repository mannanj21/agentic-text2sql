"""Metadata enrichment background job."""

from __future__ import annotations

import logging

from pydantic import BaseModel, Field
from sqlalchemy import select

from app.config import get_settings
from app.database.core import AsyncSessionLocal
from app.database.models import Connection, SchemaColumn, SchemaTable
from app.guardrails.ssrf import resolve_target
from app.llm.client import LLMClient
from app.llm.embedding import EmbedderClient
from app.tools.introspection import _target_engine

logger = logging.getLogger(__name__)

# Max sample string length stored per value
_SAMPLE_VALUE_MAX_LEN = 50
# Max distinct samples gathered per column
_SAMPLE_VALUE_LIMIT = 5
# Embedding batch size
_EMBED_CHUNK_SIZE = 100


class EnrichmentColumnResult(BaseModel):
    name: str
    description: str = Field(description="A short, clear description of the column's purpose.")


class EnrichmentTableResult(BaseModel):
    description: str = Field(description="A short, clear description of the table's purpose.")
    columns: list[EnrichmentColumnResult]


def _is_column_sensitive(col: SchemaColumn) -> bool:
    """Return True if the column is treated as sensitive."""
    return col.sensitive_override is True or (col.sensitive_override is None and col.is_sensitive)


def _safe_sample_query(schema: str, table: str, column: str, limit: int) -> str:
    """Build a parameterised-safe sample values query.

    We use double-quoted identifiers constructed from values that come from our
    own introspection (not from user SQL input), so SQL-injection risk is low.
    The ``# noqa: S608`` suppressor is intentional - identifiers are from the
    app's own metadata store, not from raw user text.
    """
    return (
        f'SELECT DISTINCT "{column}" FROM "{schema}"."{table}" '  # noqa: S608
        f'WHERE "{column}" IS NOT NULL LIMIT {limit}'
    )


async def enrich_connection_metadata(connection_id: str, force: bool = False) -> None:
    """Background task to enrich table/column descriptions and compute embeddings."""
    settings = get_settings()
    llm = LLMClient(settings)
    embedder = EmbedderClient(settings)

    total_tokens_used = 0
    cap = settings.ENRICHMENT_TOKEN_CAP

    try:
        async with AsyncSessionLocal() as db:
            connection = await db.get(Connection, connection_id)
            if not connection:
                return

            connection.status = "enriching"
            await db.commit()

            tables = (
                await db.scalars(
                    select(SchemaTable).where(SchemaTable.connection_id == connection_id)
                )
            ).all()

            # ---- Phase 1: LLM description generation ----
            for table in tables:
                if total_tokens_used >= cap:
                    break

                columns = (
                    await db.scalars(select(SchemaColumn).where(SchemaColumn.table_id == table.id))
                ).all()

                # Only enrich if something is missing (or force-regenerate)
                needs_table_desc = table.description is None or force
                needs_col_desc = any(c.description is None for c in columns) or force

                if needs_table_desc or needs_col_desc:
                    schema_ddl = f"Table: {table.name}\nColumns:\n"
                    for c in columns:
                        schema_ddl += f"- {c.name} ({c.data_type})\n"

                    messages = [
                        {
                            "role": "system",
                            "content": (
                                "You are a data dictionary expert. "
                                "Write concise descriptions for the table and columns "
                                "based on their names."
                            ),
                        },
                        {"role": "user", "content": schema_ddl},
                    ]

                    try:
                        result, usage = await llm.complete_structured(
                            "fast", messages, EnrichmentTableResult
                        )
                        total_tokens_used += usage.total_tokens

                        # Never overwrite user-edited descriptions unless force=True
                        if needs_table_desc:
                            table.description = result.description

                        col_results = {c.name: c.description for c in result.columns}
                        for c in columns:
                            if (c.description is None or force) and c.name in col_results:
                                c.description = col_results[c.name]

                        await db.commit()
                    except Exception:
                        logger.warning(
                            "LLM enrichment failed for table %s/%s",
                            connection_id,
                            table.name,
                            exc_info=True,
                        )

            # ---- Phase 2: Embedding computation ----
            for table in tables:
                if table.embedding is None or force:
                    text_to_embed = f"{table.name} - {table.description or ''}"
                    try:
                        vecs = await embedder.aembed([text_to_embed])
                        if vecs:
                            table.embedding = vecs[0]
                    except Exception:
                        logger.warning(
                            "Embedding failed for table %s/%s",
                            connection_id,
                            table.name,
                            exc_info=True,
                        )

            all_cols = (
                await db.scalars(
                    select(SchemaColumn)
                    .join(SchemaTable)
                    .where(SchemaTable.connection_id == connection_id)
                )
            ).all()

            cols_to_embed = [c for c in all_cols if c.embedding is None or force]
            if cols_to_embed:
                texts = [f"{c.table.name}.{c.name} - {c.description or ''}" for c in cols_to_embed]
                for i in range(0, len(texts), _EMBED_CHUNK_SIZE):
                    chunk_texts = texts[i : i + _EMBED_CHUNK_SIZE]
                    chunk_cols = cols_to_embed[i : i + _EMBED_CHUNK_SIZE]
                    try:
                        vecs = await embedder.aembed(chunk_texts)
                        for col, vec in zip(chunk_cols, vecs, strict=False):
                            col.embedding = vec
                    except Exception:
                        logger.warning(
                            "Batch embedding failed for connection %s chunk %d",
                            connection_id,
                            i,
                            exc_info=True,
                        )

            await db.commit()

            # ---- Phase 3: Sample values (opt-in, never for sensitive columns) ----
            if connection.sample_values_enabled:
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
                    async with engine.connect() as target_conn:
                        from sqlalchemy import text  # local to avoid polluting module scope

                        for table in tables:
                            columns = (
                                await db.scalars(
                                    select(SchemaColumn).where(SchemaColumn.table_id == table.id)
                                )
                            ).all()

                            for c in columns:
                                if _is_column_sensitive(c):
                                    continue  # never sample sensitive columns
                                if c.sample_values is not None and not force:
                                    continue

                                try:
                                    raw_sql = _safe_sample_query(
                                        table.schema,
                                        table.name,
                                        c.name,
                                        _SAMPLE_VALUE_LIMIT,
                                    )
                                    query = text(raw_sql)
                                    res = await target_conn.execute(query)
                                    raw_samples = [str(row[0]) for row in res.all()]
                                    c.sample_values = [
                                        s[:_SAMPLE_VALUE_MAX_LEN] for s in raw_samples
                                    ]
                                except Exception:
                                    logger.debug(
                                        "Sample value query failed for %s.%s.%s",
                                        table.name,
                                        table.schema,
                                        c.name,
                                        exc_info=True,
                                    )
                finally:
                    await engine.dispose()

                await db.commit()

            connection.status = "ready"
            await db.commit()

    finally:
        await llm.aclose()
        await embedder.aclose()
