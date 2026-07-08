"""Swappable notification interface — email first, WhatsApp/push later.

Bill logic never imports a concrete notifier; it calls get_notifier().
Publish is decoupled from notification: a send failure never blocks publish.
"""
import logging
import smtplib
from email.message import EmailMessage
from typing import Protocol

from ..config import settings

log = logging.getLogger(__name__)


class Notifier(Protocol):
    def bill_published(self, to_email: str, tenant_name: str, unit_name: str,
                       period_label: str, total_rupees: str) -> None: ...


class EmailNotifier:
    def bill_published(self, to_email, tenant_name, unit_name, period_label, total_rupees):
        msg = EmailMessage()
        msg["From"] = settings.mail_from
        msg["To"] = to_email
        msg["Subject"] = f"Your {period_label} bill for {unit_name} is ready"
        msg.set_content(
            f"Hi {tenant_name},\n\n"
            f"Your bill for {period_label} has been published.\n"
            f"Total amount: ₹{total_rupees}\n\n"
            f"Log in to view and download it.\n"
        )
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
            smtp.send_message(msg)


class ConsoleNotifier:
    def bill_published(self, to_email, tenant_name, unit_name, period_label, total_rupees):
        log.info("NOTIFY %s: %s bill for %s ready, total ₹%s",
                 to_email, period_label, unit_name, total_rupees)


def get_notifier() -> Notifier:
    if settings.notifier == "console":
        return ConsoleNotifier()
    return EmailNotifier()


def notify_bill_published_safe(**kwargs) -> bool:
    """Send, but never raise — publish must succeed even if notification fails."""
    try:
        get_notifier().bill_published(**kwargs)
        return True
    except Exception:
        log.exception("Bill-published notification failed (bill stays published)")
        return False
