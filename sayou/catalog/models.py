import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def generate_uuid() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


class SayouWorkspace(Base):
    __tablename__ = "sayou_workspaces"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    org_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False)
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("org_id", "slug", name="uq_workspace_org_slug"),
    )


class SayouWorkspaceMember(Base):
    __tablename__ = "sayou_workspace_members"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    workspace_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="reader")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("workspace_id", "user_id", name="uq_member_workspace_user"),
    )


class SayouFile(Base):
    __tablename__ = "sayou_files"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    org_id: Mapped[str] = mapped_column(String(36), nullable=False)
    workspace_id: Mapped[str] = mapped_column(String(36), nullable=False)
    path: Mapped[str] = mapped_column(String(512), nullable=False)
    folder_path: Mapped[str] = mapped_column(String(512), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(50), nullable=False, default="text/markdown")
    frontmatter: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    current_version_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    version_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("org_id", "workspace_id", "path", name="uq_file_org_ws_path"),
        Index("ix_file_folder", "org_id", "workspace_id", "folder_path"),
    )


class SayouFileVersion(Base):
    __tablename__ = "sayou_file_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    file_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    s3_key: Mapped[str] = mapped_column(String(512), nullable=False)
    s3_bucket: Mapped[str] = mapped_column(String(255), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("file_id", "version_number", name="uq_version_file_num"),
    )


class SayouIndexCache(Base):
    __tablename__ = "sayou_index_cache"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    org_id: Mapped[str] = mapped_column(String(36), nullable=False)
    workspace_id: Mapped[str] = mapped_column(String(36), nullable=False)
    folder_path: Mapped[str] = mapped_column(String(512), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    file_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("org_id", "workspace_id", "folder_path", name="uq_index_org_ws_folder"),
    )


class SayouKVEntry(Base):
    __tablename__ = "sayou_kv_store"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    org_id: Mapped[str] = mapped_column(String(36), nullable=False)
    workspace_id: Mapped[str] = mapped_column(String(36), nullable=False)
    key: Mapped[str] = mapped_column(String(512), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    ttl_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("org_id", "workspace_id", "key", name="uq_kv_org_ws_key"),
        Index("ix_kv_expires", "expires_at"),
    )


class SayouMutationLog(Base):
    __tablename__ = "sayou_mutation_log"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    org_id: Mapped[str] = mapped_column(String(36), nullable=False)
    workspace_id: Mapped[str] = mapped_column(String(36), nullable=False)
    agent_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    file_path: Mapped[str] = mapped_column(String(512), nullable=False)
    version_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("ix_mutation_org_ws_time", "org_id", "workspace_id", "created_at"),
        Index("ix_mutation_org_agent_time", "org_id", "agent_id", "created_at"),
    )
