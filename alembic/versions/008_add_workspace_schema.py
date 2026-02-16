"""Add workspace schema table for auto-metadata.

Revision ID: 008
Revises: 007
Create Date: 2026-02-16
"""

import sqlalchemy as sa
from alembic import op

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sayou_workspace_schema",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("org_id", sa.String(36), nullable=False),
        sa.Column("workspace_id", sa.String(36), nullable=False),
        sa.Column("field_name", sa.String(255), nullable=False),
        sa.Column("field_type", sa.String(50), nullable=False),
        sa.Column("occurrence_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("sample_values", sa.Text, nullable=True),
        sa.Column("is_auto", sa.Boolean, nullable=False, server_default=sa.text("0")),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint(
            "org_id", "workspace_id", "field_name",
            name="uq_schema_org_ws_field",
        ),
    )


def downgrade() -> None:
    op.drop_table("sayou_workspace_schema")
