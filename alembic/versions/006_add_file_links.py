"""Add file links table for knowledge graph.

Revision ID: 006
Revises: 005
Create Date: 2026-02-16
"""

import sqlalchemy as sa
from alembic import op

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sayou_file_links",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("org_id", sa.String(36), nullable=False),
        sa.Column("workspace_id", sa.String(36), nullable=False),
        sa.Column("source_path", sa.String(512), nullable=False),
        sa.Column("target_path", sa.String(512), nullable=False),
        sa.Column("link_type", sa.String(50), nullable=False, server_default="reference"),
        sa.Column("auto_detected", sa.Boolean, nullable=False, server_default=sa.text("0")),
        sa.Column("context", sa.String(512), nullable=True),
        sa.Column("created_by", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint(
            "org_id", "workspace_id", "source_path", "target_path", "link_type",
            name="uq_link_org_ws_src_tgt_type",
        ),
    )
    op.create_index("ix_link_source", "sayou_file_links", ["org_id", "workspace_id", "source_path"])
    op.create_index("ix_link_target", "sayou_file_links", ["org_id", "workspace_id", "target_path"])


def downgrade() -> None:
    op.drop_index("ix_link_target", table_name="sayou_file_links")
    op.drop_index("ix_link_source", table_name="sayou_file_links")
    op.drop_table("sayou_file_links")
