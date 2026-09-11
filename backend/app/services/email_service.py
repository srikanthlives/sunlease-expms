"""Outbound email via a plain SMTP relay (the org's own mail server) -
stdlib smtplib only, no third-party mail SDK. Deliberately synchronous
(matches every other service in this codebase); FastAPI runs a sync `def`
route in its threadpool automatically, so this never blocks the event loop.

Diagnostics use plain print(..., flush=True) with an [EMAIL] prefix -
matching this app's existing [STARTUP]/[INFO]/[WARNING] convention (see
services/storage.py, main.py) - rather than the stdlib `logging` module,
which nothing in this codebase configures a handler/level for and would
silently drop INFO-level messages. flush=True is belt-and-suspenders on
top of the Dockerfile's PYTHONUNBUFFERED=1, so these always reach the
platform's log collector (Railway, etc) immediately, even mid-request if
the connection then hangs or times out.
"""
import smtplib
import sys
import traceback
from email.message import EmailMessage

from fastapi import HTTPException, status

from app.core.config import settings

# Kept short and well under a typical reverse-proxy gateway timeout (Railway
# included) - a hung/blocked outbound SMTP connection should fail fast with
# a real 502 from OUR app (with a useful message and a log line), rather
# than the platform's own proxy timing the whole request out first and
# returning a bare, undiagnosable 502 with no body.
_SMTP_TIMEOUT_SECONDS = 12


def _log(msg: str):
    print(f"[EMAIL] {msg}", flush=True)


def send_email_with_attachment(
    *, to_email: str, subject: str, body: str, attachment_bytes: bytes, attachment_filename: str, attachment_mime: str = "application/pdf",
):
    _log(
        f"send requested: to={to_email!r} host={settings.SMTP_HOST!r} port={settings.SMTP_PORT} "
        f"use_ssl={settings.SMTP_USE_SSL} username_set={bool(settings.SMTP_USERNAME)} "
        f"password_set={bool(settings.SMTP_PASSWORD)} from={settings.SMTP_FROM_EMAIL!r}"
    )
    if not settings.SMTP_HOST or not settings.SMTP_FROM_EMAIL:
        _log("NOT SENT - SMTP_HOST or SMTP_FROM_EMAIL is empty in this process's config")
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
        _log(f"connecting to {settings.SMTP_HOST}:{settings.SMTP_PORT} (use_ssl={settings.SMTP_USE_SSL}, timeout={_SMTP_TIMEOUT_SECONDS}s)...")
        if settings.SMTP_USE_SSL:
            with smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT, timeout=_SMTP_TIMEOUT_SECONDS) as server:
                _log(f"connected. logging in as {settings.SMTP_USERNAME or '(no auth)'}...")
                if settings.SMTP_USERNAME:
                    server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
                _log("authenticated. sending message...")
                server.send_message(msg)
        else:
            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=_SMTP_TIMEOUT_SECONDS) as server:
                server.starttls()
                _log(f"connected + STARTTLS ok. logging in as {settings.SMTP_USERNAME or '(no auth)'}...")
                if settings.SMTP_USERNAME:
                    server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
                _log("authenticated. sending message...")
                server.send_message(msg)
        _log(f"sent successfully to {to_email}")
    except (smtplib.SMTPException, OSError) as exc:
        _log(f"FAILED ({type(exc).__name__}): {exc}")
        traceback.print_exc(file=sys.stderr)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Could not send email: {exc}")
    except Exception as exc:  # noqa: BLE001 - last-resort: never let this hang or 500 without a clear cause
        _log(f"UNEXPECTED FAILURE ({type(exc).__name__}): {exc}")
        traceback.print_exc(file=sys.stderr)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Could not send email: {exc}")
