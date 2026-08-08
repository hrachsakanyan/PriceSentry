"""End-to-end CLI tests, driven entirely off local fixture pages."""

import json

import pytest

from src.logger import PriceLog
from src.main import EXIT_CONFIG, EXIT_ERROR, EXIT_OK, main


@pytest.fixture
def project(tmp_path, fixtures_dir):
    """A temp project dir with a config pointing at the offline fixtures."""

    def _build(products=None, **overrides):
        data = {
            "storage": {"path": "data/price_history.csv"},
            "products": products
            or [
                {
                    "name": "Headphones",
                    "url": str(fixtures_dir / "product_selector.html"),
                    "selector": ".price-now",
                    "threshold": 50.0,
                },
                {
                    "name": "Keyboard",
                    "url": str(fixtures_dir / "product_jsonld.html"),
                    "threshold": 20.0,
                },
            ],
        }
        data.update(overrides)
        path = tmp_path / "config.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    return _build


def run(config_path, *args):
    return main(["-c", str(config_path), *args])


def require_matplotlib():
    """Skip unless matplotlib is importable.

    Not ``pytest.importorskip``: that only skips on ModuleNotFoundError, and a
    matplotlib whose native DLLs fail to load raises a plain ImportError.
    """
    try:
        import matplotlib  # noqa: F401
    except ImportError as exc:
        pytest.skip(f"matplotlib unavailable: {exc}")


class TestCheck:
    def test_scrapes_logs_and_reports(self, project, tmp_path, capsys):
        config_path = project()
        assert run(config_path, "check") == EXIT_OK

        out = capsys.readouterr().out
        assert "Headphones: 42.50 USD" in out
        assert "Keyboard: 89.50 GBP" in out

        records = PriceLog(tmp_path / "data" / "price_history.csv").read_all()
        assert sorted(r.product for r in records) == ["Headphones", "Keyboard"]

    def test_appends_across_runs(self, project, tmp_path):
        config_path = project()
        run(config_path, "check")
        run(config_path, "check")

        log = PriceLog(tmp_path / "data" / "price_history.csv")
        assert len(log.history("Headphones")) == 2

    def test_single_product_filter(self, project, tmp_path, capsys):
        config_path = project()
        assert run(config_path, "check", "-p", "Headphones") == EXIT_OK

        assert "Keyboard" not in capsys.readouterr().out
        log = PriceLog(tmp_path / "data" / "price_history.csv")
        assert log.product_names() == ["Headphones"]

    def test_threshold_alert_is_printed(self, project, fixtures_dir, capsys):
        # threshold sits above the fixture price (42.50), so the alert fires
        config_path = project(
            products=[
                {
                    "name": "Headphones",
                    "url": str(fixtures_dir / "product_selector.html"),
                    "selector": ".price-now",
                    "threshold": 100.0,
                }
            ]
        )
        run(config_path, "check")
        out = capsys.readouterr().out
        assert "Price alert" in out
        assert "below your threshold" in out

    def test_unknown_product_is_a_config_error(self, project, capsys):
        assert run(project(), "check", "-p", "Nonexistent") == EXIT_CONFIG
        assert "unknown product" in capsys.readouterr().err

    def test_unscrapeable_product_fails_without_crashing(self, project, tmp_path, capsys):
        config_path = project(
            products=[{"name": "Gone", "url": str(tmp_path / "missing.html")}]
        )
        assert run(config_path, "check") == EXIT_ERROR
        assert "FAILED" in capsys.readouterr().err

    def test_one_failure_does_not_block_the_others(self, project, tmp_path, fixtures_dir):
        config_path = project(
            products=[
                {"name": "Gone", "url": str(tmp_path / "missing.html")},
                {
                    "name": "Headphones",
                    "url": str(fixtures_dir / "product_selector.html"),
                    "selector": ".price-now",
                },
            ]
        )
        assert run(config_path, "check") == EXIT_OK
        assert PriceLog(tmp_path / "data" / "price_history.csv").product_names() == ["Headphones"]


class TestHistory:
    def test_says_so_when_empty(self, project, capsys):
        assert run(project(), "history") == EXIT_OK
        assert "No price history" in capsys.readouterr().out

    def test_prints_a_table_with_summary(self, project, capsys):
        config_path = project()
        run(config_path, "check")
        capsys.readouterr()

        assert run(config_path, "history") == EXIT_OK
        out = capsys.readouterr().out
        assert "TIMESTAMP" in out
        assert "Headphones" in out
        assert "min" in out and "max" in out

    def test_json_output_is_valid_json(self, project, capsys):
        config_path = project()
        run(config_path, "check")
        capsys.readouterr()

        run(config_path, "history", "--json")
        payload = json.loads(capsys.readouterr().out)

        assert len(payload) == 2
        assert {"timestamp", "product", "url", "price", "currency"} <= set(payload[0])

    def test_limit_trims_output(self, project, capsys):
        config_path = project()
        run(config_path, "check")
        run(config_path, "check")
        capsys.readouterr()

        run(config_path, "history", "-p", "Headphones", "-n", "1", "--json")
        assert len(json.loads(capsys.readouterr().out)) == 1


class TestProducts:
    def test_lists_products_and_last_seen_price(self, project, capsys):
        config_path = project()
        run(config_path, "products")
        assert "never checked" in capsys.readouterr().out

        run(config_path, "check")
        capsys.readouterr()
        run(config_path, "products")
        out = capsys.readouterr().out
        assert "Headphones" in out
        assert "42.50 USD" in out


class TestChart:
    def test_reports_a_clear_error_when_there_is_nothing_to_plot(self, project, capsys):
        require_matplotlib()
        assert run(project(), "chart") == EXIT_ERROR
        assert "no price history" in capsys.readouterr().err

    def test_writes_a_png(self, project, tmp_path, capsys):
        require_matplotlib()
        config_path = project()
        run(config_path, "check")

        output = tmp_path / "chart.png"
        assert run(config_path, "chart", "-o", str(output)) == EXIT_OK
        assert output.is_file() and output.stat().st_size > 0


class TestCli:
    def test_missing_config_file(self, tmp_path, capsys):
        assert main(["-c", str(tmp_path / "nope.json"), "check"]) == EXIT_CONFIG
        assert "Config error" in capsys.readouterr().err

    def test_no_subcommand_exits_with_usage_error(self):
        with pytest.raises(SystemExit) as excinfo:
            main([])
        assert excinfo.value.code == 2
