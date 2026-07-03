# utils/mailer.py
"""Outbound email via SMTP, configured entirely from env.

    SMTP_HOST, SMTP_PORT (587 STARTTLS / 465 SSL), SMTP_USER,
    SMTP_PASSWORD, SMTP_FROM (defaults to SMTP_USER)

For Gmail use smtp.gmail.com:587 with an App Password
(https://myaccount.google.com/apppasswords).

send_email() returns False instead of raising when SMTP is not
configured or delivery fails — callers decide how to degrade.
"""
import os
import smtplib
from email.message import EmailMessage

from utils.logger import get_logger

log = get_logger("mailer")

SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
SMTP_FROM = os.getenv("SMTP_FROM") or SMTP_USER


def is_configured() -> bool:
    return bool(SMTP_HOST and SMTP_USER and SMTP_PASSWORD)


def send_email(to: str, subject: str, body: str) -> bool:
    if not is_configured():
        log.warning("SMTP not configured — cannot send email to %s", to)
        return False

    msg = EmailMessage()
    msg["From"] = SMTP_FROM
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)

    try:
        if SMTP_PORT == 465:
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=20) as server:
                server.login(SMTP_USER, SMTP_PASSWORD)
                server.send_message(msg)
        else:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as server:
                server.starttls()
                server.login(SMTP_USER, SMTP_PASSWORD)
                server.send_message(msg)
        log.info("Email sent to %s (%s)", to, subject)
        return True
    except Exception as exc:
        log.error("Email to %s failed: %s", to, exc)
        return False
