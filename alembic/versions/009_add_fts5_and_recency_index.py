"""Add FTS5 full-text search and recency index.

Revision ID: 009
Revises: 008
Create Date: 2026-02-16
"""

from alembic import op

revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Recency index (works on both SQLite and MySQL)
    op.create_index(
        "ix_file_recency",
        "sayou_files",
        ["org_id", "workspace_id", "updated_at"],
    )

    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "sqlite":
        # FTS5 virtual tables
        op.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS sayou_files_fts USING fts5("
            "file_id UNINDEXED, org_id UNINDEXED, workspace_id UNINDEXED, "
            "path, content_text, frontmatter)"
        )
        op.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS sayou_chunks_fts USING fts5("
            "chunk_id UNINDEXED, org_id UNINDEXED, workspace_id UNINDEXED, "
            "file_id UNINDEXED, content)"
        )

        # Triggers — files
        op.execute(
            "CREATE TRIGGER IF NOT EXISTS sayou_files_fts_ai "
            "AFTER INSERT ON sayou_files BEGIN "
            "INSERT INTO sayou_files_fts(file_id, org_id, workspace_id, path, content_text, frontmatter) "
            "VALUES (NEW.id, NEW.org_id, NEW.workspace_id, NEW.path, "
            "COALESCE(NEW.content_text, ''), COALESCE(NEW.frontmatter, '')); END;"
        )
        op.execute(
            "CREATE TRIGGER IF NOT EXISTS sayou_files_fts_au "
            "AFTER UPDATE ON sayou_files BEGIN "
            "DELETE FROM sayou_files_fts WHERE file_id = OLD.id; "
            "INSERT INTO sayou_files_fts(file_id, org_id, workspace_id, path, content_text, frontmatter) "
            "VALUES (NEW.id, NEW.org_id, NEW.workspace_id, NEW.path, "
            "COALESCE(NEW.content_text, ''), COALESCE(NEW.frontmatter, '')); END;"
        )
        op.execute(
            "CREATE TRIGGER IF NOT EXISTS sayou_files_fts_ad "
            "AFTER DELETE ON sayou_files BEGIN "
            "DELETE FROM sayou_files_fts WHERE file_id = OLD.id; END;"
        )

        # Triggers — chunks
        op.execute(
            "CREATE TRIGGER IF NOT EXISTS sayou_chunks_fts_ai "
            "AFTER INSERT ON sayou_chunks BEGIN "
            "INSERT INTO sayou_chunks_fts(chunk_id, org_id, workspace_id, file_id, content) "
            "VALUES (NEW.id, NEW.org_id, NEW.workspace_id, NEW.file_id, NEW.content); END;"
        )
        op.execute(
            "CREATE TRIGGER IF NOT EXISTS sayou_chunks_fts_au "
            "AFTER UPDATE ON sayou_chunks BEGIN "
            "DELETE FROM sayou_chunks_fts WHERE chunk_id = OLD.id; "
            "INSERT INTO sayou_chunks_fts(chunk_id, org_id, workspace_id, file_id, content) "
            "VALUES (NEW.id, NEW.org_id, NEW.workspace_id, NEW.file_id, NEW.content); END;"
        )
        op.execute(
            "CREATE TRIGGER IF NOT EXISTS sayou_chunks_fts_ad "
            "AFTER DELETE ON sayou_chunks BEGIN "
            "DELETE FROM sayou_chunks_fts WHERE chunk_id = OLD.id; END;"
        )

        # Backfill existing data
        op.execute(
            "INSERT OR IGNORE INTO sayou_files_fts"
            "(file_id, org_id, workspace_id, path, content_text, frontmatter) "
            "SELECT id, org_id, workspace_id, path, "
            "COALESCE(content_text, ''), COALESCE(frontmatter, '') "
            "FROM sayou_files "
            "WHERE id NOT IN (SELECT file_id FROM sayou_files_fts)"
        )
        op.execute(
            "INSERT OR IGNORE INTO sayou_chunks_fts"
            "(chunk_id, org_id, workspace_id, file_id, content) "
            "SELECT id, org_id, workspace_id, file_id, content "
            "FROM sayou_chunks "
            "WHERE id NOT IN (SELECT chunk_id FROM sayou_chunks_fts)"
        )

    else:
        # MySQL FULLTEXT indexes
        op.execute(
            "ALTER TABLE sayou_files "
            "ADD FULLTEXT INDEX ft_files_search (path, content_text, frontmatter)"
        )
        op.execute(
            "ALTER TABLE sayou_chunks "
            "ADD FULLTEXT INDEX ft_chunks_search (content)"
        )


def downgrade() -> None:
    op.drop_index("ix_file_recency", table_name="sayou_files")

    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "sqlite":
        # Drop triggers
        for name in (
            "sayou_files_fts_ai", "sayou_files_fts_au", "sayou_files_fts_ad",
            "sayou_chunks_fts_ai", "sayou_chunks_fts_au", "sayou_chunks_fts_ad",
        ):
            op.execute(f"DROP TRIGGER IF EXISTS {name}")
        # Drop virtual tables
        op.execute("DROP TABLE IF EXISTS sayou_files_fts")
        op.execute("DROP TABLE IF EXISTS sayou_chunks_fts")
    else:
        op.drop_index("ft_files_search", table_name="sayou_files")
        op.drop_index("ft_chunks_search", table_name="sayou_chunks")
