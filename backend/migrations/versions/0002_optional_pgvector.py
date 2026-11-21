"""Optional pgvector embeddings table (no-op without the extension)

Revision ID: 0002
Revises: 0001
"""
from pathlib import Path

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

SQL = Path(__file__).resolve().parents[2] / "sql"


def run_sql(sql: str) -> None:
    """Send a whole SQL file to psycopg in one call. With no parameters psycopg uses the simple
    query protocol, which allows many statements, DO blocks and ':' characters in literals."""
    cur = op.get_bind().connection.cursor()
    try:
        cur.execute(sql)
    finally:
        cur.close()


def upgrade() -> None:
    run_sql((SQL / "0002_optional_pgvector.sql").read_text())


def downgrade() -> None:
    run_sql("DROP TABLE IF EXISTS variant_embedding")
