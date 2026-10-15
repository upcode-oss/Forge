"""Add editable public profiles without changing existing account email addresses."""

import sqlalchemy as sa

from alembic import op

revision = "0002"
down_revision = "0001"


def upgrade():
    for column in (
        sa.Column("bio", sa.Text(), nullable=False, server_default=""),
        sa.Column("company", sa.String(100), nullable=False, server_default=""),
        sa.Column("location", sa.String(100), nullable=False, server_default=""),
        sa.Column("website", sa.String(500), nullable=False, server_default=""),
        sa.Column("public_email", sa.String(254), nullable=True),
        sa.Column("social_links", sa.Text(), nullable=False, server_default="[]"),
    ):
        op.add_column("users", column)


def downgrade():
    with op.batch_alter_table("users") as batch:
        for name in ("social_links", "public_email", "website", "location", "company", "bio"):
            batch.drop_column(name)
