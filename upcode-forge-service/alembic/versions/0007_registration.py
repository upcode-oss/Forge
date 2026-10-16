"""Add administrator-controlled public registration, disabled by default."""

import sqlalchemy as sa

from alembic import op

revision = "0007"
down_revision = "0006"


def upgrade():
    op.add_column(
        "instance",
        sa.Column("registration_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade():
    with op.batch_alter_table("instance") as batch:
        batch.drop_column("registration_enabled")
