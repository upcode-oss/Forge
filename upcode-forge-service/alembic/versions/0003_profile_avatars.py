"""Store normalized profile pictures with their accounts."""

import sqlalchemy as sa
from sqlalchemy.dialects.mysql import MEDIUMBLOB

from alembic import op

revision = "0003"
down_revision = "0002"


def upgrade():
    op.add_column(
        "users",
        sa.Column("avatar", sa.LargeBinary().with_variant(MEDIUMBLOB(), "mysql"), nullable=True),
    )
    op.add_column("users", sa.Column("avatar_digest", sa.String(64), nullable=True))


def downgrade():
    with op.batch_alter_table("users") as batch:
        batch.drop_column("avatar_digest")
        batch.drop_column("avatar")
