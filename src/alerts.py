"""Threshold / price-drop detection and notification delivery."""

from __future__ import annotations

import smtplib
import sys
from dataclasses import dataclass
from email.message import EmailMessage

from .config import AlertSettings, EmailSettings, Product
from .scraper import PriceRecord

THRESHOLD = "threshold"
DROP = "drop"


@dataclass
class Alert:
    """Something worth telling the user about."""

    kind: str  # THRESHOLD or DROP
    record: PriceRecord
    threshold: float | None = None
    previous_price: float | None = None

    @property
    def title(self) -> str:
        if self.kind == THRESHOLD:
            return f"Price alert: {self.record.product}"
        return f"Price drop: {self.record.product}"

    @property
    def message(self) -> str:
        price = self.record.format_price()
        if self.kind == THRESHOLD:
            return (
                f"{self.record.product} is now {price}, "
                f"below your threshold of {self.threshold:,.2f} {self.record.currency}.\n"
                f"{self.record.url}"
            )
        drop = (self.previous_price or 0) - self.record.price
        percent = (drop / self.previous_price * 100) if self.previous_price else 0
        return (
            f"{self.record.product} dropped from "
            f"{self.previous_price:,.2f} to {self.record.price:,.2f} "
            f"{self.record.currency} (-{drop:,.2f}, -{percent:.1f}%).\n"
            f"{self.record.url}"
        )


def evaluate(
    record: PriceRecord,
    product: Product,
    previous: PriceRecord | None,
    notify_on_drop: bool = True,
) -> list[Alert]:
    """Decide which alerts a new observation triggers.

    A threshold alert only fires on the *crossing* - if the previous
    observation was already below the threshold, staying there is not news.
    """
    alerts: list[Alert] = []

    if product.threshold is not None and record.price <= product.threshold:
        already_below = previous is not None and previous.price <= product.threshold
        if not already_below:
            alerts.append(Alert(THRESHOLD, record, threshold=product.threshold))

    if notify_on_drop and previous is not None and record.price < previous.price:
        alerts.append(Alert(DROP, record, previous_price=previous.price))

    return alerts


# --------------------------------------------------------------------- output


class Notifier:
    """Base class - a notifier turns an :class:`Alert` into a message somewhere."""

    def send(self, alert: Alert) -> None:  # pragma: no cover - interface
        raise NotImplementedError


class ConsoleNotifier(Notifier):
    """Always on. Writes to stdout."""

    def send(self, alert: Alert) -> None:
        print(f"\n  [!] {alert.title}\n      " + alert.message.replace("\n", "\n      "))


class DesktopNotifier(Notifier):
    """Desktop toast via plyer, if it is installed."""

    def __init__(self) -> None:
        try:
            from plyer import notification  # type: ignore[import-not-found]

            self._notification = notification
        except ImportError:
            self._notification = None

    @property
    def available(self) -> bool:
        return self._notification is not None

    def send(self, alert: Alert) -> None:
        if self._notification is None:
            return
        try:
            self._notification.notify(
                title=alert.title,
                message=alert.message.split("\n")[0],
                app_name="PriceSentry",
                timeout=10,
            )
        except Exception as exc:  # a failed toast must never stop tracking
            print(f"  desktop notification failed: {exc}", file=sys.stderr)


class EmailNotifier(Notifier):
    """SMTP email. Password comes from the environment variable in the config."""

    def __init__(self, settings: EmailSettings):
        self.settings = settings

    @property
    def available(self) -> bool:
        s = self.settings
        return bool(s.enabled and s.sender and s.recipients and s.password)

    def send(self, alert: Alert) -> None:
        s = self.settings
        if not self.available:
            return

        message = EmailMessage()
        message["Subject"] = alert.title
        message["From"] = s.sender
        message["To"] = ", ".join(s.recipients)
        message.set_content(alert.message)

        try:
            with smtplib.SMTP(s.host, s.port, timeout=20) as server:
                server.starttls()
                server.login(s.sender, s.password or "")
                server.send_message(message)
        except (smtplib.SMTPException, OSError) as exc:
            print(f"  email notification failed: {exc}", file=sys.stderr)


def build_notifiers(settings: AlertSettings) -> list[Notifier]:
    """Assemble the notifier list from config, skipping unavailable channels."""
    notifiers: list[Notifier] = [ConsoleNotifier()]

    if settings.desktop:
        desktop = DesktopNotifier()
        if desktop.available:
            notifiers.append(desktop)
        else:
            print(
                "  desktop notifications requested but plyer is not installed "
                "(pip install plyer)",
                file=sys.stderr,
            )

    if settings.email.enabled:
        email = EmailNotifier(settings.email)
        if email.available:
            notifiers.append(email)
        else:
            print(
                f"  email notifications requested but not configured "
                f"(set {settings.email.password_env}, sender and recipients)",
                file=sys.stderr,
            )

    return notifiers


def dispatch(alerts: list[Alert], notifiers: list[Notifier]) -> None:
    """Send every alert through every notifier."""
    for alert in alerts:
        for notifier in notifiers:
            notifier.send(alert)
