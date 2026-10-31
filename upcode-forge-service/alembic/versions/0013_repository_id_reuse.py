"""Never reuse Git storage identities after repository deletion on SQLite."""

import sqlalchemy as sa

from alembic import op

revision = "0013"
down_revision = "0012"


def upgrade():
    connection = op.get_bind()
    if connection.dialect.name != "sqlite":
        return
    if "repositories" not in sa.inspect(connection).get_table_names():
        return
    definition = connection.scalar(
        sa.text("SELECT sql FROM sqlite_master WHERE name = 'repositories'")
    )
    if "AUTOINCREMENT" not in definition.upper():
        with op.batch_alter_table(
            "repositories", recreate="always", table_kwargs={"sqlite_autoincrement": True}
        ):
            pass


def downgrade():
    connection = op.get_bind()
    if (
        connection.dialect.name == "sqlite"
        and "repositories" in sa.inspect(connection).get_table_names()
    ):
        with op.batch_alter_table(
            "repositories", recreate="always", table_kwargs={"sqlite_autoincrement": False}
        ):
            pass
