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

# Brand colours
_TEAL = "#27777F"
_TEAL_LIGHT = "#329FAE"
_GREEN = "#12B76A"
_BG = "#F9FAFB"
_CARD = "#FFFFFF"
_TEXT = "#1D2939"
_MUTED = "#667085"


def _base(body_html: str) -> str:
    """Wrap body_html in a responsive, styled email shell."""
    return f"""\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>ALRI</title>
</head>
<body style="margin:0;padding:0;background:{_BG};font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" role="presentation" style="background:{_BG};">
<tr><td align="center" style="padding:40px 16px;">

<!-- Card -->
<table width="100%" cellpadding="0" cellspacing="0" role="presentation"
       style="max-width:520px;background:{_CARD};border-radius:16px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,.08);">

  <!-- Header bar -->
  <tr>
    <td style="background:linear-gradient(135deg,{_TEAL},{_TEAL_LIGHT});padding:28px 32px;text-align:center;">
      <span style="font-size:22px;font-weight:700;color:#fff;letter-spacing:0.5px;">ALRI</span>
    </td>
  </tr>

  <!-- Body -->
  <tr>
    <td style="padding:32px;color:{_TEXT};font-size:15px;line-height:1.6;">
      {body_html}
    </td>
  </tr>

  <!-- Footer -->
  <tr>
    <td style="padding:20px 32px;border-top:1px solid #F2F4F7;text-align:center;">
      <p style="margin:0 0 4px;font-size:12px;color:{_MUTED};">
        ALRI — Automated Lab Result Interpreter
      </p>
      <p style="margin:0;font-size:11px;color:{_MUTED};">
        This is not a substitute for professional medical advice, diagnosis, or treatment.
      </p>
    </td>
  </tr>

</table>
<!-- /Card -->

</td></tr>
</table>
</body>
</html>"""


def _button(url: str, label: str) -> str:
    """Render a teal CTA button."""
    return (
        f'<table cellpadding="0" cellspacing="0" role="presentation" style="margin:24px auto;">'
        f'<tr><td style="background:{_TEAL};border-radius:8px;">'
        f'<a href="{url}" target="_blank" '
        f'style="display:inline-block;padding:12px 28px;color:#fff;font-size:14px;'
        f'font-weight:600;text-decoration:none;">{label}</a>'
        f"</td></tr></table>"
    )


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


# ---------------------------------------------------------------------------
# Welcome
# ---------------------------------------------------------------------------

async def send_welcome(to: str, name: str | None = None) -> dict | None:
    """Send welcome email from hello@alri.health."""
    display = name or "there"
    body = f"""\
<h2 style="margin:0 0 8px;font-size:20px;color:{_TEXT};">Welcome to ALRI!</h2>
<p style="margin:0 0 20px;color:{_MUTED};font-size:14px;">Your personal lab report interpreter</p>

<p>Hi {display},</p>
<p>Thanks for joining <strong>ALRI</strong>. We make it easy to understand your lab results with
AI-powered, plain-language explanations.</p>

<table cellpadding="0" cellspacing="0" role="presentation"
       style="width:100%;background:#F0FDF9;border-radius:12px;margin:20px 0;">
<tr><td style="padding:20px 24px;text-align:center;">
  <p style="margin:0 0 4px;font-size:13px;color:{_MUTED};">Your starting balance</p>
  <p style="margin:0;font-size:28px;font-weight:700;color:{_GREEN};">\u20a65,000</p>
  <p style="margin:4px 0 0;font-size:12px;color:{_MUTED};">That\u2019s up to 10 full report unlocks</p>
</td></tr>
</table>

<p>Upload a lab report or type your values to get started:</p>

{_button(settings.APP_URL + "/scan", "Start Your First Scan")}

<p style="font-size:13px;color:{_MUTED};margin-top:24px;">
Each full report unlock costs \u20a6500, deducted from your balance.
You can top up anytime from your dashboard.
</p>"""

    return await _send(
        f"ALRI <{settings.RESEND_FROM_HELLO}>",
        to,
        "Welcome to ALRI \U0001f52c",
        _base(body),
    )


# ---------------------------------------------------------------------------
# Report ready
# ---------------------------------------------------------------------------

async def send_report(to: str, scan_id: str, summary: str) -> dict | None:
    """Send scan report link from hello@alri.health."""
    safe_summary = summary.replace("<", "&lt;").replace(">", "&gt;") if summary else ""
    body = f"""\
<h2 style="margin:0 0 8px;font-size:20px;color:{_TEXT};">Your Lab Results Are Ready</h2>
<p style="margin:0 0 20px;color:{_MUTED};font-size:14px;">We\u2019ve finished analysing your report</p>

<table cellpadding="0" cellspacing="0" role="presentation"
       style="width:100%;background:{_BG};border:1px solid #F2F4F7;border-radius:12px;margin:16px 0;">
<tr><td style="padding:16px 20px;font-size:14px;color:{_TEXT};line-height:1.6;">
  {safe_summary}
</td></tr>
</table>

{_button(settings.APP_URL + "/dashboard/results/" + scan_id, "View Full Results")}"""

    return await _send(
        f"ALRI <{settings.RESEND_FROM_HELLO}>",
        to,
        "Your Lab Results Are Ready \U0001f4ca",
        _base(body),
    )


# ---------------------------------------------------------------------------
# Payment receipt
# ---------------------------------------------------------------------------

async def send_payment_receipt(
    to: str, amount: int, currency: str = "NGN"
) -> dict | None:
    """Send payment receipt from billing@alri.health. *amount* is in kobo."""
    naira = amount / 100
    body = f"""\
<h2 style="margin:0 0 8px;font-size:20px;color:{_TEXT};">Payment Received</h2>
<p style="margin:0 0 20px;color:{_MUTED};font-size:14px;">Thanks for topping up your ALRI account</p>

<table cellpadding="0" cellspacing="0" role="presentation"
       style="width:100%;background:{_BG};border:1px solid #F2F4F7;border-radius:12px;margin:16px 0;">
<tr><td style="padding:20px 24px;">
  <table width="100%" cellpadding="0" cellspacing="0" role="presentation">
    <tr>
      <td style="font-size:13px;color:{_MUTED};padding-bottom:8px;">Amount paid</td>
      <td align="right" style="font-size:16px;font-weight:600;color:{_TEXT};padding-bottom:8px;">
        {currency} {naira:,.2f}
      </td>
    </tr>
    <tr>
      <td style="font-size:13px;color:{_MUTED};">Credits added</td>
      <td align="right" style="font-size:16px;font-weight:600;color:{_GREEN};">
        \u20a6{naira:,.0f}
      </td>
    </tr>
  </table>
</td></tr>
</table>

{_button(settings.APP_URL + "/dashboard", "Go to Dashboard")}"""

    return await _send(
        f"ALRI Billing <{settings.RESEND_FROM_BILLING}>",
        to,
        "Payment Received \u2705",
        _base(body),
    )
