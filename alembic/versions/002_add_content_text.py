"""Add content_text column to sayou_files for body search.

Revision ID: 002
Revises: 001
Create Date: 2026-02-14
"""

from alembic import op
import sqlalchemy as sa

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sayou_files", sa.Column("content_text", sa.Text, nullable=True))


def downgrade() -> None:
    op.drop_column("sayou_files", "content_text")
