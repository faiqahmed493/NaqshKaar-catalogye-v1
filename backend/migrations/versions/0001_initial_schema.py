"""Initial schema (sql/0001_initial_schema.sql)

Revision ID: 0001
Revises:
"""
from pathlib import Path

from alembic import op

revision = "0001"
down_revision = None
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
    run_sql((SQL / "0001_initial_schema.sql").read_text())


def downgrade() -> None:
    run_sql("""
        DROP VIEW IF EXISTS v_catalogue_variant, v_latest_link_check, v_latest_price CASCADE;
        DROP TABLE IF EXISTS audit_log, asset_review, asset_check, asset_3d, job_input_image, generation_job,
            generation_worker, generation_engine, admission_review, product_image, set_component, link_check,
            price_observation, variant_dimension, variant_attribute, variant_room_use, product_variant, product,
            category, retailer, stored_file, api_key, app_user CASCADE;
        DROP FUNCTION IF EXISTS set_updated_at();
        DROP TYPE IF EXISTS user_role, record_source, room_type, placement_type, product_group, variant_status,
            sale_unit_kind, length_unit, dimension_kind, availability_status, observation_outcome, attribute_key,
            attribute_source, image_role, view_angle, link_check_outcome, review_decision, engine_kind, job_status,
            asset_origin, asset_status, check_outcome, asset_decision CASCADE;
    """)
