"""Calendar helpers used only by tests (moved out of src as production dead code)."""

import QuantLib as ql

from deskpricer.pricing.conventions import CalendarLiteral, get_calendar


def annual_business_days(calendar_name: CalendarLiteral, year: int) -> int:
    """Return the number of business days in ``year`` according to ``calendar_name``."""
    calendar = get_calendar(calendar_name)
    start = ql.Date(1, 1, year)
    end = ql.Date(31, 12, year) + 1
    return count_business_days(start, end, calendar)


def count_business_days(start: ql.Date, end: ql.Date, calendar: ql.Calendar) -> int:
    """Count the number of business days in ``[start, end)`` using ``calendar``.

    Returns ``0`` when ``start == end``.  Callers that need a minimum of
    one business day should apply ``max(count_business_days(...), 1)``
    explicitly at the call site.
    """
    count = 0
    d = start
    while d < end:
        if calendar.isBusinessDay(d):
            count += 1
        d += 1
    return count
