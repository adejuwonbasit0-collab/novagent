"""add admin-managed ai provider settings"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "6c3f8db3a1aa"
down_revision: Union[str, None] = "ef28d5e84add"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ai_provider_settings",
        sa.Column("provider", sa.Enum("ANTHROPIC", "OPENAI", "OPENROUTER", "GROQ", "GEMINI", "CUSTOM", name="ai_provider"), nullable=False),
        sa.Column("model", sa.String(length=150), nullable=False),
        sa.Column("base_url", sa.String(length=500), nullable=True),
        sa.Column("encrypted_api_key", sa.Text(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("ai_provider_settings")
    op.execute("DROP TYPE ai_provider")