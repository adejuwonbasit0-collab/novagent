"""add speaker verification profiles"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b7d4e91a2c3f"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "speaker_profiles",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("UNTRAINED", "READY", name="speaker_profile_status"),
            nullable=False,
        ),
        sa.Column("embedding", sa.JSON(), nullable=True),
        sa.Column("sample_count", sa.Integer(), nullable=False),
        sa.Column("threshold", sa.Float(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_speaker_profiles_user_id"), "speaker_profiles", ["user_id"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_speaker_profiles_user_id"), table_name="speaker_profiles")
    op.drop_table("speaker_profiles")
    op.execute("DROP TYPE speaker_profile_status")
