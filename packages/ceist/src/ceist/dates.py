"""Dates in questions: phrases → an inclusive range of days, and back to words.

    "in 1850"                1850-01-01 … 1850-12-31
    "before 1900"            … 1899-12-31
    "after 1900"             1901-01-01 …
    "since 1900"             1900-01-01 …
    "between 1800 and 1850"  1800-01-01 … 1850-12-31
    "in the 1890s"           1890-01-01 … 1899-12-31
    "the 19th century", "the 1800s"   1800-01-01 … 1899-12-31
    "May 2020", "2020-05", "2020-05-01"
    "today", "yesterday", "this/last week|month|year", "in the last 3 months"

A range is kept as ISO dates (either end may be open). `label(lo, hi)` gives
the canonical words for it, made from the range alone, so a plan and a
query compiled from it read back the same way. `days()` is the encoding
Alizarin's `quantize_date` (and so Rós Madair's `range`) uses: signed days
since 1970-01-01.
"""

import calendar
import re
from dataclasses import dataclass
from datetime import date, timedelta

_EPOCH = date(1970, 1, 1)
OPEN = 10 ** 9                      # days: an open end, far outside any real date

_MONTHS = {m.lower(): i for i, m in enumerate(calendar.month_name) if m}
_MONTHS.update({m.lower(): i for i, m in enumerate(calendar.month_abbr) if m})
_MONTHS["sept"] = 9
_MONTH = "|".join(sorted(_MONTHS, key=len, reverse=True))
_POINT = (r"(?:the\s+)?(?:"
          r"\d{4}-\d{2}-\d{2}|\d{4}-\d{2}"
          rf"|(?:{_MONTH})\.?\s+\d{{4}}"
          r"|\d{3}0s|\d{1,2}(?:st|nd|rd|th)\s+century"
          r"|1\d{3}|20\d{2}"
          r"|today|yesterday|(?:this|last)\s+(?:week|month|year))")
_B = r"(?<![a-z0-9-])"
_E = r"(?![a-z0-9])"
_PATTERNS = [
    ("last_n", rf"{_B}(?:(?:in|over|during|within)\s+)?the\s+(?:last|past)\s+(\d+)\s+"
               rf"(day|week|month|year)s?{_E}"),
    ("between", rf"{_B}(?:between|from)\s+({_POINT})\s+(?:and|to|until|till)\s+({_POINT}){_E}"),
    ("before", rf"{_B}(?:before|earlier\s+than|prior\s+to)\s+({_POINT}){_E}"),
    ("after", rf"{_B}(?:after|later\s+than)\s+({_POINT}){_E}"),
    ("since", rf"{_B}since\s+({_POINT}){_E}"),
    ("in", rf"{_B}(?:(?:in|during|on|of|from)\s+)?({_POINT}){_E}"),
]


@dataclass
class DateMatch:
    start: int
    end: int
    phrase: str
    lo: str | None
    hi: str | None


def _iso(d: date) -> str:
    return d.isoformat()


def _month_end(y: int, m: int) -> date:
    return date(y, m, calendar.monthrange(y, m)[1])


def _span(point: str, today: date) -> tuple[date, date] | None:
    p = re.sub(r"^the\s+", "", point.strip())
    if m := re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", p):
        d = date(*map(int, m.groups()))
        return d, d
    if m := re.fullmatch(r"(\d{4})-(\d{2})", p):
        y, mo = map(int, m.groups())
        return date(y, mo, 1), _month_end(y, mo)
    if m := re.fullmatch(rf"({_MONTH})\.?\s+(\d{{4}})", p):
        y, mo = int(m.group(2)), _MONTHS[m.group(1)]
        return date(y, mo, 1), _month_end(y, mo)
    if m := re.fullmatch(r"(\d{3})0s", p):
        y = int(m.group(1)) * 10
        width = 100 if y % 100 == 0 else 10          # "the 1800s" is a century
        return date(y, 1, 1), date(y + width - 1, 12, 31)
    if m := re.fullmatch(r"(\d{1,2})(?:st|nd|rd|th)\s+century", p):
        y = (int(m.group(1)) - 1) * 100
        return date(max(y, 1), 1, 1), date(y + 99, 12, 31)
    if re.fullmatch(r"\d{4}", p):
        y = int(p)
        return date(y, 1, 1), date(y, 12, 31)
    if p == "today":
        return today, today
    if p == "yesterday":
        d = today - timedelta(days=1)
        return d, d
    if m := re.fullmatch(r"(this|last)\s+(week|month|year)", p):
        which, unit = m.groups()
        if unit == "year":
            y = today.year - (which == "last")
            return date(y, 1, 1), date(y, 12, 31)
        if unit == "month":
            first = today.replace(day=1)
            if which == "last":
                first = (first - timedelta(days=1)).replace(day=1)
            return first, _month_end(first.year, first.month)
        start = today - timedelta(days=today.weekday())
        if which == "last":
            start -= timedelta(days=7)
        return start, start + timedelta(days=6)
    return None


def _ago(today: date, n: int, unit: str) -> date:
    if unit == "day":
        return today - timedelta(days=n)
    if unit == "week":
        return today - timedelta(weeks=n)
    months = n * (12 if unit == "year" else 1)
    y, m = divmod(today.year * 12 + today.month - 1 - months, 12)
    m += 1
    return date(y, m, min(today.day, calendar.monthrange(y, m)[1]))


def find(raw: str, taken: list[tuple[int, int]], today: date | None = None) -> list[DateMatch]:
    """Every date phrase in `raw` (lowercase), longest construction first;
    spans already in `taken` are skipped, and new ones are added to it."""
    today = today or date.today()
    out = []
    for kind, pattern in _PATTERNS:
        for m in re.finditer(pattern, raw):
            if any(m.start() < e and m.end() > s for s, e in taken):
                continue
            if kind == "last_n":
                lo, hi = _ago(today, int(m.group(1)), m.group(2)), today
            else:
                spans = [_span(g, today) for g in m.groups()]
                if not all(spans):
                    continue
                if kind == "between":
                    lo, hi = spans[0][0], spans[1][1]
                elif kind == "before":
                    lo, hi = None, spans[0][0] - timedelta(days=1)
                elif kind == "after":
                    lo, hi = spans[0][1] + timedelta(days=1), None
                elif kind == "since":
                    lo, hi = spans[0][0], None
                else:
                    lo, hi = spans[0]
            taken.append((m.start(), m.end()))
            out.append(DateMatch(m.start(), m.end(), m.group().strip(),
                                 _iso(lo) if lo else None, _iso(hi) if hi else None))
    return sorted(out, key=lambda d: d.start)


# ── the encoding, and back to words ──────────────────────────────────────

def days(iso: str) -> int:
    """Days since 1970-01-01 — Alizarin's quantize_date for YYYY[-MM[-DD]]."""
    parts = [int(x) for x in iso[:10].split("-") if x]
    parts += [1] * (3 - len(parts))
    return (date(*parts) - _EPOCH).days


def from_days(n: int) -> str | None:
    if abs(n) >= OPEN:
        return None
    return _iso(_EPOCH + timedelta(days=n))


def _ordinal(n: int) -> str:
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _whole(lo: date, hi: date) -> str | None:
    """Words for a span of whole years or one whole month, or None."""
    if (lo.month, lo.day, hi.month, hi.day) == (1, 1, 12, 31):
        if lo.year == hi.year:
            return str(lo.year)
        if lo.year % 100 == 0 and hi.year == lo.year + 99:
            return f"the {_ordinal(lo.year // 100 + 1)} century"
        if lo.year % 10 == 0 and hi.year == lo.year + 9:
            return f"the {lo.year}s"
        return None
    if lo.day == 1 and (lo.year, lo.month) == (hi.year, hi.month) and hi == _month_end(hi.year, hi.month):
        return f"{calendar.month_name[lo.month]} {lo.year}"
    return None


def label(lo: str | None, hi: str | None) -> str:
    """The canonical words for a range: 'in 1850', 'before 1900', 'after
    1900', 'between 1800 and 1850', 'in the 1890s', 'on 2020-05-01'."""
    a = date.fromisoformat(lo) if lo else None
    b = date.fromisoformat(hi) if hi else None
    if a and b:
        if a == b:
            return f"on {lo}"
        whole = _whole(a, b)
        if whole:
            return f"in {whole}"
        if (a.month, a.day, b.month, b.day) == (1, 1, 12, 31):
            return f"between {a.year} and {b.year}"
        return f"between {lo} and {hi}"
    if b:
        nxt = b + timedelta(days=1)
        if (nxt.month, nxt.day) == (1, 1):
            return f"before {nxt.year}"
        if nxt.day == 1:
            return f"before {calendar.month_name[nxt.month]} {nxt.year}"
        return f"before {nxt.isoformat()}"
    if a:
        prev = a - timedelta(days=1)
        if (prev.month, prev.day) == (12, 31):
            return f"after {prev.year}"
        if a.day == 1:
            return f"after {calendar.month_name[prev.month]} {prev.year}"
        return f"after {prev.isoformat()}"
    return "any date"
