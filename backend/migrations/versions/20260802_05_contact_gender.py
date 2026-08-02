"""add explicit contact gender for local fallback avatars

Revision ID: 20260802_05
Revises: 20260802_04
"""
from alembic import op

revision = "20260802_05"
down_revision = "20260802_04"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE contacts ADD COLUMN IF NOT EXISTS gender VARCHAR(20) NOT NULL DEFAULT 'unspecified'")


def downgrade():
    op.execute("ALTER TABLE contacts DROP COLUMN IF EXISTS gender")
