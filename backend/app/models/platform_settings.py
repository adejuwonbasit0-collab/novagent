from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.mixins import TimestampMixin, UUIDPKMixin


class PlatformSettings(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "platform_settings"

    # Branding & CMS
    site_name: Mapped[str] = mapped_column(String(100), nullable=False, default="Nova")
    site_description: Mapped[str] = mapped_column(String(255), nullable=False, default="Personal AI Operating Assistant Platform")
    logo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    favicon_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    primary_icon_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    desktop_icon_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    mobile_icon_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    footer_text: Mapped[str | None] = mapped_column(String(255), nullable=True, default="© 2026 Nova Assistant Platform. All rights reserved.")
    seo_title: Mapped[str | None] = mapped_column(String(150), nullable=True, default="Nova — Personal AI Operating Assistant")
    seo_description: Mapped[str | None] = mapped_column(String(300), nullable=True, default="Nova is a unified AI operating assistant across desktop, browser, and mobile.")

    # Theme & Visuals
    theme: Mapped[str] = mapped_column(String(50), nullable=False, default="dark")
    accent_color: Mapped[str] = mapped_column(String(50), nullable=False, default="#6366f1")

    # Assistant Persona & Runtime Behavior
    assistant_name: Mapped[str] = mapped_column(String(100), nullable=False, default="Nova")
    assistant_greeting: Mapped[str] = mapped_column(String(255), nullable=False, default="Hello! How can I assist you today?")
    assistant_personality: Mapped[str] = mapped_column(
        String(2000),
        nullable=False,
        default="You are Nova, an efficient, trustworthy, concise, and helpful personal AI operating assistant."
    )
    default_language: Mapped[str] = mapped_column(String(50), nullable=False, default="en-US")
    default_voice: Mapped[str] = mapped_column(String(100), nullable=False, default="neutral")