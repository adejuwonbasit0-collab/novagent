from __future__ import annotations

from pydantic import BaseModel, Field


class AssistantNameOut(BaseModel):
    assistant_name: str


class AssistantNameUpdate(BaseModel):
    assistant_name: str = Field(min_length=1, max_length=100)


class PlatformBrandingOut(BaseModel):
    site_name: str
    site_description: str
    logo_url: str | None = None
    favicon_url: str | None = None
    primary_icon_url: str | None = None
    desktop_icon_url: str | None = None
    mobile_icon_url: str | None = None
    footer_text: str | None = None
    seo_title: str | None = None
    seo_description: str | None = None

    theme: str
    accent_color: str

    assistant_name: str
    assistant_greeting: str
    assistant_personality: str
    default_language: str
    default_voice: str


class PlatformBrandingUpdate(BaseModel):
    site_name: str = Field(min_length=1, max_length=100)
    site_description: str = Field(min_length=1, max_length=255)
    logo_url: str | None = None
    favicon_url: str | None = None
    primary_icon_url: str | None = None
    desktop_icon_url: str | None = None
    mobile_icon_url: str | None = None
    footer_text: str | None = None
    seo_title: str | None = None
    seo_description: str | None = None

    theme: str = Field(default="dark", max_length=50)
    accent_color: str = Field(default="#6366f1", max_length=50)

    assistant_name: str = Field(min_length=1, max_length=100)
    assistant_greeting: str = Field(min_length=1, max_length=255)
    assistant_personality: str = Field(min_length=1, max_length=2000)
    default_language: str = Field(default="en-US", max_length=50)
    default_voice: str = Field(default="neutral", max_length=100)