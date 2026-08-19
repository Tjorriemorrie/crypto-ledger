"""The geometry behind the ledger's charts, and nothing else.

All of them are plain SVG drawn by their templates: no charting library, and the browser fetches
no data of its own. Every coordinate is worked out here and handed to the template as a string,
already rounded, so the template only places what it is given and nothing arrives at the
browser needing arithmetic. Nothing here reads the database — a chart is handed the series it
draws.

The price chart is one asset over one window: the daily close and a moving average over it. The
close is drawn in runs rather than as one line, since its colour says whether the short average
is over the long one on that day. Under it sits a strip on the same dates — how far the close
stands from where it was a long average ago — sharing the x axis and carrying a zero line of its
own.

The profit chart is the whole ledger over a longer one: what each account held at the close of a
week, stacked into one bar, with the profit that is the net of the stack drawn over it and a
straight trend through that. The analysis page draws its own runs with the same function, an
investment plan's two wallets standing in for the ledger's accounts.

The results chart is the analysis page's sweep: a mark per combination tried, placed across the
plot by its position in the grid, so the picture fills in from the left as the sweep runs.

They all label the value down each side of the plot — the same scale twice, so the right-hand end
of a long window reads without tracking back across it.
"""

import math
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal

ZERO = Decimal(0)

# The days drawn, and the averages drawn over them. An average needs the days before the
# window as well as the days in it, or it would only start once it was far enough in; the lead
# handed over with the window is what lets both lines run the whole width of the plot.
DAYS = 260
SMAS = (26, 260)

# The strip under the price plot: the close against the close `CHANGE_SPAN` days before it. The
# span is the long average's, which is not a coincidence worth hiding — it is the longest run of
# days the chart already has the lead for, so the strip costs no extra price. What it is for
# is written out on the page: it is the one reading that tracks whether simply holding Bitcoin has
# been better than the analysis page's plans, and it says nothing about the days after it.
CHANGE_SPAN = max(SMAS)
# The days wanted behind the window, so that both averages and the strip have a figure on its
# very first day. An average of n days needs the n - 1 days before it; the strip reaches one day
# further back than that, so it is what the lead is sized on.
LEAD_DAYS = CHANGE_SPAN
# The whole series the price chart is handed: the window drawn, and the lead behind it.
PRICE_DAYS = DAYS + LEAD_DAYS
STRIP_HEIGHT = 72
# Room between the price plot and the strip, so the two read as separate panels rather than one.
STRIP_GAP = 26
STRIP_TICKS = 3

# What the close is coloured by: whether the short average is above the long one that day.
# It takes two averages to say that, so a chart drawn with fewer leaves the close plain.
UP = "up"
DOWN = "down"
MIN_TREND_AVERAGES = 2

WIDTH = 960
HEIGHT = 360
# Room for a price down each side of the plot, and for the dates under it.
PAD_LEFT = 88
PAD_RIGHT = 88
PAD_TOP = 16
PAD_BOTTOM = 28

RIGHT = WIDTH - PAD_RIGHT
BOTTOM = HEIGHT - PAD_BOTTOM
PLOT_WIDTH = RIGHT - PAD_LEFT
PLOT_HEIGHT = BOTTOM - PAD_TOP

# The price chart is the one with a strip under it, so it is the one that is taller. The profit and
# results charts keep `HEIGHT`, and the plot itself is where it always was — the strip is hung below
# it, and the dates move under the strip, rather than the price being squeezed to make room.
STRIP_TOP = BOTTOM + STRIP_GAP
STRIP_BOTTOM = STRIP_TOP + STRIP_HEIGHT
PRICE_HEIGHT = STRIP_BOTTOM + PAD_BOTTOM

# About this many value gridlines; the rounding of the axis decides the exact number. The profit
# chart asks for more of them because it has to hold zero as well as its figures, which is a
# wider range to round out — with five it would draw itself across the middle of a mostly empty
# axis.
PRICE_TICKS = 5
PROFIT_TICKS = 8
DATE_TICKS = 6
# Two points is the least that makes a line; one figure is a number, not a chart.
MIN_POINTS = 2

# The gaps a price axis is allowed to step in, times a power of ten. A gridline is there to be
# read off, and 250 000 is a figure the eye can carry across the plot where 237 419 is not.
STEPS = (Decimal(1), Decimal(2), Decimal("2.5"), Decimal(5), Decimal(10))

DOT_RADIUS = 4
# The tooltip is sized here rather than by the browser, since SVG will not grow a box to fit
# the text put inside it. The figures are tabular and short, so a width per character does.
TIP_CHAR_WIDTH = 6.6
TIP_PADDING = 10
TIP_HEIGHT = 44
TIP_GAP = 12
TIP_LINE = 16
# Where a line's text sits inside the strip of height reserved for it.
TIP_BASELINE = 12
# The blank kept between a label and the figure against the other edge of the panel.
TIP_COLUMN_GAP = 3

# How many colours the stacked bars cycle through, so a chart knows when to start again. The
# colours themselves are in the stylesheet; a bar only carries which of them it is.
SERIES_COLOURS = 7
# A hair between one week's bar and the next, so a hundred of them do not read as one block.
BAR_GAP = 1


def price_chart(series, asset):
    """Lay out the last `DAYS` of `series`, oldest first, or None when there is too little.

    A series is `(date, price)` a day, the price being that day's close in ZAR. Anything handed
    over beyond the window is not drawn — it is the lead, there to give the moving averages and
    the strip the days behind them they need on the window's very first day. Gaps in the dates
    are not spaced out: a day with no price is simply not a point, and the lines join up the days
    there are.
    """
    shown = series[-DAYS:]
    if len(shown) < MIN_POINTS:
        return None

    prices = [price for _, price in series]
    averages = [(span, _moving_average(prices, span)[-len(shown) :]) for span in sorted(SMAS)]
    plotted = [price for _, price in shown]
    plotted += [value for _, line in averages for value in line if value is not None]
    low, tick, gridlines = _scale(min(plotted), max(plotted))
    high = low + tick * (gridlines - 1)
    step = PLOT_WIDTH / (len(shown) - 1)

    def x_at(index):
        return PAD_LEFT + index * step

    def y_at(price):
        return BOTTOM - float((price - low) / (high - low)) * PLOT_HEIGHT

    points = [
        _point(day, price, (x_at(index), y_at(price)), step, asset)
        for index, (day, price) in enumerate(shown)
    ]
    # Lines and no fill under them: the axis does not start at zero, and a filled area would
    # read as a quantity measured from a baseline that is not there.
    average_lines = _average_lines(averages, x_at, y_at)
    close = _close_lines(points, averages)
    strip = _change_strip(_changes(prices, CHANGE_SPAN)[-len(shown) :], x_at)
    return {
        "asset": asset,
        "close": close,
        "averages": average_lines,
        "key": _key(close, average_lines),
        "points": points,
        "change": strip,
        "prices": _value_ticks(low, tick, gridlines),
        "dates": _date_ticks([day for day, _ in shown], x_at, _day_label, bottom=STRIP_BOTTOM),
        "plot": {
            "x": _n(PAD_LEFT),
            "y": _n(PAD_TOP),
            "height": _n(PLOT_HEIGHT),
            "right": _n(RIGHT),
            "bottom": _n(BOTTOM),
        },
        "width": WIDTH,
        "height": PRICE_HEIGHT,
        "tip_height": _n(TIP_HEIGHT),
        "dot_radius": DOT_RADIUS,
        "first": shown[0][0],
        "last": shown[-1][0],
    }


def _changes(prices, span):
    """How far each price stands from the one `span` places before it, as a fraction of it.

    Counted in places rather than in dates, the same way the moving averages are: a day the ledger
    holds no price for is not a point on this chart, so the run of prices is what a span counts. A
    day without `span` days behind it has no reading rather than a guessed one.
    """
    return [
        prices[index] / prices[index - span] - 1 if index >= span and prices[index - span] else None
        for index in range(len(prices))
    ]


def _change_strip(changes, x_at):
    """The band under the price plot: the close against where it stood a long average ago.

    Drawn as one line over a zero line, filled between the two. The price plot above carries no
    fill because its axis does not start at zero and an area would read as a quantity measured from
    a baseline that is not there; here the baseline is real and is the whole reading, so the fill
    is the thing that says how far from it the price has got, and for how long.

    It is deliberately not coloured by which side of the line it is on. The close above it is
    already coloured green and purple for a different reading altogether, and a second pair of
    colours on one picture would be read as the same statement twice. Which side the strip is on is
    said by where it sits and, in words, in the key.

    None when the window has no day with `CHANGE_SPAN` days behind it — a ledger holding only a
    few prices draws its close and no strip, rather than a strip drawn off one reading.
    """
    points = [(index, value) for index, value in enumerate(changes) if value is not None]
    if len(points) < MIN_POINTS:
        return None

    values = [value for _, value in points]
    low, tick, gridlines = _scale(min(*values, ZERO), max(*values, ZERO), STRIP_TICKS)
    high = low + tick * (gridlines - 1)

    def y_at(value):
        return STRIP_BOTTOM - float((value - low) / (high - low)) * STRIP_HEIGHT

    line = " ".join(f"{_n(x_at(index))},{_n(y_at(value))}" for index, value in points)
    zero = _n(y_at(ZERO))
    latest = points[-1][1]
    return {
        "line": line,
        # The area closes back along the zero line, so a reading that crosses it fills to the
        # baseline on both sides rather than to the foot of the strip.
        "area": f"{_n(x_at(points[0][0]))},{zero} {line} {_n(x_at(points[-1][0]))},{zero}",
        "zero": zero,
        "values": _value_ticks(
            low, tick, gridlines, label=_percent, panel=(STRIP_BOTTOM, STRIP_HEIGHT)
        ),
        "span": CHANGE_SPAN,
        "latest": _percent(latest, places=1),
        "ahead": latest > ZERO,
        "plot": {
            "x": _n(PAD_LEFT),
            "y": _n(STRIP_TOP),
            "height": _n(STRIP_HEIGHT),
            "right": _n(RIGHT),
            "bottom": _n(STRIP_BOTTOM),
        },
    }


def _close_lines(points, averages):
    """The close, cut into runs of days that agree on which average is on top.

    A run keeps the point before it as well, so the colour turns on the crossing itself and the
    line has no gap at the join. Days without both averages behind them — a chart too short for
    them to have started — are drawn plain rather than guessed at.
    """
    trend = _trend(averages, len(points))
    runs = []
    for index, point in enumerate(points):
        if runs and runs[-1]["state"] == trend[index]:
            runs[-1]["points"].append(point)
        else:
            runs.append(
                {"state": trend[index], "points": ([points[index - 1]] if index else []) + [point]}
            )
    return [
        {
            "state": run["state"],
            "css": f"line {run['state']}" if run["state"] else "line",
            "line": " ".join(f"{point['x']},{point['y']}" for point in run["points"]),
        }
        for run in runs
        if len(run["points"]) >= MIN_POINTS
    ]


def _trend(averages, count):
    """Which average is on top on each day, or None where one of them has not started."""
    if len(averages) < MIN_TREND_AVERAGES:
        return [None] * count
    fast, slow = averages[0][1], averages[-1][1]
    return [
        None if quick is None or steady is None else (UP if quick > steady else DOWN)
        for quick, steady in zip(fast, slow, strict=True)
    ]


def _key(close, averages):
    """What each line on the plot is, in the words that go beside its swatch.

    Four lines in two colours apiece is more than a reader should have to work out, so every
    one of them is named — and the close is named by what its colour means, not just as the
    close, since that is the only place the crossing is written down.
    """
    fast, slow = min(SMAS), max(SMAS)
    labels = {
        UP: f"Close, {fast} above {slow}",
        DOWN: f"Close, {fast} below {slow}",
        None: "Close",
    }
    drawn = {run["state"] for run in close}
    return [
        {"css": f"line {state}" if state else "line", "label": labels[state]}
        for state in (UP, DOWN, None)
        if state in drawn
    ] + [{"css": average["css"], "label": average["label"]} for average in averages]


def _moving_average(prices, span):
    """The mean of the last `span` prices at each point, None until there are that many."""
    averages = []
    running = Decimal(0)
    for index, price in enumerate(prices):
        running += price
        if index >= span:
            running -= prices[index - span]
        averages.append(running / span if index >= span - 1 else None)
    return averages


def _average_lines(averages, x_at, y_at):
    """The moving averages as lines, each labelled for the legend the chart carries.

    Three lines on one plot need saying apart by something other than the eye, so each is
    named. An average with too few days behind it to have started is left off altogether
    rather than drawn from where it happens to begin.
    """
    lines = []
    for position, (span, series) in enumerate(averages, start=1):
        drawn = [
            f"{_n(x_at(index))},{_n(y_at(value))}"
            for index, value in enumerate(series)
            if value is not None
        ]
        if len(drawn) >= MIN_POINTS:
            lines.append(
                {"css": f"sma sma-{position}", "label": f"{span}-day", "line": " ".join(drawn)}
            )
    return lines


def profit_chart(weeks):
    """Lay out the ledger's profit over `weeks`, as a stacked bar a week with a trend over it.

    Each week is `{"date": date, "parts": [{"label": str, "value": Decimal}, ...]}`, oldest first,
    dated to the week's close and every one of them carrying the same accounts in the same order.
    The bar's two ends are the money put in and what that money is now holding, so the profit is
    the net of the stack — and the eye cannot read the difference between two stacks, so it is
    drawn over the bars as a line, with a straight least-squares line through it for the trend.
    """
    if len(weeks) < MIN_POINTS:
        return None

    stacks = [_stack(week["parts"]) for week in weeks]
    profits = [stack["profit"] for stack in stacks]
    trend = _trend_values(profits)
    # Zero is in the range whatever the figures do: a stack read from both sides of the axis is
    # meaningless without the axis itself on the plot.
    spanned = [ZERO, trend[0], trend[-1], *profits]
    spanned += [
        edge
        for stack in stacks
        for segment in stack["segments"]
        for edge in (segment["bottom"], segment["top"])
    ]
    low, tick, gridlines = _scale(min(spanned), max(spanned), ticks=PROFIT_TICKS)
    high = low + tick * (gridlines - 1)
    step = PLOT_WIDTH / len(weeks)

    def x_at(index):
        # A bar takes up its week rather than sitting on a gridline, so it is centred in its share
        # of the plot and the profit line runs through those centres.
        return PAD_LEFT + (index + 0.5) * step

    def y_at(value):
        return BOTTOM - float((value - low) / (high - low)) * PLOT_HEIGHT

    return {
        "bars": [
            _bar(week, stack, x_at(index), y_at, step)
            for index, (week, stack) in enumerate(zip(weeks, stacks, strict=True))
        ],
        "profit": " ".join(
            f"{_n(x_at(index))},{_n(y_at(value))}" for index, value in enumerate(profits)
        ),
        "trend": {
            "x1": _n(x_at(0)),
            "y1": _n(y_at(trend[0])),
            "x2": _n(x_at(len(weeks) - 1)),
            "y2": _n(y_at(trend[-1])),
        },
        "key": _profit_key(weeks[0]["parts"]),
        "values": _value_ticks(low, tick, gridlines),
        "zero": _n(y_at(ZERO)),
        "dates": _date_ticks([week["date"] for week in weeks], x_at, _month_label),
        "plot": {
            "x": _n(PAD_LEFT),
            "y": _n(PAD_TOP),
            "height": _n(PLOT_HEIGHT),
            "right": _n(RIGHT),
            "bottom": _n(BOTTOM),
        },
        "width": WIDTH,
        "height": HEIGHT,
        "dot_radius": DOT_RADIUS,
        "first": weeks[0]["date"],
        "last": weeks[-1]["date"],
    }


def _stack(parts):
    """One week's bar: where each account sits in it, and the profit the whole of it nets to.

    An account is stacked above the axis where it holds and below it where it does not, the two
    signs running away from the axis rather than cancelling, so the bar shows the money put in
    and what it is holding as the two things they are. What is left when the two ends are added
    back together is the profit.
    """
    above = below = ZERO
    segments = []
    for position, part in enumerate(parts, start=1):
        value = part["value"]
        if value < 0:
            top, bottom = below, below + value
            below = bottom
        else:
            bottom, top = above, above + value
            above = top
        segments.append(
            {
                "series": (position - 1) % SERIES_COLOURS + 1,
                "label": part["label"],
                "value": value,
                "bottom": bottom,
                "top": top,
            }
        )
    return {"segments": segments, "profit": above + below}


def _bar(week, stack, x, y_at, step):
    """One week: its stacked segments, the band that hovers it, and what that band shows.

    The panel breaks the bar back down account by account, since a stack is there to say what
    the profit is made up of and a reader should not have to measure a segment off the axis to
    find out. An account worth nothing that week is drawn as no segment but still listed, so the
    panel reads the same from one week to the next. Its date is named as the week it closes,
    because a bar covering seven days reads as one day otherwise.
    """
    width = max(step - BAR_GAP, 1)
    profit = stack["profit"]
    close = f"Week to {week['date'].day} {week['date']:%b %Y}"
    lines = [{"css": "date", "label": close, "value": ""}]
    lines += [
        {"css": "part", "label": segment["label"], "value": _money(segment["value"])}
        for segment in stack["segments"]
    ]
    # The net of one week is named the way the accounts page names it: a profit, or a loss when it
    # comes out negative.
    lines.append(
        {"css": "price", "label": "Profit" if profit >= 0 else "Loss", "value": _money(profit)}
    )
    return {
        "segments": [
            {
                "css": f"bar series-{segment['series']}",
                "x": _n(x - width / 2),
                "width": _n(width),
                "y": _n(y_at(segment["top"])),
                "height": _n(y_at(segment["bottom"]) - y_at(segment["top"])),
            }
            for segment in stack["segments"]
            if segment["top"] != segment["bottom"]
        ],
        "x": _n(x),
        "y": _n(y_at(profit)),
        "band_x": _n(x - step / 2),
        "band_width": _n(step),
        "tip": _tip(x, y_at(profit), lines),
    }


def _trend_values(profits):
    """The straight least-squares line through `profits`, as a figure for each week.

    Which way the profit has gone over the window, and nothing more: it is a reading of the bars
    already on the chart, and nothing in the ledger acts on it.
    """
    count = len(profits)
    middle = Decimal(count - 1) / 2
    mean = sum(profits, ZERO) / count
    spread = sum((Decimal(index) - middle) ** 2 for index in range(count))
    slope = (
        sum((Decimal(index) - middle) * (value - mean) for index, value in enumerate(profits))
        / spread
    )
    return [mean + slope * (Decimal(index) - middle) for index in range(count)]


def _profit_key(parts):
    """What each colour on the plot is: an account per swatch, then the two lines drawn over."""
    return [
        {"css": f"swatch series-{(position - 1) % SERIES_COLOURS + 1}", "label": part["label"]}
        for position, part in enumerate(parts, start=1)
    ] + [{"css": "net", "label": "Profit"}, {"css": "trend", "label": "Trend"}]


def results_chart(results, total, baseline=None):
    """Lay out a sweep's results so far: `{"label": str, "profit": float}` each, in grid order.

    A mark per combination, its profit up the plot and its place in the grid across it. The plot is
    always the width of the whole grid rather than of the results in hand, so a sweep still running
    fills in from the left and the picture is its own progress bar. The best so far is ringed,
    since which mark is highest is the whole question being asked.

    `baseline` is drawn across the plot as a line, so the marks above it are the combinations that
    beat doing nothing and the marks below it are the ones that were not worth running. That is a
    reading no ranking of the plans against each other can give.

    Marks and no line: consecutive combinations differ by one parameter and are not a series, so
    joining them up would draw a shape that means nothing.
    """
    if len(results) < MIN_POINTS:
        return None

    profits = [Decimal(result["profit"]).quantize(Decimal("0.01")) for result in results]
    # Zero is always on the plot: a sweep is read for whether a plan made money, and an axis that
    # does not hold zero cannot be read for that at a glance. So is the baseline, which is no use
    # off the top of the picture.
    spanned = [*profits, ZERO]
    if baseline is not None:
        baseline = Decimal(baseline).quantize(Decimal("0.01"))
        spanned.append(baseline)
    low, tick, gridlines = _scale(min(spanned), max(spanned))
    high = low + tick * (gridlines - 1)
    step = PLOT_WIDTH / total

    def x_at(index):
        return PAD_LEFT + (index + 0.5) * step

    def y_at(value):
        return BOTTOM - float((value - low) / (high - low)) * PLOT_HEIGHT

    labels = list(dict.fromkeys(result["label"] for result in results))
    series = {label: position % SERIES_COLOURS + 1 for position, label in enumerate(labels)}
    leader = max(range(len(profits)), key=profits.__getitem__)
    return {
        "marks": [
            {
                "css": f"mark series-{series[result['label']]}",
                "x": _n(x_at(index)),
                "y": _n(y_at(profit)),
            }
            for index, (result, profit) in enumerate(zip(results, profits, strict=True))
        ],
        "best": {"x": _n(x_at(leader)), "y": _n(y_at(profits[leader]))},
        "baseline": None if baseline is None else _n(y_at(baseline)),
        "key": [{"css": f"swatch series-{series[label]}", "label": label} for label in labels],
        "values": _value_ticks(low, tick, gridlines),
        "zero": _n(y_at(ZERO)),
        "counts": _index_ticks(total, x_at),
        "plot": {
            "x": _n(PAD_LEFT),
            "y": _n(PAD_TOP),
            "height": _n(PLOT_HEIGHT),
            "right": _n(RIGHT),
            "bottom": _n(BOTTOM),
        },
        "width": WIDTH,
        "height": HEIGHT,
        "dot_radius": DOT_RADIUS,
    }


def _index_ticks(total, x_at):
    """A handful of positions along the bottom, counting the combinations rather than dates."""
    last = total - 1
    indexes = sorted({round(last * index / (DATE_TICKS - 1)) for index in range(DATE_TICKS)})
    return [
        {"x": _n(x_at(index)), "y": _n(BOTTOM + 18), "label": f"{index + 1}"} for index in indexes
    ]


def _tip(x, y, lines):
    """A hover panel of labelled figures, sized to its longest line and placed beside `x`."""
    height = TIP_PADDING * 2 + TIP_LINE * len(lines)
    width = _tip_width(
        [
            f"{line['label']}{' ' * TIP_COLUMN_GAP}{line['value']}"
            if line["value"]
            else line["label"]
            for line in lines
        ]
    )
    left, top = _tip_box(x, y, width, height)
    return {
        "x": _n(left),
        "y": _n(top),
        "width": _n(width),
        "height": _n(height),
        "text_x": _n(left + TIP_PADDING),
        "value_x": _n(left + width - TIP_PADDING),
        "lines": [
            {**line, "y": _n(top + TIP_PADDING + TIP_LINE * index + TIP_BASELINE)}
            for index, line in enumerate(lines)
        ],
    }


def _scale(low, high, ticks=PRICE_TICKS):
    """The foot of the value axis, the gap between its gridlines, and how many there are.

    The gap is rounded to a figure worth reading off, and the axis is then opened out to the
    round numbers either side of the range seen. That rounding is also all the air the lines
    get: padding the range first and rounding after would step the gap up a size and leave the
    chart drawn across the middle third of an axis that is mostly empty. It is the number of
    gridlines that gives, not the size of the gap — `ticks` is what the range is aimed at, not
    what it comes out as.
    """
    span = high - low
    if span == 0:
        # A window holding one price the whole way through still needs a scale to sit on.
        span = high or Decimal(1)
    tick = _nice_step(span / (ticks - 1))
    bottom = (low / tick).to_integral_value(ROUND_FLOOR) * tick
    top = (high / tick).to_integral_value(ROUND_CEILING) * tick
    return bottom, tick, int((top - bottom) / tick) + 1


def _nice_step(size):
    """The smallest round gap no narrower than `size`."""
    magnitude = Decimal(10) ** math.floor(math.log10(float(size)))
    for multiple in STEPS:
        step = multiple * magnitude
        if step >= size:
            return step
    return magnitude * 10


def _point(day, close, at, step, asset):
    """One day: where its dot sits, the band that hovers it, and the tooltip that band shows."""
    x, y = at
    date = f"{day.day} {day:%b %Y}"
    price = _money(close)
    width = _tip_width([date, f"1 {asset} = {price}"])
    tip_x, tip_y = _tip_box(x, y, width, TIP_HEIGHT)
    return {
        "x": _n(x),
        "y": _n(y),
        "band_x": _n(x - step / 2),
        "band_width": _n(step),
        "date": date,
        "price": price,
        "tip_x": _n(tip_x),
        "tip_y": _n(tip_y),
        "tip_width": _n(width),
        "text_x": _n(tip_x + TIP_PADDING),
        "date_y": _n(tip_y + 18),
        "price_y": _n(tip_y + 34),
    }


def _tip_box(x, y, width, height):
    """Where a hover panel sits beside the point it belongs to.

    Worked out here because SVG cannot flip a box that runs off the edge of the picture by
    itself. It sits to the right until there is no room for it, then to the left, and is held
    inside the plot from top and bottom the same way.
    """
    left = x + TIP_GAP
    if left + width > WIDTH:
        left = x - TIP_GAP - width
    return left, min(max(y - height / 2, PAD_TOP), BOTTOM - height)


def _tip_width(lines):
    """How wide a hover panel has to be to hold `lines`.

    Sized here rather than by the browser, since SVG will not grow a box to fit the text put
    inside it. The text is tabular and short, so a width per character does.
    """
    return TIP_PADDING * 2 + TIP_CHAR_WIDTH * max(len(line) for line in lines)


def _value_ticks(low, tick, gridlines, label=None, panel=None):
    """The value gridlines, each labelled at both ends of its own line.

    `panel` is where they are drawn — its foot and its depth — because the price chart's strip is a
    second panel with an axis of its own, read in percentages rather than rands but laid out
    exactly the same way. The main plot is what it falls back on.
    """
    label = label or _money
    bottom, height = panel or (BOTTOM, PLOT_HEIGHT)
    return [
        {
            "y": _n(bottom - index / (gridlines - 1) * height),
            "label": label(low + tick * index),
            "left_x": _n(PAD_LEFT - 12),
            "right_x": _n(RIGHT + 12),
        }
        for index in range(gridlines)
    ]


def _date_ticks(dates, x_at, label, bottom=BOTTOM):
    """A handful of dates along the bottom, evenly spaced through the window.

    `bottom` is where they sit, since the price chart's dates go under its strip rather than
    between the two panels, both being read against the same days.
    """
    last = len(dates) - 1
    indexes = sorted({round(last * index / (DATE_TICKS - 1)) for index in range(DATE_TICKS)})
    return [
        {"x": _n(x_at(index)), "y": _n(bottom + 18), "label": label(dates[index])}
        for index in indexes
    ]


def _day_label(day):
    """A date on the price chart's axis: 260 days sit inside a year, so the day and month do."""
    return f"{day.day} {day:%b}"


def _month_label(day):
    """A date on the profit chart's axis: 100 weeks cross years, so it takes the year to place a
    tick, and the day of the month is noise at that width."""
    return f"{day:%b %Y}"


def _percent(fraction, places=0):
    """A fraction as a percentage, signed unless it is nothing.

    The sign is most of the reading here, so it is shown — but on zero itself it would read as a
    figure rounded up to nothing rather than as the line the rest is measured from.
    """
    return f"{fraction:.{places}%}" if not fraction else f"{fraction:+.{places}%}"


def _money(amount):
    """A figure for an axis or a tooltip: rands only, since a chart is read, not filed from."""
    amount = Decimal(amount)
    return f"-R {-amount:,.0f}" if amount < 0 else f"R {amount:,.0f}"


def _n(value):
    """Coordinates go to the template as strings, so no locale can reformat them."""
    return f"{value:.1f}"
