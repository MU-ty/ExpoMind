"""expand contact cards and face profiles

Revision ID: 20260801_03
Revises: 20260730_02
"""
from alembic import op

revision = "20260801_03"
down_revision = "20260730_02"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE contacts ADD COLUMN IF NOT EXISTS phone VARCHAR(80) NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE contacts ADD COLUMN IF NOT EXISTS contact_email VARCHAR(255) NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE contacts ADD COLUMN IF NOT EXISTS summary TEXT NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE contacts ADD COLUMN IF NOT EXISTS photo_url TEXT NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE contacts ADD COLUMN IF NOT EXISTS face_embedding TEXT NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE contacts ADD COLUMN IF NOT EXISTS face_consent_at TIMESTAMPTZ")


def downgrade():
    op.execute("ALTER TABLE contacts DROP COLUMN IF EXISTS face_consent_at")
    op.execute("ALTER TABLE contacts DROP COLUMN IF EXISTS face_embedding")
    op.execute("ALTER TABLE contacts DROP COLUMN IF EXISTS photo_url")
    op.execute("ALTER TABLE contacts DROP COLUMN IF EXISTS summary")
    op.execute("ALTER TABLE contacts DROP COLUMN IF EXISTS contact_email")
    op.execute("ALTER TABLE contacts DROP COLUMN IF EXISTS phone")
