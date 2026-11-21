"""Seed categories and the 3D engine registry (idempotent)

Revision ID: 0003
Revises: 0002
"""
from pathlib import Path

from alembic import op

revision = "0003"
down_revision = "0002"
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
    run_sql((SQL / "0003_seed_reference.sql").read_text())


def downgrade() -> None:
    pass  # reference rows are kept; products may point at them
