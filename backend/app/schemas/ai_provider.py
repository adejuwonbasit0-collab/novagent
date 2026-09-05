from pydantic import BaseModel, Field

from app.models.ai_provider import AIProvider


class AIProviderSettingsOut(BaseModel):
    provider: AIProvider
    model: str
    base_url: str | None
    has_api_key: bool
    enabled: bool


class AIProviderSettingsUpdate(BaseModel):
    provider: AIProvider
    model: str = Field(min_length=1, max_length=150)
    base_url: str | None = Field(default=None, max_length=500)
    api_key: str | None = Field(default=None, max_length=500)
    enabled: bool = True