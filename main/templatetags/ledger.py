"""Template filters for rendering ledger quantities and their ZAR value."""

from decimal import Decimal, InvalidOperation

from django import template

register = template.Library()


@register.filter
def qty(value):
    """Render a quantity without the 18 stored decimal places of trailing zeros."""
    if value is None or value == "":
        return ""
    try:
        number = Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        return value
    number = number.normalize()
    if number == number.to_integral_value():
        number = number.quantize(Decimal(1))
    return f"{number:f}"


@register.filter
def zar(value):
    """Render a ZAR amount to the cent, or a dash when there is no rate to value it with."""
    if value is None:
        return "—"
    try:
        number = Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        return value
    return f"R {number:,.2f}"
