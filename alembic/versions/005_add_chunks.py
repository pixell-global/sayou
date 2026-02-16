"""Add chunks table for auto-chunking.

Revision ID: 005
Revises: 004
Create Date: 2026-02-16
"""

import sqlalchemy as sa
from alembic import op

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sayou_chunks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("org_id", sa.String(36), nullable=False),
        sa.Column("workspace_id", sa.String(36), nullable=False),
        sa.Column("file_id", sa.String(36), nullable=False),
        sa.Column("version_id", sa.String(36), nullable=False),
        sa.Column("chunk_index", sa.Integer, nullable=False),
        sa.Column("heading", sa.String(512), nullable=True),
        sa.Column("heading_level", sa.Integer, nullable=True),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("line_start", sa.Integer, nullable=False),
        sa.Column("line_end", sa.Integer, nullable=False),
        sa.Column("char_count", sa.Integer, nullable=False),
        sa.Column("token_estimate", sa.Integer, nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("file_id", "version_id", "chunk_index", name="uq_chunk_file_ver_idx"),
    )
    op.create_index("ix_chunk_org_ws", "sayou_chunks", ["org_id", "workspace_id"])
    op.create_index("ix_chunk_file_id", "sayou_chunks", ["file_id"])


def downgrade() -> None:
    op.drop_index("ix_chunk_file_id", table_name="sayou_chunks")
    op.drop_index("ix_chunk_org_ws", table_name="sayou_chunks")
    op.drop_table("sayou_chunks")
