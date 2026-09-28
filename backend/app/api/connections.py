"""Authenticated connection management endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import current_user
from app.config import get_settings
from app.database.core import get_db
from app.database.crypto import CredentialCipher
from app.database.models import Connection, User
from app.guardrails.ssrf import UnsafeTargetError, resolve_target
from app.tools.introspection import TargetConnectionError, test_target_connection

router = APIRouter(prefix="/connections", tags=["Connections"])
CurrentUser = Annotated[User, Depends(current_user)]
DbSession = Annotated[AsyncSession, Depends(get_db)]


class ConnectionCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    host: str = Field(min_length=1, max_length=253)
    port: int = 5432
    database: str = Field(min_length=1, max_length=63)
    username: str = Field(min_length=1, max_length=63)
    password: SecretStr = Field(min_length=1)
    schemas: list[str] = Field(default_factory=lambda: ["public"], min_length=1)


class ConnectionResponse(BaseModel):
    id: str
    name: str
    host: str
    port: int
    database: str
    username: str
    status: str

    @classmethod
    def from_model(cls, connection: Connection) -> "ConnectionResponse":
        return cls(
            id=connection.id,
            name=connection.name,
            host=connection.host,
            port=connection.port,
            database=connection.database,
            username=connection.username,
            status=connection.status,
        )


def _safety_refusal(reasons: tuple[str, ...]) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={
            "message": "Target database role is not safe for read-only analytics.",
            "reasons": list(reasons),
            "readonly_role_setup": "/docs/readonly-role.sql",
        },
    )


async def _verify_connection_request(request: ConnectionCreateRequest) -> str:
    settings = get_settings()
    try:
        target = resolve_target(
            request.host,
            request.port,
            allow_private_hosts=settings.ALLOW_PRIVATE_HOSTS,
        )
    except UnsafeTargetError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    encrypted_password = CredentialCipher(settings.ENCRYPTION_KEY).encrypt(
        request.password.get_secret_value()
    )
    try:
        report = await test_target_connection(
            target=target,
            database=request.database,
            username=request.username,
            encrypted_password=encrypted_password,
            encryption_key=settings.ENCRYPTION_KEY.get_secret_value(),
            schemas=request.schemas,
        )
    except TargetConnectionError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if not report.is_safe:
        raise _safety_refusal(report.reasons)
    return encrypted_password


async def _owned_connection(connection_id: str, user_id: str, db: AsyncSession) -> Connection:
    connection = await db.scalar(
        select(Connection).where(Connection.id == connection_id, Connection.user_id == user_id)
    )
    if connection is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connection not found")
    return connection


@router.post("", response_model=ConnectionResponse, status_code=status.HTTP_201_CREATED)
async def create_connection(
    request: ConnectionCreateRequest, user: CurrentUser, db: DbSession
) -> ConnectionResponse:
    encrypted_password = await _verify_connection_request(request)
    connection = Connection(
        user_id=user.id,
        name=request.name,
        host=request.host,
        port=request.port,
        database=request.database,
        username=request.username,
        encrypted_password=encrypted_password,
        status="pending",
    )
    db.add(connection)
    await db.commit()
    await db.refresh(connection)
    return ConnectionResponse.from_model(connection)


@router.get("", response_model=list[ConnectionResponse])
async def list_connections(user: CurrentUser, db: DbSession) -> list[ConnectionResponse]:
    connections = (
        await db.scalars(
            select(Connection).where(Connection.user_id == user.id).order_by(Connection.name)
        )
    ).all()
    return [ConnectionResponse.from_model(connection) for connection in connections]


@router.delete("/{connection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_connection(connection_id: str, user: CurrentUser, db: DbSession) -> None:
    connection = await _owned_connection(connection_id, user.id, db)
    await db.delete(connection)
    await db.commit()


@router.post("/{connection_id}/sync", response_model=ConnectionResponse)
async def sync_connection(
    connection_id: str, user: CurrentUser, db: DbSession
) -> ConnectionResponse:
    """Recheck credentials and safety; schema synchronization follows in S2.6."""
    connection = await _owned_connection(connection_id, user.id, db)
    settings = get_settings()
    try:
        target = resolve_target(
            connection.host,
            connection.port,
            allow_private_hosts=settings.ALLOW_PRIVATE_HOSTS,
        )
        report = await test_target_connection(
            target=target,
            database=connection.database,
            username=connection.username,
            encrypted_password=connection.encrypted_password,
            encryption_key=settings.ENCRYPTION_KEY.get_secret_value(),
            schemas=["public"],
        )
    except (UnsafeTargetError, TargetConnectionError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if not report.is_safe:
        raise _safety_refusal(report.reasons)
    return ConnectionResponse.from_model(connection)
