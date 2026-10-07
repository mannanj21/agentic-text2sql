import datetime
import uuid
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.config import get_settings
from app.database.core import Base

settings = get_settings()


def generate_uuid() -> str:
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=generate_uuid)
    email: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)

    connections: Mapped[list["Connection"]] = relationship(
        "Connection", back_populates="user", cascade="all, delete-orphan"
    )
    conversations: Mapped[list["Conversation"]] = relationship(
        "Conversation", back_populates="user", cascade="all, delete-orphan"
    )
    runs: Mapped[list["Run"]] = relationship(
        "Run", back_populates="user", cascade="all, delete-orphan"
    )


class Connection(Base):
    __tablename__ = "connections"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=generate_uuid)
    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    host: Mapped[str] = mapped_column(String, nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False)
    database: Mapped[str] = mapped_column(String, nullable=False)
    username: Mapped[str] = mapped_column(String, nullable=False)
    encrypted_password: Mapped[str] = mapped_column(String, nullable=False)
    allowed_schemas: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=lambda: ["public"]
    )
    embedding_model: Mapped[str | None] = mapped_column(String, nullable=True)
    embedding_dim: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sample_values_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    last_synced_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_sync_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    user: Mapped["User"] = relationship("User", back_populates="connections")
    tables: Mapped[list["SchemaTable"]] = relationship(
        "SchemaTable", back_populates="connection", cascade="all, delete-orphan"
    )
    glossary_terms: Mapped[list["GlossaryTerm"]] = relationship(
        "GlossaryTerm", back_populates="connection", cascade="all, delete-orphan"
    )
    conversations: Mapped[list["Conversation"]] = relationship(
        "Conversation", back_populates="connection", cascade="all, delete-orphan"
    )


class SchemaTable(Base):
    __tablename__ = "schema_tables"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=generate_uuid)
    connection_id: Mapped[str] = mapped_column(
        String, ForeignKey("connections.id", ondelete="CASCADE"), nullable=False, index=True
    )
    schema: Mapped[str] = mapped_column(String, nullable=False, default="public")
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    row_estimate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    embedding: Mapped[Any | None] = mapped_column(Vector(settings.EMBEDDING_DIM), nullable=True)

    connection: Mapped["Connection"] = relationship("Connection", back_populates="tables")
    columns: Mapped[list["SchemaColumn"]] = relationship(
        "SchemaColumn", back_populates="table", cascade="all, delete-orphan"
    )
    indexes: Mapped[list["SchemaIndex"]] = relationship(
        "SchemaIndex", back_populates="table", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_schema_tables_conn_schema_name", "connection_id", "schema", "name", unique=True),
    )


class SchemaColumn(Base):
    __tablename__ = "schema_columns"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=generate_uuid)
    table_id: Mapped[str] = mapped_column(
        String, ForeignKey("schema_tables.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    data_type: Mapped[str] = mapped_column(String, nullable=False)
    is_pk: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_sensitive: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sensitive_override: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    sample_values: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    embedding: Mapped[Any | None] = mapped_column(Vector(settings.EMBEDDING_DIM), nullable=True)

    table: Mapped["SchemaTable"] = relationship("SchemaTable", back_populates="columns")

    __table_args__ = (Index("ix_schema_columns_table_name", "table_id", "name", unique=True),)


class SchemaRelationship(Base):
    __tablename__ = "schema_relationships"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=generate_uuid)
    connection_id: Mapped[str] = mapped_column(
        String, ForeignKey("connections.id", ondelete="CASCADE"), nullable=False, index=True
    )
    from_column_id: Mapped[str] = mapped_column(
        String, ForeignKey("schema_columns.id", ondelete="CASCADE"), nullable=False
    )
    to_column_id: Mapped[str] = mapped_column(
        String, ForeignKey("schema_columns.id", ondelete="CASCADE"), nullable=False
    )


class SchemaIndex(Base):
    __tablename__ = "schema_indexes"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=generate_uuid)
    table_id: Mapped[str] = mapped_column(
        String, ForeignKey("schema_tables.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    definition: Mapped[str] = mapped_column(Text, nullable=False)

    table: Mapped["SchemaTable"] = relationship("SchemaTable", back_populates="indexes")

    __table_args__ = (Index("ix_schema_indexes_table_name", "table_id", "name", unique=True),)


class GlossaryTerm(Base):
    __tablename__ = "glossary_terms"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=generate_uuid)
    connection_id: Mapped[str] = mapped_column(
        String, ForeignKey("connections.id", ondelete="CASCADE"), nullable=False, index=True
    )
    term: Mapped[str] = mapped_column(String, nullable=False)
    definition: Mapped[str] = mapped_column(Text, nullable=False)

    connection: Mapped["Connection"] = relationship("Connection", back_populates="glossary_terms")


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=generate_uuid)
    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    connection_id: Mapped[str] = mapped_column(
        String, ForeignKey("connections.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship("User", back_populates="conversations")
    connection: Mapped["Connection"] = relationship("Connection", back_populates="conversations")
    messages: Mapped[list["Message"]] = relationship(
        "Message", back_populates="conversation", cascade="all, delete-orphan"
    )
    runs: Mapped[list["Run"]] = relationship(
        "Run", back_populates="conversation", cascade="all, delete-orphan"
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=generate_uuid)
    conversation_id: Mapped[str] = mapped_column(
        String, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String, nullable=False)  # 'user' or 'assistant'
    content: Mapped[str] = mapped_column(Text, nullable=False)
    run_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("runs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    conversation: Mapped["Conversation"] = relationship("Conversation", back_populates="messages")
    run: Mapped["Run"] = relationship("Run", back_populates="messages")


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=generate_uuid)
    conversation_id: Mapped[str] = mapped_column(
        String, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    standalone_question: Mapped[str | None] = mapped_column(Text, nullable=True)
    intent: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="running")
    total_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    final_sql: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_meta: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    result_preview: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    conversation: Mapped["Conversation"] = relationship("Conversation", back_populates="runs")
    user: Mapped["User"] = relationship("User", back_populates="runs")
    messages: Mapped[list["Message"]] = relationship("Message", back_populates="run")
    steps: Mapped[list["RunStep"]] = relationship(
        "RunStep", back_populates="run", cascade="all, delete-orphan", order_by="RunStep.seq"
    )
    attempts: Mapped[list["RunAttempt"]] = relationship(
        "RunAttempt",
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="RunAttempt.attempt_no",
    )


class RunStep(Base):
    __tablename__ = "run_steps"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=generate_uuid)
    run_id: Mapped[str] = mapped_column(
        String, ForeignKey("runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    node: Mapped[str] = mapped_column(String, nullable=False)
    started_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False)
    tool: Mapped[str | None] = mapped_column(String, nullable=True)
    tokens_in: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_out: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    run: Mapped["Run"] = relationship("Run", back_populates="steps")


class RunAttempt(Base):
    __tablename__ = "run_attempts"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=generate_uuid)
    run_id: Mapped[str] = mapped_column(
        String, ForeignKey("runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    attempt_no: Mapped[int] = mapped_column(Integer, nullable=False)
    sql: Mapped[str] = mapped_column(Text, nullable=False)
    failure_type: Mapped[str | None] = mapped_column(String, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    outcome: Mapped[str] = mapped_column(String, nullable=False)

    run: Mapped["Run"] = relationship("Run", back_populates="attempts")


class RateLimit(Base):
    __tablename__ = "rate_limits"

    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    window_start: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True
    )
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
