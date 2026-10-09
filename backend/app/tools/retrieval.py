"""Schema retrieval for the text-to-SQL prompt context."""

from __future__ import annotations

import time
from dataclasses import dataclass

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.database.models import GlossaryTerm, SchemaColumn, SchemaRelationship, SchemaTable
from app.llm.embedding import EmbedderClient


@dataclass(frozen=True)
class RetrievedSchema:
    """Small, serialisable retrieval result for graph state and tracing."""

    ddl: str
    table_ids: list[str]
    table_names: list[str]
    latency_ms: int


def _is_sensitive(column: SchemaColumn) -> bool:
    return (
        column.sensitive_override if column.sensitive_override is not None else column.is_sensitive
    )


async def _glossary_hits(db: AsyncSession, connection_id: str, question: str) -> list[GlossaryTerm]:
    terms = (
        await db.scalars(
            select(GlossaryTerm)
            .where(GlossaryTerm.connection_id == connection_id)
            .order_by(GlossaryTerm.term)
        )
    ).all()
    question_words = set(question.casefold().split())
    return [term for term in terms if set(term.term.casefold().split()) <= question_words]


async def _expand_one_fk_hop(db: AsyncSession, table_ids: set[str]) -> set[str]:
    if not table_ids:
        return set()
    seed_ids = set(
        (
            await db.scalars(select(SchemaColumn.id).where(SchemaColumn.table_id.in_(table_ids)))
        ).all()
    )
    if not seed_ids:
        return set()
    rels = (
        await db.scalars(
            select(SchemaRelationship).where(
                or_(
                    SchemaRelationship.from_column_id.in_(seed_ids),
                    SchemaRelationship.to_column_id.in_(seed_ids),
                )
            )
        )
    ).all()
    related_ids = {
        column_id
        for rel in rels
        for column_id in (rel.from_column_id, rel.to_column_id)
        if column_id not in seed_ids
    }
    if not related_ids:
        return set()
    return set(
        (
            await db.scalars(select(SchemaColumn.table_id).where(SchemaColumn.id.in_(related_ids)))
        ).all()
    )


async def _render(
    db: AsyncSession, connection_id: str, table_ids: set[str], question: str
) -> tuple[str, list[str], list[str]]:
    tables = (
        await db.scalars(
            select(SchemaTable)
            .where(SchemaTable.connection_id == connection_id, SchemaTable.id.in_(table_ids))
            .options(selectinload(SchemaTable.columns))
            .order_by(SchemaTable.schema, SchemaTable.name)
        )
    ).all()
    table_by_id = {table.id: table for table in tables}
    columns = {column.id: column for table in tables for column in table.columns}
    rels = (
        await db.scalars(
            select(SchemaRelationship).where(
                SchemaRelationship.connection_id == connection_id,
                SchemaRelationship.from_column_id.in_(columns),
            )
        )
    ).all()
    foreign_keys = {rel.from_column_id: rel.to_column_id for rel in rels}
    lines: list[str] = []
    rendered_ids: list[str] = []
    names: list[str] = []
    for table in tables:
        visible = [
            column
            for column in sorted(table.columns, key=lambda c: c.name)
            if not _is_sensitive(column)
        ]
        if not visible:
            continue
        rendered_ids.append(table.id)
        names.append(f"{table.schema}.{table.name}")
        if table.description:
            lines.append(f"-- {table.description}")
        lines.append(f"CREATE TABLE {table.schema}.{table.name} (")
        definitions: list[str] = []
        for column in visible:
            definition = f"  {column.name} {column.data_type}"
            if column.is_pk:
                definition += " PRIMARY KEY"
            target = columns.get(foreign_keys.get(column.id, ""))
            if target is not None:
                target_table = table_by_id[target.table_id]
                definition += (
                    f" REFERENCES {target_table.schema}.{target_table.name}({target.name})"
                )
            if column.description:
                definition += f" -- {column.description}"
            definitions.append(definition)
        lines.append(",\n".join(definitions))
        lines.extend((");", ""))
    glossary = await _glossary_hits(db, connection_id, question)
    if glossary:
        lines.append("/* Relevant glossary:")
        lines.extend(f"- {term.term}: {term.definition}" for term in glossary)
        lines.append("*/")
    return "\n".join(lines).rstrip(), rendered_ids, names


async def retrieve_schema(db: AsyncSession, connection_id: str, question: str) -> RetrievedSchema:
    """Retrieve top-k schema metadata, expanding selected tables one FK hop."""
    started = time.perf_counter()
    settings = get_settings()
    count = await db.scalar(
        select(func.count(SchemaTable.id)).where(SchemaTable.connection_id == connection_id)
    )
    if int(count or 0) <= settings.RETRIEVAL_MIN_TABLES:
        selected = set(
            (
                await db.scalars(
                    select(SchemaTable.id).where(SchemaTable.connection_id == connection_id)
                )
            ).all()
        )
    else:
        embedder = EmbedderClient(settings)
        try:
            vector = (await embedder.aembed([question]))[0]
        finally:
            await embedder.aclose()
        k = settings.RETRIEVAL_TOP_K
        table_hits = (
            await db.scalars(
                select(SchemaTable.id)
                .where(
                    SchemaTable.connection_id == connection_id, SchemaTable.embedding.is_not(None)
                )
                .order_by(SchemaTable.embedding.cosine_distance(vector))
                .limit(k)
            )
        ).all()
        column_hits = (
            await db.scalars(
                select(SchemaColumn.table_id)
                .join(SchemaTable, SchemaColumn.table_id == SchemaTable.id)
                .where(
                    SchemaTable.connection_id == connection_id, SchemaColumn.embedding.is_not(None)
                )
                .order_by(SchemaColumn.embedding.cosine_distance(vector))
                .limit(k)
            )
        ).all()
        selected = set(table_hits) | set(column_hits)
        selected.update(await _expand_one_fk_hop(db, selected))
    ddl, table_ids, table_names = await _render(db, connection_id, selected, question)
    return RetrievedSchema(
        ddl, table_ids, table_names, max(1, int((time.perf_counter() - started) * 1000))
    )
