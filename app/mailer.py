from __future__ import annotations
"""Minimal email sender supporting Resend API and standard SMTP."""
import asyncio
import logging
import smtplib
from email.message import EmailMessage

import httpx

from app import config

logger = logging.getLogger("asistto.mailer")


def is_configured() -> bool:
    if config.RESEND_API_KEY and config.EMAIL_FROM:
        return True
    if config.SMTP_HOST and (config.EMAIL_FROM or config.SMTP_USER):
        return True
    return False


def _send_smtp_sync(to_email: str, subject: str, text_body: str, html_body: str) -> None:
    sender = config.EMAIL_FROM or config.SMTP_USER
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(text_body)
    msg.add_alternative(html_body, subtype="html")

    if config.SMTP_PORT == 465 and not config.SMTP_USE_TLS:
        with smtplib.SMTP_SSL(config.SMTP_HOST, config.SMTP_PORT, timeout=15) as server:
            if config.SMTP_USER and config.SMTP_PASSWORD:
                server.login(config.SMTP_USER, config.SMTP_PASSWORD)
            server.send_message(msg)
        return

    with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=15) as server:
        server.ehlo()
        if config.SMTP_USE_TLS:
            server.starttls()
            server.ehlo()
        if config.SMTP_USER and config.SMTP_PASSWORD:
            server.login(config.SMTP_USER, config.SMTP_PASSWORD)
        server.send_message(msg)


async def send_email(to_email: str, subject: str, text_body: str, html_body: str) -> bool:
    """Sends an email via Resend API or SMTP. Returns True if dispatched."""
    if config.RESEND_API_KEY and config.EMAIL_FROM:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {config.RESEND_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "from": config.EMAIL_FROM,
                    "to": [to_email],
                    "subject": subject,
                    "text": text_body,
                    "html": html_body,
                },
            )
            resp.raise_for_status()
        return True

    if config.SMTP_HOST and (config.EMAIL_FROM or config.SMTP_USER):
        await asyncio.to_thread(_send_smtp_sync, to_email, subject, text_body, html_body)
        return True

    logger.warning(
        "Email not sent to %s: configure RESEND_API_KEY+EMAIL_FROM or SMTP_HOST+EMAIL_FROM.",
        to_email,
    )
    return False
