import os
from dotenv import load_dotenv
import smtplib
import ssl
import logging
from email.mime.text import MIMEText

# Load environment variables from .env file
load_dotenv()

# Configure logger for email notifications
glogger = logging.getLogger("notifications")
glogger.setLevel(logging.DEBUG)
handler = logging.StreamHandler()
formatter = logging.Formatter(
    "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
handler.setFormatter(formatter)
glogger.addHandler(handler)

# SMTP configuration from environment
HOST = os.getenv("SMTP_HOST")
PORT = int(os.getenv("SMTP_PORT", 587))  # 587 for STARTTLS, 465 for SSL
USER = os.getenv("SMTP_USER")
PASS = os.getenv("SMTP_PASS")
FROM = os.getenv("ALERT_FROM")
USE_SSL = os.getenv("SMTP_SSL", "false").lower() in ("1", "true") or PORT == 465


def send_email(to: str, subject: str, body: str) -> bool:
    """
    Send an email alert. Returns True if sent successfully, False otherwise.

    Tries implicit SSL (SMTP_SSL) if USE_SSL is True, otherwise STARTTLS.
    Logs SMTP protocol conversation for debugging.
    """
    if not HOST or not FROM:
        glogger.error("SMTP_HOST and ALERT_FROM must be set in environment.")
        return False

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = FROM
    msg["To"] = to

    context = ssl.create_default_context()
    try:
        if USE_SSL:
            # glogger.debug(f"Connecting via SMTP_SSL to {HOST}:{PORT}")
            server = smtplib.SMTP_SSL(HOST, PORT, context=context, timeout=10)
        else:
            # glogger.debug(f"Connecting via SMTP to {HOST}:{PORT} with STARTTLS")
            server = smtplib.SMTP(HOST, PORT, timeout=10)
            server.set_debuglevel(1)
            server.ehlo()
            server.starttls(context=context)
            server.ehlo()

        server.login(USER, PASS)
        server.sendmail(FROM, [to], msg.as_string())
        server.quit()

        # glogger.info(f"Email sent successfully to {to}")
        return True
    except Exception as e:
        # glogger.error(f"Failed to send email to {to}: {e}")
        return False
