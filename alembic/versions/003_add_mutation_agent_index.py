"""Add index on (org_id, agent_id, created_at) for per-agent audit queries.

Revision ID: 003
Revises: 002
Create Date: 2026-02-15
"""

from alembic import op

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_mutation_org_agent_time",
        "sayou_mutation_log",
        ["org_id", "agent_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_mutation_org_agent_time", table_name="sayou_mutation_log")
