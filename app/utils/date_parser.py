"""Normalize the several date shapes CT.gov returns into (year, month).

CT.gov mixes ISO dates, year-month, bare years, English month names, and
date-struct dicts. One tolerant parser handles them all and never raises.
"""

import re

_MONTHS = {
    name.lower(): num
    for num, name in enumerate(
        [
            "January",
            "February",
            "March",
            "April",
            "May",
            "June",
            "July",
            "August",
            "September",
            "October",
            "November",
            "December",
        ],
        start=1,
    )
}
# Add 3-letter abbreviations ("jan", "feb", ...).
_MONTHS.update({name[:3]: num for name, num in list(_MONTHS.items())})

# 2024-01-15 / 2024-01 / 2024  (numeric, anchored)
_ISO = re.compile(r"^(\d{4})(?:-(\d{1,2}))?(?:-\d{1,2})?$")
# "January 2024" / "January 15, 2024" / "Jan 2024"  (month word + year)
_TEXT = re.compile(r"([A-Za-z]{3,9})\.?\s+(?:\d{1,2},?\s+)?(\d{4})")


def parse_date(value) -> tuple[int | None, int | None]:
    """Parse a messy CT.gov date into (year, month); (None, None) if unparseable."""
    if isinstance(value, dict):
        return parse_date(value.get("date"))
    if not isinstance(value, str):
        return (None, None)
    s = value.strip()
    if not s:
        return (None, None)

    m = _ISO.match(s)
    if m:
        year = int(m.group(1))
        month = int(m.group(2)) if m.group(2) else None
        if month is not None and not (1 <= month <= 12):
            month = None
        return (year, month)

    t = _TEXT.search(s)
    if t:
        return (int(t.group(2)), _MONTHS.get(t.group(1).lower()))

    return (None, None)
