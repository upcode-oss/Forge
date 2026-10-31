"""Add optional authenticator-based two-factor authentication."""

import sqlalchemy as sa

from alembic import op

revision = "0010"
down_revision = "0009"


def upgrade():
    inspector = sa.inspect(op.get_bind())
    if "users" not in inspector.get_table_names():
        return
    existing = {column["name"] for column in inspector.get_columns("users")}
    columns = [
        sa.Column("mfa_secret_encrypted", sa.Text(), nullable=True),
        sa.Column("mfa_pending_secret_encrypted", sa.Text(), nullable=True),
        sa.Column("mfa_pending_expires_at", sa.BigInteger(), nullable=True),
        sa.Column("mfa_last_step", sa.BigInteger(), nullable=False, server_default="-1"),
        sa.Column("mfa_recovery_hashes", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("mfa_failed_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("mfa_locked_until", sa.BigInteger(), nullable=True),
    ]
    for column in columns:
        if column.name not in existing:
            op.add_column("users", column)


def downgrade():
    with op.batch_alter_table("users") as batch:
        for name in (
            "mfa_locked_until",
            "mfa_failed_attempts",
            "mfa_recovery_hashes",
            "mfa_last_step",
            "mfa_pending_expires_at",
            "mfa_pending_secret_encrypted",
            "mfa_secret_encrypted",
        ):
            batch.drop_column(name)
