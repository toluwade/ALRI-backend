"""Email service via Resend.

- hello@alri.health → welcome emails, report delivery
- billing@alri.health → payment receipts, credit notifications
"""
from __future__ import annotations

import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

RESEND_API = "https://api.resend.com/emails"


async def _send(from_addr: str, to: str, subject: str, html: str) -> dict | None:
    if not settings.RESEND_API_KEY:
        logger.warning("RESEND_API_KEY not set — skipping email to %s", to)
        return None

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            RESEND_API,
            headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}"},
            json={
                "from": from_addr,
                "to": [to],
                "subject": subject,
                "html": html,
            },
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()


async def send_welcome(to: str, name: str | None = None) -> dict | None:
    """Send welcome email from hello@alri.health."""
    display = name or "there"
    html = f"""
    <h2>Welcome to ALRI! 🔬</h2>
    <p>Hi {display},</p>
    <p>You've just joined <strong>ALRI — Automated Lab Result Interpreter</strong>.</p>
    <p>Upload any lab report and get instant, plain-language explanations of your results.</p>
    <p>You have <strong>5 free credits</strong> to get started.</p>
    <br>
    <p>Stay healthy,<br>The ALRI Team</p>
    <hr><small>This is not medical advice. Always consult a healthcare provider.</small>
    """
    return await _send(
        f"ALRI <{settings.RESEND_FROM_HELLO}>", to, "Welcome to ALRI 🔬", html
    )


async def send_report(to: str, scan_id: str, summary: str) -> dict | None:
    """Send scan report link from hello@alri.health."""
    html = f"""
    <h2>Your Lab Results Are Ready 📊</h2>
    <p>Your scan has been processed. Here's a quick summary:</p>
    <blockquote>{summary}</blockquote>
    <p><a href="{settings.APP_URL}/scan/{scan_id}">View Full Results →</a></p>
    <br>
    <p>Stay healthy,<br>The ALRI Team</p>
    <hr><small>This is not medical advice. Always consult a healthcare provider.</small>
    """
    return await _send(
        f"ALRI <{settings.RESEND_FROM_HELLO}>", to, "Your Lab Results Are Ready 📊", html
    )


async def send_payment_receipt(
    to: str, amount: int, currency: str = "NGN", credits: int = 0
) -> dict | None:
    """Send payment receipt from billing@alri.health."""
    html = f"""
    <h2>Payment Received ✅</h2>
    <p>Thank you! We received your payment of <strong>{currency} {amount / 100:,.2f}</strong>.</p>
    <p><strong>{credits} credits</strong> have been added to your account.</p>
    <p><a href="{settings.APP_URL}/dashboard">Go to Dashboard →</a></p>
    <br>
    <p>The ALRI Team</p>
    """
    return await _send(
        f"ALRI Billing <{settings.RESEND_FROM_BILLING}>",
        to,
        "Payment Received ✅",
        html,
    )
