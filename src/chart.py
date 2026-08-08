"""Optional price-history chart. Requires matplotlib (pip install matplotlib)."""

from __future__ import annotations

from pathlib import Path

from .scraper import PriceRecord


class ChartError(Exception):
    """Raised when a chart cannot be produced."""


def plot_history(
    records: list[PriceRecord],
    output_path: str | Path,
    title: str = "Price history",
) -> Path:
    """Draw price-over-time for one or more products and save it as a PNG."""
    try:
        import matplotlib

        matplotlib.use("Agg")  # no GUI needed - we only write a file
        import matplotlib.pyplot as plt
        from matplotlib.dates import AutoDateFormatter, AutoDateLocator
    except ModuleNotFoundError as exc:
        raise ChartError(
            "matplotlib is required for charts - install it with: pip install matplotlib"
        ) from exc
    except ImportError as exc:
        # Installed, but unusable - e.g. its native DLLs failed to load.
        raise ChartError(f"matplotlib is installed but could not be loaded: {exc}") from exc

    if not records:
        raise ChartError("no price history to plot yet - run 'check' first")

    by_product: dict[str, list[PriceRecord]] = {}
    for record in records:
        by_product.setdefault(record.product, []).append(record)

    figure, axes = plt.subplots(figsize=(10, 5.5))

    for name, series in by_product.items():
        series.sort(key=lambda r: r.timestamp)
        axes.plot(
            [r.timestamp for r in series],
            [r.price for r in series],
            marker="o",
            markersize=4,
            linewidth=1.8,
            label=name,
        )

    currencies = {r.currency for r in records}
    ylabel = "Price" if len(currencies) != 1 else f"Price ({currencies.pop()})"

    axes.set_title(title)
    axes.set_xlabel("Date")
    axes.set_ylabel(ylabel)
    axes.grid(True, linestyle="--", alpha=0.35)
    if len(by_product) > 1:
        axes.legend()

    locator = AutoDateLocator()
    axes.xaxis.set_major_locator(locator)
    axes.xaxis.set_major_formatter(AutoDateFormatter(locator))
    figure.autofmt_xdate()
    figure.tight_layout()

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output, dpi=140)
    plt.close(figure)
    return output
