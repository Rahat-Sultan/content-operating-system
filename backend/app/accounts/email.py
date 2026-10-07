"""
Sends the password reset email. Without SMTP configured, the code goes to the server
log instead so the flow can be tested locally — never into the API response, since that
would let anyone read another account's code.
"""
import logging
import smtplib
from email.message import EmailMessage

from app.config import settings

logger = logging.getLogger(__name__)


def smtp_configured() -> bool:
    return bool(settings.smtp_host and settings.smtp_username and settings.smtp_password)


def send_reset_code(to_email: str, code: str) -> None:
    if not smtp_configured():
        logger.warning("SMTP is not configured; password reset code for %s is %s", to_email, code)
        return

    message = EmailMessage()
    message["Subject"] = "Your Content OS password reset code"
    message["From"] = settings.smtp_from
    message["To"] = to_email
    message.set_content(
        f"Your Content OS password reset code is {code}.\n\n"
        "It expires in 10 minutes. If you did not request this, you can ignore this email."
    )

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as client:
        if settings.smtp_use_tls:
            client.starttls()
        client.login(settings.smtp_username, settings.smtp_password)
        client.send_message(message)
