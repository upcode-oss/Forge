"""Allow repositories to belong to a user or organization."""

import sqlalchemy as sa

from alembic import op

revision = "0006"
down_revision = "0005"


def upgrade():
    with op.batch_alter_table("repositories") as batch:
        batch.alter_column("owner_id", existing_type=sa.Integer(), nullable=True)
        batch.add_column(sa.Column("organization_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("created_by_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_repositories_organization", "organizations", ["organization_id"], ["id"]
        )
        batch.create_foreign_key("fk_repositories_creator", "users", ["created_by_id"], ["id"])
        batch.create_unique_constraint(
            "uq_repositories_organization_name", ["organization_id", "name"]
        )
        batch.create_check_constraint(
            "ck_repositories_single_owner",
            "(owner_id IS NOT NULL AND organization_id IS NULL) OR (owner_id IS NULL AND organization_id IS NOT NULL)",
        )
        batch.create_index("ix_repositories_organization_id", ["organization_id"])
    op.execute("UPDATE repositories SET created_by_id = owner_id")


def downgrade():
    if op.get_bind().scalar(
        sa.text("SELECT COUNT(*) FROM repositories WHERE organization_id IS NOT NULL")
    ):
        raise RuntimeError("Organization repositories must be removed before downgrading")
    with op.batch_alter_table("repositories") as batch:
        batch.drop_index("ix_repositories_organization_id")
        batch.drop_constraint("ck_repositories_single_owner", type_="check")
        batch.drop_constraint("uq_repositories_organization_name", type_="unique")
        batch.drop_constraint("fk_repositories_organization", type_="foreignkey")
        batch.drop_constraint("fk_repositories_creator", type_="foreignkey")
        batch.drop_column("organization_id")
        batch.drop_column("created_by_id")
        batch.alter_column("owner_id", existing_type=sa.Integer(), nullable=False)
