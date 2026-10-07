"""Отправка писем (07.10.2026) - пока только коды входа по почте
(core/email_login.py).

Обычный SMTP, без SDK конкретного сервиса: подходит и Brevo (smtp-relay.
brevo.com:587), и Gmail с паролем приложения - менять отправителя значит
поменять .env, а не код. Не настроено - mail_configured() False, и
приложение честно скажет, что вход по почте пока недоступен.
"""
import logging
import os
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr

log = logging.getLogger(__name__)


def _cfg():
    return {
        "host": os.getenv("SMTP_HOST", ""),
        "port": int(os.getenv("SMTP_PORT", "587") or 587),
        "user": os.getenv("SMTP_USER", ""),
        "password": os.getenv("SMTP_PASS", ""),
        "sender": os.getenv("MAIL_FROM", ""),
    }


def mail_configured():
    c = _cfg()
    return bool(c["host"] and c["sender"])


def send_mail(to, subject, text, html=None):
    """Синхронно - из aiohttp звать через asyncio.to_thread. True/False,
    исключения наружу не выпускает: человеку достаточно «не получилось»."""
    c = _cfg()
    if not (c["host"] and c["sender"]):
        return False
    msg = EmailMessage()
    msg["From"] = formataddr(("Yassir", c["sender"]))
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(text)
    if html:
        msg.add_alternative(html, subtype="html")
    try:
        ctx = ssl.create_default_context()
        if c["port"] == 465:
            s = smtplib.SMTP_SSL(c["host"], c["port"], context=ctx, timeout=20)
        else:
            s = smtplib.SMTP(c["host"], c["port"], timeout=20)
            s.starttls(context=ctx)
        with s:
            if c["user"]:
                s.login(c["user"], c["password"])
            s.send_message(msg)
        return True
    except (smtplib.SMTPException, OSError) as e:
        log.warning("send_mail to %s failed: %s", to, e)
        return False
