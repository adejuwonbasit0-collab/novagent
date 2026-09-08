from __future__ import annotations

import uuid
from datetime import datetime
from pydantic import BaseModel, Field


class PhishingCheckRequest(BaseModel):
    text_content: str = Field(min_length=1, max_length=50000, description="Email body or message text to analyze")
    sender_info: str | None = Field(default=None, max_length=500, description="Sender email or address if available")
    urls: list[str] = Field(default_factory=list, description="Extracted links or URLs to evaluate")


class PhishingIndicator(BaseModel):
    category: str  # e.g., "Suspicious Link", "Urgency/Coercion", "Credential Request", "Spoofed Domain"
    severity: str  # "LOW" | "MEDIUM" | "HIGH" | "CRITICAL"
    description: str


class PhishingCheckResponse(BaseModel):
    risk_level: str  # "LOW" | "MEDIUM" | "HIGH" | "CRITICAL"
    risk_score: int  # 0 to 100
    summary: str
    indicators: list[PhishingIndicator]
    recommendations: list[str]


class FraudCheckRequest(BaseModel):
    transaction_or_message: str = Field(min_length=1, max_length=50000, description="Invoice, payment request, or conversation text")
    amount: str | None = None
    recipient: str | None = None


class FraudIndicator(BaseModel):
    category: str  # e.g. "Unusual Payment Method", "Impersonation", "Urgent Wire Request"
    severity: str
    description: str


class FraudCheckResponse(BaseModel):
    risk_level: str  # "LOW" | "MEDIUM" | "HIGH" | "CRITICAL"
    risk_score: int  # 0 to 100
    is_confirmed_fraud: bool  # False unless unequivocal proof
    summary: str
    indicators: list[FraudIndicator]
    recommendations: list[str]


class SecurityEventOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID | None
    device_id: uuid.UUID | None
    event_type: str
    risk_level: str
    risk_score: int
    ip_address: str | None
    user_agent: str | None
    location_summary: str | None
    description: str
    details_json: str | None
    created_at: datetime


class SecurityStatsOut(BaseModel):
    total_events: int
    failed_logins_24h: int
    active_threats: int
    threat_score_avg: float
