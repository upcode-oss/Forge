"""Keep MCP disabled until an administrator explicitly enables it."""

import sqlalchemy as sa

from alembic import op

revision = "0012"
down_revision = "0011"


def upgrade():
    inspector = sa.inspect(op.get_bind())
    if "instance" not in inspector.get_table_names():
        return
    if "mcp_enabled" not in {column["name"] for column in inspector.get_columns("instance")}:
        op.add_column(
            "instance",
            sa.Column("mcp_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        )


def downgrade():
    with op.batch_alter_table("instance") as batch:
        batch.drop_column("mcp_enabled")
