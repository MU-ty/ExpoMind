"""add editable exhibition name to users

Revision ID: 20260802_04
Revises: 20260801_03
"""
from alembic import op

revision = "20260802_04"
down_revision = "20260801_03"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS event_name VARCHAR(120) NOT NULL DEFAULT '2026 Shenzhen Electronics Expo'")


def downgrade():
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS event_name")
