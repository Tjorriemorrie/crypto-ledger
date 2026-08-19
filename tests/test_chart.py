"""Laying a series of daily prices out as a line, and daily holdings out as stacked bars."""

import datetime as dt
from decimal import Decimal

from main import chart
from main.models import RatedAsset

START = dt.date(2026, 1, 1)


def _series(days, price=lambda offset: 1000000 + offset * 100000):
    return [(START + dt.timedelta(days=offset), Decimal(price(offset))) for offset in range(days)]


def test_price_chart_plots_a_point_for_every_day():
    plotted = chart.price_chart(_series(3), RatedAsset.BTC)

    assert [point["price"] for point in plotted["points"]] == [
        "R 1,000,000",
        "R 1,100,000",
        "R 1,200,000",
    ]
    # The dearest day is the highest on the page, and SVG counts y downwards.
    assert float(plotted["points"][-1]["y"]) < float(plotted["points"][0]["y"])


def test_the_close_is_coloured_by_which_average_is_on_top():
    days = chart.PRICE_DAYS
    peak = days // 2

    def rise_then_fall(offset):
        return 1000000 + 10000 * (offset if offset < peak else 2 * peak - offset)

    plotted = chart.price_chart(_series(days, price=rise_then_fall), RatedAsset.BTC)

    assert {run["state"] for run in plotted["close"]} == {"up", "down"}


def test_the_strip_reads_the_close_against_the_day_a_span_before_it():
    # A window that ends a tenth above where the strip's own span began.
    days = chart.PRICE_DAYS
    plotted = chart.price_chart(
        _series(days, price=lambda offset: 1000000 + offset * 1000), RatedAsset.BTC
    )

    strip = plotted["change"]
    last, before = 1000000 + (days - 1) * 1000, 1000000 + (days - 1 - strip["span"]) * 1000
    assert strip["latest"] == f"{Decimal(last) / before - 1:+.1%}"
    assert strip["ahead"] is True


def test_a_moving_average_is_drawn_once_it_has_its_days_behind_it():
    plotted = chart.price_chart(_series(30), RatedAsset.BTC)

    # 30 days is enough for the 26-day average to have started, and not for the 260-day one.
    assert [average["label"] for average in plotted["averages"]] == ["26-day"]


def _holdings(weeks, held=lambda offset: 1200 + offset * 100):
    return [
        {
            "date": START + dt.timedelta(weeks=offset),
            "parts": [
                {"label": "Bank ZAR", "value": Decimal(-1000)},
                {"label": "Ledger BTC", "value": Decimal(held(offset))},
            ],
        }
        for offset in range(weeks)
    ]


def test_the_profit_chart_stacks_a_bar_for_every_week():
    plotted = chart.profit_chart(_holdings(3))

    assert len(plotted["bars"]) == 3
    # The money put in hangs below the axis and what it bought stands above it, so the net of the
    # stack is the profit. SVG counts y downwards, so above the axis is a smaller y.
    axis = float(plotted["zero"])
    put_in, bought = plotted["bars"][0]["segments"]
    assert float(put_in["y"]) == axis
    assert float(bought["y"]) + float(bought["height"]) == axis


def test_the_results_chart_marks_every_combination_run():
    results = [{"label": "Crossover", "profit": profit} for profit in (1000.0, 5000.0, 2000.0)]

    plotted = chart.results_chart(results, total=10)

    assert len(plotted["marks"]) == 3
    # The best is ringed, and the dearest result is the highest on the page; SVG counts y downwards.
    assert plotted["best"]["y"] == plotted["marks"][1]["y"]
    assert float(plotted["marks"][1]["y"]) < float(plotted["marks"][0]["y"])


def test_the_trend_follows_the_profit_over_the_window():
    rising = chart.profit_chart(_holdings(3))["trend"]
    falling = chart.profit_chart(_holdings(3, held=lambda offset: 1200 - offset * 100))["trend"]

    assert float(rising["y2"]) < float(rising["y1"])
    assert float(falling["y2"]) > float(falling["y1"])
