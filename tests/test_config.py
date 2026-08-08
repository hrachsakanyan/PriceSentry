"""Tests for config loading and validation."""

import json

import pytest

from src.config import ConfigError, EmailSettings, load_config


def write_config(tmp_path, data, name="config.json"):
    path = tmp_path / name
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


MINIMAL = {"products": [{"name": "Thing", "url": "https://example.com/p"}]}


class TestLoading:
    def test_loads_a_minimal_config(self, tmp_path):
        config = load_config(write_config(tmp_path, MINIMAL))

        assert len(config.products) == 1
        assert config.products[0].name == "Thing"
        assert config.products[0].threshold is None
        assert config.interval_minutes == 360

    def test_applies_defaults(self, tmp_path):
        config = load_config(write_config(tmp_path, MINIMAL))

        assert config.request.timeout == 15.0
        assert config.request.retries == 2
        assert config.alerts.notify_on_drop is True
        assert config.alerts.desktop is False
        assert config.alerts.email.enabled is False

    def test_reads_every_field(self, tmp_path):
        config = load_config(
            write_config(
                tmp_path,
                {
                    "storage": {"path": "out/history.json"},
                    "request": {"timeout": 5, "retries": 0, "user_agent": "custom-agent"},
                    "alerts": {"notify_on_drop": False, "desktop": True},
                    "schedule": {"interval_minutes": 30},
                    "products": [
                        {
                            "name": "Thing",
                            "url": "https://example.com/p",
                            "selector": ".price",
                            "threshold": 49.99,
                            "currency": "EUR",
                        }
                    ],
                },
            )
        )

        assert config.storage_path.name == "history.json"
        assert config.request.timeout == 5.0
        assert config.request.user_agent == "custom-agent"
        assert config.alerts.notify_on_drop is False
        assert config.alerts.desktop is True
        assert config.interval_minutes == 30
        assert config.products[0].selector == ".price"
        assert config.products[0].threshold == pytest.approx(49.99)
        assert config.products[0].currency == "EUR"

    def test_storage_path_resolves_relative_to_the_config_file(self, tmp_path):
        config = load_config(
            write_config(tmp_path, {**MINIMAL, "storage": {"path": "data/history.csv"}})
        )
        assert config.storage_path == tmp_path.resolve() / "data" / "history.csv"

    def test_local_product_url_resolves_relative_to_the_config_file(self, tmp_path):
        page = tmp_path / "samples" / "demo.html"
        page.parent.mkdir()
        page.write_text("<html></html>", encoding="utf-8")

        config = load_config(
            write_config(
                tmp_path,
                {"products": [{"name": "Demo", "url": "samples/demo.html"}]},
            )
        )
        assert config.products[0].url == str(page.resolve())

    def test_http_urls_are_left_alone(self, tmp_path):
        config = load_config(write_config(tmp_path, MINIMAL))
        assert config.products[0].url == "https://example.com/p"


class TestValidation:
    def test_missing_file(self, tmp_path):
        with pytest.raises(ConfigError, match="not found"):
            load_config(tmp_path / "nope.json")

    def test_invalid_json(self, tmp_path):
        path = tmp_path / "config.json"
        path.write_text("{broken", encoding="utf-8")
        with pytest.raises(ConfigError, match="not valid JSON"):
            load_config(path)

    def test_empty_product_list(self, tmp_path):
        with pytest.raises(ConfigError, match="non-empty 'products'"):
            load_config(write_config(tmp_path, {"products": []}))

    def test_product_without_a_name(self, tmp_path):
        with pytest.raises(ConfigError, match=r"products\[0\].name"):
            load_config(write_config(tmp_path, {"products": [{"url": "https://x.com"}]}))

    def test_product_without_a_url(self, tmp_path):
        with pytest.raises(ConfigError, match=r"products\[0\].url"):
            load_config(write_config(tmp_path, {"products": [{"name": "Thing"}]}))

    def test_non_numeric_threshold(self, tmp_path):
        data = {"products": [{"name": "Thing", "url": "https://x.com", "threshold": "cheap"}]}
        with pytest.raises(ConfigError, match="must be a number"):
            load_config(write_config(tmp_path, data))

    def test_negative_threshold(self, tmp_path):
        data = {"products": [{"name": "Thing", "url": "https://x.com", "threshold": -5}]}
        with pytest.raises(ConfigError, match="greater than 0"):
            load_config(write_config(tmp_path, data))

    def test_duplicate_product_names(self, tmp_path):
        data = {
            "products": [
                {"name": "Thing", "url": "https://x.com/1"},
                {"name": "thing", "url": "https://x.com/2"},
            ]
        }
        with pytest.raises(ConfigError, match="duplicate product names"):
            load_config(write_config(tmp_path, data))

    def test_invalid_interval(self, tmp_path):
        with pytest.raises(ConfigError, match="at least 1"):
            load_config(write_config(tmp_path, {**MINIMAL, "schedule": {"interval_minutes": 0}}))


class TestLookup:
    def test_product_lookup_is_case_insensitive(self, tmp_path):
        config = load_config(write_config(tmp_path, MINIMAL))

        assert config.product_by_name("thing") is not None
        assert config.product_by_name("  THING  ") is not None
        assert config.product_by_name("other") is None


class TestEmailSettings:
    def test_password_comes_from_the_environment(self, monkeypatch):
        settings = EmailSettings(password_env="TEST_SENTRY_PASSWORD")
        assert settings.password is None

        monkeypatch.setenv("TEST_SENTRY_PASSWORD", "hunter2")
        assert settings.password == "hunter2"

    def test_a_single_recipient_string_becomes_a_list(self):
        settings = EmailSettings.from_dict({"recipients": "me@example.com"})
        assert settings.recipients == ["me@example.com"]
