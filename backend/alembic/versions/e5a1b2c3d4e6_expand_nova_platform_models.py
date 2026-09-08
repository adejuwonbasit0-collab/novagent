"""expand nova platform models

Revision ID: e5a1b2c3d4e6
Revises: d4f8a2b6c1e0
Create Date: 2026-09-08 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "e5a1b2c3d4e6"
down_revision: Union[str, Sequence[str], None] = "d4f8a2b6c1e0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Expand platform_settings table
    with op.batch_alter_table("platform_settings", schema=None) as batch_op:
        batch_op.add_column(sa.Column("site_name", sa.String(length=100), nullable=False, server_default="Nova"))
        batch_op.add_column(sa.Column("site_description", sa.String(length=255), nullable=False, server_default="Personal AI Operating Assistant Platform"))
        batch_op.add_column(sa.Column("logo_url", sa.String(length=500), nullable=True))
        batch_op.add_column(sa.Column("favicon_url", sa.String(length=500), nullable=True))
        batch_op.add_column(sa.Column("primary_icon_url", sa.String(length=500), nullable=True))
        batch_op.add_column(sa.Column("desktop_icon_url", sa.String(length=500), nullable=True))
        batch_op.add_column(sa.Column("mobile_icon_url", sa.String(length=500), nullable=True))
        batch_op.add_column(sa.Column("footer_text", sa.String(length=255), nullable=True, server_default="© 2026 Nova Assistant Platform. All rights reserved."))
        batch_op.add_column(sa.Column("seo_title", sa.String(length=150), nullable=True, server_default="Nova — Personal AI Operating Assistant"))
        batch_op.add_column(sa.Column("seo_description", sa.String(length=300), nullable=True, server_default="Nova is a unified AI operating assistant across desktop, browser, and mobile."))
        batch_op.add_column(sa.Column("theme", sa.String(length=50), nullable=False, server_default="dark"))
        batch_op.add_column(sa.Column("accent_color", sa.String(length=50), nullable=False, server_default="#6366f1"))
        batch_op.add_column(sa.Column("assistant_greeting", sa.String(length=255), nullable=False, server_default="Hello! How can I assist you today?"))
        batch_op.add_column(sa.Column("assistant_personality", sa.String(length=2000), nullable=False, server_default="You are Nova, an efficient, trustworthy, concise, and helpful personal AI operating assistant."))
        batch_op.add_column(sa.Column("default_language", sa.String(length=50), nullable=False, server_default="en-US"))
        batch_op.add_column(sa.Column("default_voice", sa.String(length=100), nullable=False, server_default="neutral"))

    # 2. Create conversations table
    op.create_table(
        "conversations",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("title", sa.String(length=255), nullable=False, server_default="New Conversation"),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("last_message_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )

    # 3. Create messages table
    op.create_table(
        "messages",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("conversation_id", sa.UUID(as_uuid=True), sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("role", sa.String(length=50), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("tool_calls_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )

    # 4. Create security_events table
    op.create_table(
        "security_events",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("device_id", sa.UUID(as_uuid=True), sa.ForeignKey("devices.id", ondelete="SET NULL"), nullable=True),
        sa.Column("event_type", sa.String(length=50), nullable=False, index=True),
        sa.Column("risk_level", sa.String(length=20), nullable=False, server_default="LOW"),
        sa.Column("risk_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ip_address", sa.String(length=64), nullable=True, index=True),
        sa.Column("user_agent", sa.String(length=255), nullable=True),
        sa.Column("location_summary", sa.String(length=100), nullable=True),
        sa.Column("description", sa.String(length=255), nullable=False),
        sa.Column("details_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False, index=True),
    )


def downgrade() -> None:
    op.drop_table("security_events")
    op.drop_table("messages")
    op.drop_table("conversations")
    with op.batch_alter_table("platform_settings", schema=None) as batch_op:
        batch_op.drop_column("default_voice")
        batch_op.drop_column("default_language")
        batch_op.drop_column("assistant_personality")
        batch_op.drop_column("assistant_greeting")
        batch_op.drop_column("accent_color")
        batch_op.drop_column("theme")
        batch_op.drop_column("seo_description")
        batch_op.drop_column("seo_title")
        batch_op.drop_column("footer_text")
        batch_op.drop_column("mobile_icon_url")
        batch_op.drop_column("desktop_icon_url")
        batch_op.drop_column("primary_icon_url")
        batch_op.drop_column("favicon_url")
        batch_op.drop_column("logo_url")
        batch_op.drop_column("site_description")
        batch_op.drop_column("site_name")
