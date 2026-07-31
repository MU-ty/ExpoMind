"""add WeChat identity

Revision ID: 20260730_02
Revises: 20260730_01
"""
from alembic import op

revision = "20260730_02"
down_revision = "20260730_01"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS wechat_openid VARCHAR(128)")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_wechat_openid ON users(wechat_openid) WHERE wechat_openid IS NOT NULL")


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_users_wechat_openid")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS wechat_openid")
