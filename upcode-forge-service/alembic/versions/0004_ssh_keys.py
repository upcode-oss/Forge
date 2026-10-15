"""Add user SSH public keys for Git authentication."""

import sqlalchemy as sa

from alembic import op

revision = "0004"
down_revision = "0003"


def upgrade():
    op.create_table(
        "ssh_keys",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("public_key", sa.Text(), nullable=False),
        sa.Column("fingerprint", sa.String(80), unique=True, nullable=False),
        sa.Column("scope", sa.String(10), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_ssh_keys_user_id", "ssh_keys", ["user_id"])


def downgrade():
    op.drop_table("ssh_keys")
