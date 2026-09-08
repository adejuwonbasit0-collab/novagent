from __future__ import annotations

import re
import json
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.security_event import SecurityEvent, SecurityEventType, SecurityRiskLevel
from app.models.user import User
from app.schemas.security import (
    FraudCheckRequest,
    FraudCheckResponse,
    FraudIndicator,
    PhishingCheckRequest,
    PhishingCheckResponse,
    PhishingIndicator,
    SecurityEventOut,
    SecurityStatsOut,
)

router = APIRouter(prefix="/api/v1/security", tags=["security"])

_SUSPICIOUS_DOMAINS = ["bit.ly", "tinyurl.com", "is.gd", "t.co", "account-update-security.com", "secure-login-verify.net"]
_URGENT_PHRASES = [
    r"account\s+(?:suspended|locked|terminated|disabled)",
    r"immediate\s+action\s+required",
    r"verify\s+your\s+identity\s+within\s+\d+\s+(?:hours|minutes)",
    r"unauthorized\s+login\s+attempt",
    r"click\s+here\s+immediately",
    r"confirm\s+your\s+password",
    r"update\s+payment\s+details\s+now",
    r"wire\s+transfer\s+urgently",
    r"gift\s+cards?",
    r"overdue\s+invoice\s+payment",
]


def _analyze_phishing(text: str, sender: str | None, urls: list[str]) -> tuple[str, int, list[PhishingIndicator], list[str]]:
    indicators: list[PhishingIndicator] = []
    score = 0
    lowered_text = text.lower()

    # 1. Check for urgency / coercion
    for pattern in _URGENT_PHRASES:
        if re.search(pattern, lowered_text):
            indicators.append(
                PhishingIndicator(
                    category="Urgency / Psychological Manipulation",
                    severity="HIGH",
                    description=f"Detected pressure tactic matching pattern '{pattern}'",
                )
            )
            score += 25
            break

    # 2. Check for credential harvesting words
    if any(k in lowered_text for k in ["enter your password", "login credentials", "verify passcode", "ssn", "social security", "pin code"]):
        indicators.append(
            PhishingIndicator(
                category="Credential Harvesting",
                severity="CRITICAL",
                description="Message explicitly solicits sensitive credentials, passwords, or security PINs.",
            )
        )
        score += 35

    # 3. Analyze URLs
    for url in urls:
        lowered_url = url.lower()
        if any(dom in lowered_url for dom in _SUSPICIOUS_DOMAINS):
            indicators.append(
                PhishingIndicator(
                    category="Suspicious / Obfuscated Link",
                    severity="HIGH",
                    description=f"Contains shortened or obfuscated link: {url}",
                )
            )
            score += 25
        if re.search(r"https?://\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}", lowered_url):
            indicators.append(
                PhishingIndicator(
                    category="Direct IP Address Link",
                    severity="CRITICAL",
                    description=f"Direct IP link found bypassing domain reputation: {url}",
                )
            )
            score += 30

    # 4. Check sender anomaly if provided
    if sender:
        lowered_sender = sender.lower()
        if any(free in lowered_sender for free in ["@gmail.com", "@yahoo.com", "@hotmail.com"]) and any(
            corp in lowered_text for corp in ["bank of america", "paypal", "microsoft security", "apple support", "google support"]
        ):
            indicators.append(
                PhishingIndicator(
                    category="Sender Domain Mismatch (Spoofing)",
                    severity="CRITICAL",
                    description=f"Corporate service claimed in body but sent from public mailbox: {sender}",
                )
            )
            score += 40

    score = min(100, score)
    if score >= 60:
        level = "HIGH" if score < 85 else "CRITICAL"
    elif score >= 25:
        level = "MEDIUM"
    else:
        level = "LOW"

    recommendations = []
    if score >= 25:
        recommendations.append("Do NOT click links or download attachments in this message.")
        recommendations.append("Verify the sender's identity through an independent, trusted channel.")
    if score >= 60:
        recommendations.append("Report this message to your security team or mail provider.")
        recommendations.append("If you already entered credentials, immediately change passwords and enable MFA.")
    if not recommendations:
        recommendations.append("No obvious phishing patterns detected. Practice standard cyber vigilance.")

    return level, score, indicators, recommendations


def _analyze_fraud(text: str, amount: str | None, recipient: str | None) -> tuple[str, int, bool, list[FraudIndicator], list[str]]:
    indicators: list[FraudIndicator] = []
    score = 0
    lowered_text = text.lower()

    # 1. Wire transfer / untraceable payment requests
    if any(p in lowered_text for p in ["wire transfer", "western union", "moneygram", "crypto", "bitcoin", "gift cards", "apple gift card"]):
        indicators.append(
            FraudIndicator(
                category="Untraceable / Irreversible Payment Method",
                severity="HIGH",
                description="Requests non-standard or irreversible payment methods (crypto, wire transfer, gift cards).",
            )
        )
        score += 35

    # 2. Changed bank details / updated routing numbers
    if any(p in lowered_text for p in ["new bank account", "updated routing number", "changed our banking details", "payment details changed"]):
        indicators.append(
            FraudIndicator(
                category="Vendor Impersonation / Bank Account Modification",
                severity="CRITICAL",
                description="Claims vendor bank account details have changed — classic Business Email Compromise (BEC) indicator.",
            )
        )
        score += 45

    # 3. Urgency regarding payments
    if any(p in lowered_text for p in ["pay immediately to avoid penalties", "strictly confidential payment", "do not tell anyone"]):
        indicators.append(
            FraudIndicator(
                category="Executive Impersonation / Secrecy Pressure",
                severity="HIGH",
                description="Urges secrecy or immediate payment execution bypassing approval processes.",
            )
        )
        score += 30

    score = min(100, score)
    level = "LOW"
    if score >= 70:
        level = "CRITICAL"
    elif score >= 40:
        level = "HIGH"
    elif score >= 20:
        level = "MEDIUM"

    is_confirmed = False  # Always an indicator unless confirmed by human review
    recommendations = [
        "Do not issue funds until secondary verbal confirmation is obtained using a known phone number on file.",
        "Inspect the invoice formatting, tax IDs, and compare against historical purchase orders.",
    ]
    if score < 20:
        recommendations = ["Transaction text appears normal. Maintain standard accounting validation controls."]

    return level, score, is_confirmed, indicators, recommendations


@router.post("/phishing-check", response_model=PhishingCheckResponse)
async def check_phishing(
    payload: PhishingCheckRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    level, score, indicators, recommendations = _analyze_phishing(
        payload.text_content, payload.sender_info, payload.urls
    )

    summary = (
        f"Phishing analysis complete: {level} risk detected (Risk Score: {score}/100) with "
        f"{len(indicators)} flagged indicator(s)."
    )

    # Log security event
    event = SecurityEvent(
        user_id=current_user.id,
        event_type=SecurityEventType.PHISHING_ANALYSIS,
        risk_level=SecurityRiskLevel(level),
        risk_score=score,
        description=f"Phishing analysis requested: {level} risk ({score}/100)",
        details_json=json.dumps({"indicators_count": len(indicators), "urls_analyzed": len(payload.urls)}),
    )
    db.add(event)
    await db.commit()

    return PhishingCheckResponse(
        risk_level=level,
        risk_score=score,
        summary=summary,
        indicators=indicators,
        recommendations=recommendations,
    )


@router.post("/fraud-check", response_model=FraudCheckResponse)
async def check_fraud(
    payload: FraudCheckRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    level, score, is_confirmed, indicators, recommendations = _analyze_fraud(
        payload.transaction_or_message, payload.amount, payload.recipient
    )

    summary = (
        f"Fraud pattern check complete: {level} risk ({score}/100). "
        f"{'Elevated risk patterns identified.' if score >= 40 else 'No high-risk fraud patterns detected.'}"
    )

    event = SecurityEvent(
        user_id=current_user.id,
        event_type=SecurityEventType.FRAUD_ANALYSIS,
        risk_level=SecurityRiskLevel(level),
        risk_score=score,
        description=f"Fraud risk evaluation: {level} risk ({score}/100)",
        details_json=json.dumps({"amount": payload.amount, "recipient": payload.recipient, "indicators_count": len(indicators)}),
    )
    db.add(event)
    await db.commit()

    return FraudCheckResponse(
        risk_level=level,
        risk_score=score,
        is_confirmed_fraud=is_confirmed,
        summary=summary,
        indicators=indicators,
        recommendations=recommendations,
    )


@router.get("/ip-audit", response_model=list[SecurityEventOut])
async def get_ip_audit_log(
    limit: int = Query(default=50, ge=1, le=200),
    event_type: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(SecurityEvent).where(SecurityEvent.user_id == current_user.id)
    if event_type:
        query = query.where(SecurityEvent.event_type == event_type)
    query = query.order_by(desc(SecurityEvent.created_at)).limit(limit)

    result = await db.execute(query)
    events = result.scalars().all()
    return events


@router.get("/stats", response_model=SecurityStatsOut)
async def get_security_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    now = datetime.now(timezone.utc)
    day_ago = now - timedelta(hours=24)

    # Total events
    tot_res = await db.execute(select(func.count(SecurityEvent.id)).where(SecurityEvent.user_id == current_user.id))
    total_events = tot_res.scalar_one() or 0

    # Failed logins in 24h
    fl_res = await db.execute(
        select(func.count(SecurityEvent.id)).where(
            SecurityEvent.user_id == current_user.id,
            SecurityEvent.event_type == SecurityEventType.LOGIN_FAILED,
            SecurityEvent.created_at >= day_ago,
        )
    )
    failed_logins = fl_res.scalar_one() or 0

    # Active threats (events with HIGH or CRITICAL risk)
    threat_res = await db.execute(
        select(func.count(SecurityEvent.id)).where(
            SecurityEvent.user_id == current_user.id,
            SecurityEvent.risk_score >= 50,
        )
    )
    active_threats = threat_res.scalar_one() or 0

    # Average score
    avg_res = await db.execute(select(func.avg(SecurityEvent.risk_score)).where(SecurityEvent.user_id == current_user.id))
    avg_score = float(avg_res.scalar_one() or 0.0)

    return SecurityStatsOut(
        total_events=total_events,
        failed_logins_24h=failed_logins,
        active_threats=active_threats,
        threat_score_avg=round(avg_score, 1),
    )
