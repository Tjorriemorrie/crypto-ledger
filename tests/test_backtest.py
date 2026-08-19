"""Running a weekly investment plan over a price history, and sweeping its parameters."""

from main import backtest, preferences
from main.forms import SweepForm

# Long enough for the shortest long average in the grid (20 x 5) to have started with weeks to
# spare, and rising throughout, so the short average is over the long one on every week read.
RISING = [1000.0 + day * 10 for day in range(400)]

COMBO = backtest.combination(backtest.RISE, percent=2, short=20, multiplier=5, fee=0)
AVERAGES = backtest.moving_averages(RISING, {COMBO["short"], COMBO["long"]})


def test_a_rising_price_ends_holding_bitcoin():
    result = backtest.run(RISING, AVERAGES, COMBO)

    # The short average is above the long one throughout, so every contribution bought Bitcoin and
    # the rand wallet was never used. A price that only rises leaves that ahead of what went in.
    assert result["weeks"][-1]["zar"] == 0
    assert result["profit"] > 0
    assert result["contributed"] == len(result["weeks"]) * backtest.WEEKLY_CONTRIBUTION


def test_the_two_plans_read_the_same_week_opposite_ways():
    other = backtest.combination(backtest.FALL, percent=2, short=20, multiplier=5, fee=0)

    rise = backtest.run(RISING, AVERAGES, COMBO)
    fall = backtest.run(RISING, AVERAGES, other)

    assert {week["signal"] for week in rise["weeks"]} == {backtest.UP}
    assert {week["signal"] for week in fall["weeks"]} == {backtest.DOWN}


def test_a_fee_is_charged_on_everything_converted():
    charged = backtest.combination(backtest.RISE, percent=2, short=20, multiplier=5, fee=10)

    free = backtest.run(RISING, AVERAGES, COMBO)
    costly = backtest.run(RISING, AVERAGES, charged)

    # Every week reads up here, so every contribution and every move is a purchase that pays.
    assert costly["paid"] > 0
    assert costly["profit"] < free["profit"]
    assert free["paid"] == 0


def test_the_baseline_buys_every_week_and_never_sells():
    plan = backtest.run(RISING, AVERAGES, COMBO)

    held = backtest.hold(RISING, fee=0, first=COMBO["long"] - 1)

    # The same weeks and the same money as the plan it is set against, so the two compare.
    assert len(held["weeks"]) == len(plan["weeks"])
    assert held["contributed"] == plan["contributed"]
    # Nothing is ever sold, so the rand wallet stays empty and the whole lot is in Bitcoin.
    assert held["weeks"][-1]["zar"] == 0
    assert held["final"] == held["weeks"][-1]["bitcoin"]


def test_the_sweep_ranks_every_combination_it_has_run():
    results = backtest.search(RISING, 12)

    # Both plans, five percentages, eleven short averages and six multipliers. The fee is not
    # swept — one fee runs every combination — so it is no part of the count.
    assert len(backtest.combinations()) == 2 * 5 * 11 * 6
    assert len(results) == 12
    assert backtest.best(results) == max(results, key=lambda result: result["profit"])


def test_the_report_ranks_each_settings_values_by_profit():
    results = backtest.search(RISING, backtest.count())

    tables = backtest.report(results)

    assert [table["setting"] for table in tables] == ["strategy", "percent", "multiplier"]
    # One row per value of that table's setting: two plans, five weekly moves, six multipliers.
    assert [len(table["rows"]) for table in tables] == [2, 5, 6]
    # Every table ranked by what its values came to, best first.
    for table in tables:
        profits = [row["profit"] for row in table["rows"]]
        assert profits == sorted(profits, reverse=True)
    # And a run that leads more than one setting is listed under each of them, not held back.
    leader = backtest.best(results)
    assert all(table["rows"][0]["profit"] == leader["profit"] for table in tables)


def test_the_form_turns_the_sliders_into_a_grid():
    form = SweepForm(
        {
            "percent_min": 4,
            "percent_max": 8,
            "short_min": 20,
            "short_max": 30,
            "multiplier_min": 5,
            "multiplier_max": 10,
            "fee": 2,
            "years": 10,
        }
    )

    assert form.is_valid()
    assert form.grid() == {"percent": (4, 8), "short": (20, 30), "multiplier": (5, 10)}
    # The fee and the window ride along on every combination rather than being any of them.
    assert form.cleaned_data["fee"] == 2
    assert form.cleaned_data["years"] == 10
    assert backtest.count(form.grid()) == 2 * 5 * 11 * 6


def test_the_page_opens_on_the_last_sweep_that_ran():
    form = SweepForm(
        {
            "percent_min": 4,
            "percent_max": 8,
            "short_min": 20,
            "short_max": 30,
            "multiplier_min": 5,
            "multiplier_max": 10,
            "fee": 2,
            "years": 10,
        }
    )
    assert form.is_valid()

    preferences.remember(form.cleaned_data)

    # Kept through a restart, so the sliders come back where they were left rather than at the
    # defaults — and read back through the form, so only settings a sweep would still run get in.
    assert SweepForm.opening() == form.cleaned_data
