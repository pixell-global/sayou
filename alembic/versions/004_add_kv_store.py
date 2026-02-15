"""Add KV store table.

Revision ID: 004
Revises: 003
Create Date: 2026-02-15
"""

import sqlalchemy as sa
from alembic import op

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sayou_kv_store",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("org_id", sa.String(36), nullable=False),
        sa.Column("workspace_id", sa.String(36), nullable=False),
        sa.Column("key", sa.String(512), nullable=False),
        sa.Column("value", sa.Text, nullable=False),
        sa.Column("ttl_seconds", sa.Integer, nullable=True),
        sa.Column("expires_at", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("org_id", "workspace_id", "key", name="uq_kv_org_ws_key"),
    )
    op.create_index("ix_kv_expires", "sayou_kv_store", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_kv_expires", table_name="sayou_kv_store")
    op.drop_table("sayou_kv_store")
