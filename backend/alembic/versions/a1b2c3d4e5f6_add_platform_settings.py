"""add global platform settings"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "6c3f8db3a1aa"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "platform_settings",
        sa.Column("assistant_name", sa.String(length=100), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    # Generated in Python and parametrized rather than calling
    # gen_random_uuid() in raw SQL -- that function is Postgres-only
    # (pgcrypto), and this migration otherwise runs cleanly on SQLite too
    # (sa.UUID() is the generic 2.0 type, not the postgres-specific one).
    import uuid

    platform_settings = sa.table(
        "platform_settings", sa.column("id", sa.UUID()), sa.column("assistant_name", sa.String())
    )
    op.execute(platform_settings.insert().values(id=uuid.uuid4(), assistant_name="Nova"))


def downgrade() -> None:
    op.drop_table("platform_settings")