"""Outbound email via a plain SMTP relay (the org's own mail server) -
stdlib smtplib only, no third-party mail SDK. Deliberately synchronous
(matches every other service in this codebase); FastAPI runs a sync `def`
route in its threadpool automatically, so this never blocks the event loop.
"""
import smtplib
from email.message import EmailMessage

from fastapi import HTTPException, status

from app.core.config import settings


def send_email_with_attachment(
    *, to_email: str, subject: str, body: str, attachment_bytes: bytes, attachment_filename: str, attachment_mime: str = "application/pdf",
):
    if not settings.SMTP_HOST or not settings.SMTP_FROM_EMAIL:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Email sending isn't configured on this server - set EXPMS_SMTP_HOST and EXPMS_SMTP_FROM_EMAIL (see .env.example).",
        )

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM_EMAIL}>" if settings.SMTP_FROM_NAME else settings.SMTP_FROM_EMAIL
    msg["To"] = to_email
    msg.set_content(body)

    maintype, _, subtype = attachment_mime.partition("/")
    msg.add_attachment(attachment_bytes, maintype=maintype or "application", subtype=subtype or "octet-stream", filename=attachment_filename)

    try:
        if settings.SMTP_USE_SSL:
            with smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT, timeout=20) as server:
                if settings.SMTP_USERNAME:
                    server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
                server.send_message(msg)
        else:
            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=20) as server:
                server.starttls()
                if settings.SMTP_USERNAME:
                    server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
                server.send_message(msg)
    except (smtplib.SMTPException, OSError) as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Could not send email: {exc}")
