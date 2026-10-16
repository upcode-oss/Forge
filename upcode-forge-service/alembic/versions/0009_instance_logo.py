"""Store a custom logo for the Forge instance."""

import sqlalchemy as sa
from sqlalchemy.dialects.mysql import MEDIUMBLOB

from alembic import op

revision = "0009"
down_revision = "0008"


def upgrade():
    op.add_column(
        "instance",
        sa.Column("logo", sa.LargeBinary().with_variant(MEDIUMBLOB(), "mysql"), nullable=True),
    )
    op.add_column("instance", sa.Column("logo_digest", sa.String(64), nullable=True))


def downgrade():
    with op.batch_alter_table("instance") as batch:
        batch.drop_column("logo_digest")
        batch.drop_column("logo")
