"""Initial schema - 6 tables for sayou MVP

Revision ID: 001
Revises:
Create Date: 2026-02-14
"""

from alembic import op
import sqlalchemy as sa

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # sayou_workspaces
    op.create_table(
        "sayou_workspaces",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("org_id", sa.String(36), nullable=False, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(255), nullable=False),
        sa.Column("created_by", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("org_id", "slug", name="uq_workspace_org_slug"),
    )

    # sayou_workspace_members
    op.create_table(
        "sayou_workspace_members",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), nullable=False, index=True),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("role", sa.String(20), nullable=False, server_default="reader"),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("workspace_id", "user_id", name="uq_member_workspace_user"),
    )

    # sayou_files
    op.create_table(
        "sayou_files",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("org_id", sa.String(36), nullable=False),
        sa.Column("workspace_id", sa.String(36), nullable=False),
        sa.Column("path", sa.String(512), nullable=False),
        sa.Column("folder_path", sa.String(512), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(50), nullable=False, server_default="text/markdown"),
        sa.Column("frontmatter", sa.Text, nullable=True),
        sa.Column("current_version_id", sa.String(36), nullable=True),
        sa.Column("version_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("deleted_at", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("org_id", "workspace_id", "path", name="uq_file_org_ws_path"),
    )
    op.create_index("ix_file_folder", "sayou_files", ["org_id", "workspace_id", "folder_path"])

    # sayou_file_versions
    op.create_table(
        "sayou_file_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("file_id", sa.String(36), nullable=False, index=True),
        sa.Column("version_number", sa.Integer, nullable=False),
        sa.Column("s3_key", sa.String(512), nullable=False),
        sa.Column("s3_bucket", sa.String(255), nullable=False),
        sa.Column("size_bytes", sa.Integer, nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("created_by", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("file_id", "version_number", name="uq_version_file_num"),
    )

    # sayou_index_cache
    op.create_table(
        "sayou_index_cache",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("org_id", sa.String(36), nullable=False),
        sa.Column("workspace_id", sa.String(36), nullable=False),
        sa.Column("folder_path", sa.String(512), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("file_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint(
            "org_id", "workspace_id", "folder_path", name="uq_index_org_ws_folder"
        ),
    )

    # sayou_mutation_log
    op.create_table(
        "sayou_mutation_log",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("org_id", sa.String(36), nullable=False),
        sa.Column("workspace_id", sa.String(36), nullable=False),
        sa.Column("agent_id", sa.String(255), nullable=True),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("file_path", sa.String(512), nullable=False),
        sa.Column("version_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "ix_mutation_org_ws_time",
        "sayou_mutation_log",
        ["org_id", "workspace_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("sayou_mutation_log")
    op.drop_table("sayou_index_cache")
    op.drop_table("sayou_file_versions")
    op.drop_table("sayou_files")
    op.drop_table("sayou_workspace_members")
    op.drop_table("sayou_workspaces")
