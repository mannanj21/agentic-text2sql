"""Authenticated schema metadata and glossary endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.connections import _owned_connection
from app.auth import current_user
from app.database.core import get_db
from app.database.models import GlossaryTerm, SchemaColumn, SchemaTable, User

router = APIRouter(prefix="/connections", tags=["Schema"])
CurrentUser = Annotated[User, Depends(current_user)]
DbSession = Annotated[AsyncSession, Depends(get_db)]


class SchemaColumnResponse(BaseModel):
    id: str
    name: str
    data_type: str
    is_pk: bool
    is_sensitive: bool
    description: str | None


class SchemaTableResponse(BaseModel):
    id: str
    schema_name: str = Field(serialization_alias="schema")
    name: str
    description: str | None
    row_estimate: int | None
    columns: list[SchemaColumnResponse]


class SchemaResponse(BaseModel):
    tables: list[SchemaTableResponse]


class TableUpdate(BaseModel):
    id: str
    description: str | None = Field(default=None, max_length=5_000)


class ColumnUpdate(BaseModel):
    id: str
    description: str | None = Field(default=None, max_length=5_000)
    is_sensitive: bool | None = None


class SchemaPatchRequest(BaseModel):
    tables: list[TableUpdate] = Field(default_factory=list, max_length=100)
    columns: list[ColumnUpdate] = Field(default_factory=list, max_length=1_000)


class GlossaryTermRequest(BaseModel):
    term: str = Field(min_length=1, max_length=200)
    definition: str = Field(min_length=1, max_length=5_000)


class GlossaryTermResponse(GlossaryTermRequest):
    id: str

    @classmethod
    def from_model(cls, term: GlossaryTerm) -> "GlossaryTermResponse":
        return cls(id=term.id, term=term.term, definition=term.definition)


def _schema_response(tables: list[SchemaTable]) -> SchemaResponse:
    return SchemaResponse(
        tables=[
            SchemaTableResponse(
                id=table.id,
                schema_name=table.schema,
                name=table.name,
                description=table.description,
                row_estimate=table.row_estimate,
                columns=[
                    SchemaColumnResponse(
                        id=column.id,
                        name=column.name,
                        data_type=column.data_type,
                        is_pk=column.is_pk,
                        is_sensitive=column.is_sensitive,
                        description=column.description,
                    )
                    for column in table.columns
                ],
            )
            for table in tables
        ]
    )


@router.get("/{connection_id}/schema", response_model=SchemaResponse)
async def get_schema(connection_id: str, user: CurrentUser, db: DbSession) -> SchemaResponse:
    await _owned_connection(connection_id, user.id, db)
    tables = (
        await db.scalars(
            select(SchemaTable)
            .where(SchemaTable.connection_id == connection_id)
            .order_by(SchemaTable.schema, SchemaTable.name)
        )
    ).all()
    for table in tables:
        await db.refresh(table, attribute_names=["columns"])
        table.columns.sort(key=lambda column: column.name)
    return _schema_response(list(tables))


@router.patch("/{connection_id}/schema", response_model=SchemaResponse)
async def patch_schema(
    connection_id: str,
    request: SchemaPatchRequest,
    user: CurrentUser,
    db: DbSession,
) -> SchemaResponse:
    await _owned_connection(connection_id, user.id, db)
    table_ids = {update.id for update in request.tables}
    column_ids = {update.id for update in request.columns}
    tables = (
        await db.scalars(
            select(SchemaTable).where(
                SchemaTable.connection_id == connection_id,
                SchemaTable.id.in_(table_ids),
            )
        )
    ).all()
    columns = (
        await db.scalars(
            select(SchemaColumn)
            .join(SchemaTable)
            .where(
                SchemaTable.connection_id == connection_id,
                SchemaColumn.id.in_(column_ids),
            )
        )
    ).all()
    if len(tables) != len(table_ids) or len(columns) != len(column_ids):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Schema object not found")

    tables_by_id = {table.id: table for table in tables}
    for update in request.tables:
        if "description" in update.model_fields_set:
            tables_by_id[update.id].description = update.description
    columns_by_id = {column.id: column for column in columns}
    for column_update in request.columns:
        column = columns_by_id[column_update.id]
        if "description" in column_update.model_fields_set:
            column.description = column_update.description
        if column_update.is_sensitive is not None:
            column.is_sensitive = column_update.is_sensitive
            column.sensitive_override = column_update.is_sensitive
    await db.commit()
    return await get_schema(connection_id, user, db)


@router.get("/{connection_id}/glossary", response_model=list[GlossaryTermResponse])
async def list_glossary(
    connection_id: str, user: CurrentUser, db: DbSession
) -> list[GlossaryTermResponse]:
    await _owned_connection(connection_id, user.id, db)
    terms = (
        await db.scalars(
            select(GlossaryTerm)
            .where(GlossaryTerm.connection_id == connection_id)
            .order_by(GlossaryTerm.term)
        )
    ).all()
    return [GlossaryTermResponse.from_model(term) for term in terms]


@router.post(
    "/{connection_id}/glossary",
    response_model=GlossaryTermResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_glossary_term(
    connection_id: str,
    request: GlossaryTermRequest,
    user: CurrentUser,
    db: DbSession,
) -> GlossaryTermResponse:
    await _owned_connection(connection_id, user.id, db)
    term = GlossaryTerm(
        connection_id=connection_id,
        term=request.term,
        definition=request.definition,
    )
    db.add(term)
    await db.commit()
    await db.refresh(term)
    return GlossaryTermResponse.from_model(term)


@router.delete("/{connection_id}/glossary/{term_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_glossary_term(
    connection_id: str, term_id: str, user: CurrentUser, db: DbSession
) -> None:
    await _owned_connection(connection_id, user.id, db)
    term = await db.scalar(
        select(GlossaryTerm).where(
            GlossaryTerm.id == term_id,
            GlossaryTerm.connection_id == connection_id,
        )
    )
    if term is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Glossary term not found")
    await db.delete(term)
    await db.commit()
