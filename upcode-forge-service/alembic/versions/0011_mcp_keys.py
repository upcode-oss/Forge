"""Store personal, scoped MCP keys without their plaintext secrets."""

import sqlalchemy as sa

from alembic import op

revision = "0011"
down_revision = "0010"


def upgrade():
    if "mcp_keys" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "mcp_keys",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("digest", sa.String(64), nullable=False, unique=True),
        sa.Column("scopes", sa.Text(), nullable=False),
        sa.Column("password_digest", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_mcp_keys_user_id", "mcp_keys", ["user_id"])


def downgrade():
    op.drop_table("mcp_keys")
