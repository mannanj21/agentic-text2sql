"""Schema DDL renderer for LLM context — Stage 3: full schema in compact DDL."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Connection, SchemaColumn, SchemaRelationship, SchemaTable


async def render_schema_ddl(connection: Connection, db: AsyncSession) -> str:
    """Return a compact PostgreSQL DDL string for all non-sensitive tables.

    Sensitive columns are excluded entirely.  Foreign-key references are
    appended as REFERENCES comments so the LLM can follow join paths.
    """
    # Load tables with their columns eagerly
    tables = (
        await db.scalars(
            select(SchemaTable)
            .where(SchemaTable.connection_id == connection.id)
            .order_by(SchemaTable.schema, SchemaTable.name)
        )
    ).all()

    if not tables:
        return "-- (no schema metadata available; run a sync first)"

    # Build a map of column-id → qualified table name for FK rendering
    col_id_to_table: dict[str, str] = {}
    for table in tables:
        columns = (
            await db.scalars(select(SchemaColumn).where(SchemaColumn.table_id == table.id))
        ).all()
        for col in columns:
            col_id_to_table[col.id] = f"{table.schema}.{table.name}"

    # Load FK relationships for this connection
    rels = (
        await db.scalars(
            select(SchemaRelationship).where(SchemaRelationship.connection_id == connection.id)
        )
    ).all()
    # Map from_column_id → referenced table name
    fk_map: dict[str, str] = {}
    for rel in rels:
        ref_table = col_id_to_table.get(rel.to_column_id, "")
        if ref_table:
            fk_map[rel.from_column_id] = ref_table

    lines: list[str] = []
    for table in tables:
        qualified = f"{table.schema}.{table.name}"
        header = f"CREATE TABLE {qualified} ("
        if table.description:
            lines.append(f"-- {table.description}")
        if table.row_estimate is not None:
            lines.append(f"-- ~{table.row_estimate:,} rows")

        columns = (
            await db.scalars(
                select(SchemaColumn)
                .where(SchemaColumn.table_id == table.id)
                .order_by(SchemaColumn.name)
            )
        ).all()

        col_lines: list[str] = []
        pk_cols: list[str] = []
        for col in columns:
            # Exclude sensitive columns from DDL
            effective_sensitive = (
                col.sensitive_override if col.sensitive_override is not None else col.is_sensitive
            )
            if effective_sensitive:
                continue
            parts = [f"  {col.name} {col.data_type}"]
            if col.is_pk:
                pk_cols.append(col.name)
            if col.id in fk_map:
                parts.append(f"-- FK → {fk_map[col.id]}")
            if col.description:
                parts.append(f"-- {col.description}")
            col_lines.append(" ".join(parts))

        if not col_lines:
            # All columns are sensitive — skip this table entirely
            continue

        if pk_cols:
            col_lines.append(f"  PRIMARY KEY ({', '.join(pk_cols)})")

        lines.append(header)
        lines.extend(f"{line}," for line in col_lines[:-1])
        lines.append(col_lines[-1])
        lines.append(");")
        lines.append("")

    return "\n".join(lines).rstrip() or "-- (schema rendered empty; all columns may be sensitive)"
