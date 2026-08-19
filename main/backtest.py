"""Two weekly investment plans run over a long price history, and the sweep that ranks them.

The question the ledger cannot answer is what a plan would have come to. So a fixed amount is
contributed every week over the whole history, put into rands or into Bitcoin according to two
moving averages of the price, and a slice of one wallet is moved into the other every week on the
same reading. Which wallet, how big a slice and how long the averages are is what the sweep
settles: every combination is run and the one that ended with the most is reported.

Two plans, which are the same reading taken the two ways round:

- **Bitcoin on a rise** buys Bitcoin while the short average is over the long one, and sells back
  into rands while it is under.
- **Bitcoin on a fall** does the opposite — it buys while the short average is under the long one
  and sells while it is over.

Neither is the sensible one and the other the perverse one; which of them the history rewarded is
the question, and it is asked by running both. There is no third plan and no reading beyond the two
averages: a rule needing more conditions than that is one the sweep cannot say much about.

The contribution is money arriving from outside; it is never taken out of the rand wallet, so
every combination receives exactly the same amount and ranking them by what they ended with is
ranking them by profit.

Nothing here reads the database or writes anything: it is handed a list of prices and hands back
figures. Those figures are floats rather than `Decimal`, unlike everywhere else in the ledger,
because this is a simulation of what might have happened and not a rand that goes on a return.
They are rounded to the cent at `equity_weeks`, where the chart takes them.
"""

import math
from decimal import Decimal
from itertools import product

# What arrives from outside every week. Fixed, so every combination is handed the same money and
# the only thing separating them is what they did with it.
WEEKLY_CONTRIBUTION = 1000.0

# The grid, as a lowest and a highest for each setting. The long average is the short one times the
# multiplier, so the sweep asks how far apart the two have to be rather than pinning a length onto
# each. The ranges are set on the page; these are what it opens on.
DEFAULTS = {
    "percent": (1, 5),
    "short": (20, 30),
    "multiplier": (5, 10),
}

# The fee is set for the whole sweep rather than swept over. What an exchange charges is not a
# setting to be optimised — it is a fact about where the money is held — so a sweep is run at one
# fee and asked what the plan is worth at that cost, rather than being asked to discover that a
# cheaper exchange would be better.
FEE_DEFAULT = 1

# How far back a sweep is run, in years counted off the last day priced. Not swept either: a plan
# run over a different stretch of history is a different question rather than a better answer to
# this one, and a sweep asked to optimise its own window would only ever answer "pick the years
# that suited". So it is one slider like the fee, and the page prints the dates it actually covered.
YEARS_DEFAULT = 10

# What each range may be set to. A short average of one day is the price itself and a multiplier of
# one makes both averages the same line, so neither is a reading anything could come of. A fee may
# be nothing at all, since what a plan came to before costs is worth being able to see. Fifteen
# years is a ceiling and not a promise — the history begins where the prices do, in September
# 2014 — so asking for more of it than there is gives the whole of it.
BOUNDS = {
    "percent": (1, 25),
    "short": (2, 200),
    "multiplier": (2, 30),
    "fee": (0, 10),
    "years": (1, 15),
}

# The most combinations one sweep will run. Every one of them is a walk through the whole history
# and draws its own mark on the chart, so a grid is turned away with its count rather than left to
# run — a page that never finishes says less than a smaller grid that does. The page holds its
# sliders to this as they are dragged; this is the check behind that, for everything that arrives
# some other way.
MAX_COMBINATIONS = 10000

# Which settings get a table of their own, and what each is called. Every value of the setting is
# listed with the best result found at it, so a table says what that one setting was worth. The
# short average is swept like the rest but is not read down this way — it is the setting with the
# most values in it, and a table of two hundred rows answers nothing. The fee is not here because
# it is not swept: one fee runs the whole sweep, so there is only ever one value to report.
TABS = {
    "strategy": "Plan",
    "percent": "Weekly move",
    "multiplier": "Multiplier",
}

# What a sweep keeps of each run. The weeks themselves are dropped — see `search`.
TOTALS = ("contributed", "paid", "final", "profit")

# The two plans: which wallet the money goes into while the short average is over the long one.
# One is the other read backwards, which is the whole point — the sweep is asked which way round
# the history rewarded, so both ways round have to be run.
RISE = "rise"
FALL = "fall"
PLANS = {RISE: "Bitcoin on a rise", FALL: "Bitcoin on a fall"}

# The baseline every plan is set against: the same money, into Bitcoin, left alone. It is not one
# of `PLANS` and is never swept — there is nothing in it to vary — but no plan's profit means much
# until it is put beside this one.
HOLD = "Hold Bitcoin"

UP = "up"
DOWN = "down"

DAYS_PER_WEEK = 7
# Two weeks is the least that is a history; one week is a deposit.
MIN_WEEKS = 2
# How many bars the equity chart is drawn with. A decade of weekly bars is five hundred of them
# across the plot, which is thinner than the gap between them.
CHART_WEEKS = 130

CENTS = Decimal("0.01")


def combinations(grid=None, fee=FEE_DEFAULT):
    """Every parameter set the sweep tries over `grid`, at one `fee`, in a fixed order.

    Both plans are always swept: comparing them is what the page is for, so the grid says only how
    wide each of the three settings runs. The fee rides along on every combination rather than
    being one of them, since it is the cost the whole sweep is being run at.

    The order is what lets the page run the sweep in slices without holding any state: a batch is
    a stretch of this list, and asking for the first two hundred twice gives the same two hundred.
    """
    ranges = grid or DEFAULTS
    return [
        combination(*parameters, fee=fee)
        for parameters in product(PLANS, *(_span(ranges[setting]) for setting in DEFAULTS))
    ]


def combination(strategy, percent, short, multiplier, fee):
    """One parameter set, built the same way the grid builds every one of its own.

    So the plan's own page describes exactly what the sweep ran, rather than a second shape of the
    same thing that could drift away from it.
    """
    return {
        "strategy": strategy,
        "plan": PLANS[strategy],
        "percent": percent,
        "short": short,
        "multiplier": multiplier,
        "fee": fee,
        "long": short * multiplier,
    }


def count(grid=None):
    """How many combinations a grid comes to, without building a single one of them.

    So a grid can be turned away for being too big before anything has been spent on it.
    """
    ranges = grid or DEFAULTS
    return len(PLANS) * math.prod(high - low + 1 for low, high in ranges.values())


def search(prices, upto, grid=None, fee=FEE_DEFAULT):
    """Run the first `upto` combinations over `prices` and give back what each came to.

    The averages are worked out once for the whole batch, since the same span turns up in dozens
    of combinations — a 200-day average is a 20-day one times ten and a 25-day one times eight.

    Only the totals are kept. A sweep at the cap is five thousand walks through five hundred weeks,
    and holding every week of every one of them would cost hundreds of megabytes to answer a
    question nobody asked: the sweep is read for which combination won, and the weeks behind any one
    of them are a `replay` away whenever they are actually wanted.
    """
    combos = combinations(grid, fee)[:upto]
    spans = {span for combo in combos for span in (combo["short"], combo["long"])}
    averages = moving_averages(prices, spans)
    results = []
    for combo in combos:
        outcome = run(prices, averages, combo)
        if outcome is not None:
            results.append(combo | {key: outcome[key] for key in TOTALS})
    return results


def hold(prices, fee=FEE_DEFAULT, first=0):
    """The baseline: every week's contribution buys Bitcoin, and none of it is ever sold.

    What the same money would have come to with no plan at all — no averages read, no wallet moved,
    nothing to get right. A plan is only worth running if it beats this, and a sweep that cannot say
    whether it did is a ranking of plans against each other and nothing more.

    It is contributed the same R1 000 a week and pays the same fee on each purchase, and `first`
    starts it on the same week as the plan it is set against — a baseline running a different number
    of weeks on different money would not be one.
    """
    weeks = []
    bitcoin = contributed = paid = 0.0
    for index in _week_days(len(prices), first):
        price = prices[index]
        contributed += WEEKLY_CONTRIBUTION
        charged = WEEKLY_CONTRIBUTION * fee / 100
        paid += charged
        bitcoin += (WEEKLY_CONTRIBUTION - charged) / price
        held = bitcoin * price
        weeks.append(
            {
                "day": index,
                "price": price,
                "charged": charged,
                "zar": 0.0,
                "bitcoin": held,
                "value": held,
                "contributed": contributed,
                "profit": held - contributed,
            }
        )

    if len(weeks) < MIN_WEEKS:
        return None
    final = weeks[-1]["bitcoin"]
    return {
        "plan": HOLD,
        "weeks": weeks,
        "contributed": contributed,
        "paid": paid,
        "final": final,
        "profit": final - contributed,
    }


def replay(prices, combo):
    """Run one combination again, week by week, for the chart and for the plan's own page.

    The sweep throws the weeks away, so anything wanting them asks for them back. It is one walk
    through the history and costs nothing worth saving.
    """
    return run(prices, moving_averages(prices, {combo["short"], combo["long"]}), combo)


def best(results):
    """The combination that ended with the most, or None before any has been run."""
    return max(results, key=lambda result: result["profit"], default=None)


def report(results):
    """The sweep read back a setting at a time, one table per setting in `TABS`.

    A sweep is run to find out what a setting is worth, and a list of the best few combinations
    cannot say that — the top ten of a grid are usually the same setting ten times over, which
    tells you nothing about the nine values it beat. So each table takes one setting, lists every
    value it was swept over, and shows the best result found at that value.

    Each table is complete in itself and sorted by profit, best first, so it reads as a ranking of
    that setting's values. The plan's table is therefore two rows — the best each way round — and
    the order they come out in is the answer to which way round the history rewarded.
    """
    return [
        {
            "label": label,
            "setting": setting,
            "rows": sorted(
                (
                    max(
                        (result for result in results if result[setting] == value),
                        key=lambda result: result["profit"],
                    )
                    for value in {result[setting] for result in results}
                ),
                key=lambda result: result["profit"],
                reverse=True,
            ),
        }
        for setting, label in TABS.items()
    ]


def run(prices, averages, combo):
    """Walk one plan through the history a week at a time, and say what it came to.

    Weeks are counted back from the last day in sevens rather than run off the calendar, so the
    final week is where the history ends and every earlier one is the same weekday before it — the
    same way the ledger's own profit chart picks its weeks. A week before the long average has
    started is not a week the plan could have read, so the walk begins where that average does.

    Each week the contribution arrives and is put where the reading says, and then a slice of the
    source wallet is moved the same way. The slice is taken from the wallet it leaves, so neither
    can be spent past empty. None when the history is too short for the averages asked for.

    Every week is kept in full — what it read, what it moved and where both wallets stood after —
    because the plan's own page lists them, and a week that only reported its totals could not be
    checked against the price it was acting on.
    """
    short_average = averages[combo["short"]]
    long_average = averages[combo["long"]]
    fraction = combo["percent"] / 100
    rate = combo["fee"] / 100
    strategy = combo["strategy"]

    weeks = []
    zar = bitcoin = contributed = paid = 0.0
    for index in _week_days(len(prices), combo["long"] - 1):
        price = prices[index]
        signal = _signal(strategy, short_average[index], long_average[index])
        contributed += WEEKLY_CONTRIBUTION
        if signal == UP:
            # The contribution and a slice of the rand wallet both become Bitcoin, and the fee is
            # taken off the lot of it — a contribution is a purchase like any other.
            moved = zar * fraction
            zar -= moved
            charged = (WEEKLY_CONTRIBUTION + moved) * rate
            bitcoin += (WEEKLY_CONTRIBUTION + moved - charged) / price
        else:
            # The contribution lands as rands and converts nothing, so it is charged nothing; only
            # the Bitcoin sold back pays.
            zar += WEEKLY_CONTRIBUTION
            sold = bitcoin * fraction
            bitcoin -= sold
            moved = -sold * price
            charged = -moved * rate
            zar += -moved - charged
        paid += charged
        held = bitcoin * price
        weeks.append(
            {
                "day": index,
                "price": price,
                "signal": signal,
                "short": short_average[index],
                "long": long_average[index],
                "moved": moved,
                "charged": charged,
                "zar": zar,
                "bitcoin": held,
                "value": zar + held,
                "contributed": contributed,
                "profit": zar + held - contributed,
            }
        )

    if len(weeks) < MIN_WEEKS:
        return None
    final = weeks[-1]["zar"] + weeks[-1]["bitcoin"]
    return {
        "weeks": weeks,
        "contributed": contributed,
        "paid": paid,
        "final": final,
        "profit": final - contributed,
    }


def moving_averages(prices, spans):
    """The mean of the last `span` prices at each day, for each span asked for."""
    return {span: _moving_average(prices, span) for span in spans}


def equity_weeks(result, dates):
    """One run as the profit chart takes it: the money put in, and the two wallets holding it.

    The contribution hangs below the axis and the wallets stand above, so what is left when the two
    ends are added back together is the profit — the same picture the accounts page draws, over a
    plan that was never run rather than the ledger that was. The Bitcoin wallet is last so it
    stacks on top, being the only one whose value moves on its own.

    Sampled down to about `CHART_WEEKS` bars, since a decade of weekly ones is too thin to read,
    and rounded to the cent, since the chart is where these figures stop being floats.
    """
    weeks = result["weeks"]
    step = max(len(weeks) // CHART_WEEKS, 1)
    sampled = weeks[::step]
    if sampled[-1]["day"] != weeks[-1]["day"]:
        sampled.append(weeks[-1])
    return [
        {
            "date": dates[week["day"]],
            "parts": [
                {"label": "Contributed", "value": -_cents(week["contributed"])},
                {"label": "Rand wallet", "value": _cents(week["zar"])},
                {"label": "Bitcoin wallet", "value": _cents(week["bitcoin"])},
            ],
        }
        for week in sampled
    ]


def _signal(strategy, short, long_average):
    """Which wallet this week's money belongs in: UP for Bitcoin, DOWN for rands.

    One average is always over the other, so there is always a reading and a plan never sits a week
    out. The two plans are that one reading taken the two ways round: whichever way `rise` sends
    the money on a week, `fall` sends it the other.
    """
    rising = short > long_average
    if strategy == FALL:
        rising = not rising
    return UP if rising else DOWN


def _span(bounds):
    """A range from a lowest and a highest, both of them included."""
    low, high = bounds
    return range(low, high + 1)


def _week_days(days, first):
    """Which day each week is read at, oldest first: every seventh, counted back from the last."""
    return sorted(range(days - 1, first - 1, -DAYS_PER_WEEK))


def _moving_average(prices, span):
    """The mean of the last `span` prices at each point, None until there are that many."""
    averages = []
    running = 0.0
    for index, price in enumerate(prices):
        running += price
        if index >= span:
            running -= prices[index - span]
        averages.append(running / span if index >= span - 1 else None)
    return averages


def _cents(amount):
    """A float becoming a figure on a chart, which has never needed more than two places."""
    return Decimal(amount).quantize(CENTS)
