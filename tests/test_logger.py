"""Tests for the append-only price log."""

import csv

import pytest

from src.logger import FIELDNAMES, PriceLog, StorageError, summarize


class TestAppendAndRead:
    def test_creates_file_with_header_on_first_write(self, tmp_path, make_record):
        path = tmp_path / "nested" / "history.csv"
        log = PriceLog(path)
        log.append(make_record(42.50))

        assert path.is_file()
        with path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.reader(handle))
        assert tuple(rows[0]) == FIELDNAMES
        assert len(rows) == 2

    def test_appends_without_repeating_the_header(self, tmp_path, make_record):
        log = PriceLog(tmp_path / "history.csv")
        log.append(make_record(42.50, days_ago=2))
        log.append(make_record(39.99, days_ago=1))

        records = log.read_all()
        assert [r.price for r in records] == [42.50, 39.99]

    def test_round_trips_all_fields(self, tmp_path, make_record):
        log = PriceLog(tmp_path / "history.csv")
        original = make_record(1299.0, currency="EUR")
        log.append(original)

        restored = log.read_all()[0]
        assert restored.product == original.product
        assert restored.url == original.url
        assert restored.price == pytest.approx(original.price)
        assert restored.currency == "EUR"
        assert restored.timestamp == original.timestamp

    def test_empty_log_reads_as_empty_list(self, tmp_path):
        assert PriceLog(tmp_path / "missing.csv").read_all() == []

    def test_records_come_back_in_chronological_order(self, tmp_path, make_record):
        log = PriceLog(tmp_path / "history.csv")
        log.append_many([make_record(10.0, days_ago=1), make_record(20.0, days_ago=5)])

        assert [r.price for r in log.read_all()] == [20.0, 10.0]

    def test_corrupt_rows_are_skipped_not_fatal(self, tmp_path, make_record):
        path = tmp_path / "history.csv"
        log = PriceLog(path)
        log.append(make_record(42.50))
        with path.open("a", encoding="utf-8") as handle:
            handle.write("not-a-date,Broken,,abc,USD\n")

        records = log.read_all()
        assert len(records) == 1
        assert records[0].price == pytest.approx(42.50)


class TestJsonBackend:
    def test_json_extension_selects_json_storage(self, tmp_path, make_record):
        path = tmp_path / "history.json"
        log = PriceLog(path)
        assert log.format == "json"

        log.append(make_record(42.50, days_ago=1))
        log.append(make_record(39.99))

        assert path.read_text(encoding="utf-8").lstrip().startswith("[")
        assert [r.price for r in log.read_all()] == [42.50, 39.99]

    def test_malformed_json_raises_storage_error(self, tmp_path):
        path = tmp_path / "history.json"
        path.write_text("{not json", encoding="utf-8")
        with pytest.raises(StorageError):
            PriceLog(path).read_all()


class TestQueries:
    @pytest.fixture
    def populated(self, tmp_path, make_record):
        log = PriceLog(tmp_path / "history.csv")
        log.append_many(
            [
                make_record(100.0, product="Laptop", days_ago=3),
                make_record(95.0, product="Laptop", days_ago=2),
                make_record(90.0, product="Laptop", days_ago=1),
                make_record(20.0, product="Mouse", days_ago=1),
            ]
        )
        return log

    def test_filters_by_product(self, populated):
        assert len(populated.history("Laptop")) == 3
        assert len(populated.history("Mouse")) == 1

    def test_product_filter_is_case_insensitive(self, populated):
        assert len(populated.history("laptop")) == 3

    def test_limit_keeps_the_most_recent(self, populated):
        prices = [r.price for r in populated.history("Laptop", limit=2)]
        assert prices == [95.0, 90.0]

    def test_latest_returns_newest_observation(self, populated):
        assert populated.latest("Laptop").price == pytest.approx(90.0)

    def test_latest_is_none_for_unknown_product(self, populated):
        assert populated.latest("Monitor") is None

    def test_product_names_lists_distinct_products(self, populated):
        assert sorted(populated.product_names()) == ["Laptop", "Mouse"]


class TestSummarize:
    def test_computes_stats(self, make_record):
        records = [
            make_record(100.0, days_ago=3),
            make_record(80.0, days_ago=2),
            make_record(90.0, days_ago=1),
        ]
        stats = summarize(records)

        assert stats["count"] == 3
        assert stats["current"] == pytest.approx(90.0)
        assert stats["min"] == pytest.approx(80.0)
        assert stats["max"] == pytest.approx(100.0)
        assert stats["average"] == pytest.approx(90.0)
        assert stats["change"] == pytest.approx(-10.0)

    def test_returns_none_for_empty_history(self):
        assert summarize([]) is None
