"""Add embeddings table for semantic search.

Revision ID: 007
Revises: 006
Create Date: 2026-02-16
"""

import sqlalchemy as sa
from alembic import op

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sayou_embeddings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("org_id", sa.String(36), nullable=False),
        sa.Column("workspace_id", sa.String(36), nullable=False),
        sa.Column("file_id", sa.String(36), nullable=False),
        sa.Column("version_id", sa.String(36), nullable=False),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("dimensions", sa.Integer, nullable=False),
        sa.Column("embedding", sa.LargeBinary, nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("file_id", "provider", "model", name="uq_embedding_file_provider_model"),
    )
    op.create_index("ix_embedding_org_ws", "sayou_embeddings", ["org_id", "workspace_id"])


def downgrade() -> None:
    op.drop_index("ix_embedding_org_ws", table_name="sayou_embeddings")
    op.drop_table("sayou_embeddings")
