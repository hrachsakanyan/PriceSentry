"""Tests for alert evaluation and notification dispatch."""

import pytest

from src.alerts import (
    DROP,
    THRESHOLD,
    Alert,
    ConsoleNotifier,
    Notifier,
    build_notifiers,
    dispatch,
    evaluate,
)
from src.config import AlertSettings, EmailSettings, Product


@pytest.fixture
def product():
    return Product(name="Test Product", url="https://example.com/p", threshold=100.0)


class TestEvaluate:
    def test_fires_when_price_crosses_below_threshold(self, product, make_record):
        alerts = evaluate(make_record(90.0), product, previous=make_record(110.0, days_ago=1))
        kinds = [a.kind for a in alerts]

        assert THRESHOLD in kinds
        assert DROP in kinds

    def test_fires_on_first_ever_check_below_threshold(self, product, make_record):
        alerts = evaluate(make_record(90.0), product, previous=None)
        assert [a.kind for a in alerts] == [THRESHOLD]

    def test_does_not_repeat_threshold_alert_while_still_below(self, product, make_record):
        """Staying below the threshold is not news - only the crossing is."""
        alerts = evaluate(make_record(85.0), product, previous=make_record(90.0, days_ago=1))
        assert [a.kind for a in alerts] == [DROP]

    def test_silent_when_price_is_above_threshold_and_rising(self, product, make_record):
        alerts = evaluate(make_record(120.0), product, previous=make_record(110.0, days_ago=1))
        assert alerts == []

    def test_exactly_at_threshold_counts_as_below(self, product, make_record):
        alerts = evaluate(make_record(100.0), product, previous=None)
        assert [a.kind for a in alerts] == [THRESHOLD]

    def test_drop_alert_without_a_threshold(self, make_record):
        product = Product(name="Test Product", url="https://example.com/p")
        alerts = evaluate(make_record(90.0), product, previous=make_record(95.0, days_ago=1))
        assert [a.kind for a in alerts] == [DROP]

    def test_drop_alerts_can_be_disabled(self, product, make_record):
        alerts = evaluate(
            make_record(95.0),
            product,
            previous=make_record(99.0, days_ago=1),
            notify_on_drop=False,
        )
        assert alerts == []

    def test_unchanged_price_is_not_a_drop(self, product, make_record):
        alerts = evaluate(make_record(95.0), product, previous=make_record(95.0, days_ago=1))
        assert alerts == []


class TestAlertMessages:
    def test_threshold_message_mentions_the_threshold(self, make_record):
        alert = Alert(THRESHOLD, make_record(90.0), threshold=100.0)
        assert "below your threshold" in alert.message
        assert "100.00" in alert.message
        assert alert.title.startswith("Price alert")

    def test_drop_message_reports_amount_and_percent(self, make_record):
        alert = Alert(DROP, make_record(90.0), previous_price=100.0)
        assert "-10.00" in alert.message
        assert "-10.0%" in alert.message
        assert alert.title.startswith("Price drop")


class TestNotifiers:
    def test_console_notifier_prints(self, capsys, make_record):
        ConsoleNotifier().send(Alert(THRESHOLD, make_record(90.0), threshold=100.0))
        assert "Price alert" in capsys.readouterr().out

    def test_console_notifier_is_always_present(self):
        notifiers = build_notifiers(AlertSettings())
        assert any(isinstance(n, ConsoleNotifier) for n in notifiers)

    def test_unconfigured_email_is_skipped_with_a_warning(self, capsys):
        settings = AlertSettings(email=EmailSettings(enabled=True, sender="", recipients=[]))
        notifiers = build_notifiers(settings)

        assert len(notifiers) == 1
        assert "email notifications requested" in capsys.readouterr().err

    def test_dispatch_sends_every_alert_to_every_notifier(self, make_record):
        class Recorder(Notifier):
            def __init__(self):
                self.sent = []

            def send(self, alert):
                self.sent.append(alert)

        a, b = Recorder(), Recorder()
        alerts = [
            Alert(THRESHOLD, make_record(90.0), threshold=100.0),
            Alert(DROP, make_record(90.0), previous_price=100.0),
        ]
        dispatch(alerts, [a, b])

        assert len(a.sent) == 2
        assert len(b.sent) == 2
