"""Numeric comparisons in questions: "capacity over 200", "taller than 30 metres",
"worth more than 5 crore", and the words that say them back.

    over / more than / above / greater than / exceeding / taller / bigger than N   > N
    under / less than / below / fewer than / shorter than / smaller than N         < N
    at least / no less than / a minimum of / room for / holds / capacity of N      >= N
    at most / no more than / up to / a maximum of N                                <= N
    between N and M                                                                N <= v <= M
    exactly N, of N                                                                = N

Units and money multipliers are arithmetic, so they are fixed here, not in a
vocabulary. The phrasings and money units follow Phil's `numbers.rs`
(aonach-responder, crates/greasan-ask), credited in PRIOR-ART.md.
"""

import re
from dataclasses import dataclass
from decimal import Decimal

from .text import overlaps

# unit → (kind, factor to the kind's base: metres, or the amount itself)
UNITS = {
    "m": ("length", 1), "metre": ("length", 1), "metres": ("length", 1),
    "meter": ("length", 1), "meters": ("length", 1),
    "km": ("length", 1000), "kilometre": ("length", 1000), "kilometres": ("length", 1000),
    "kilometer": ("length", 1000), "kilometers": ("length", 1000),
    "ft": ("length", 0.3048), "foot": ("length", 0.3048), "feet": ("length", 0.3048),
    "thousand": ("money", 10 ** 3), "k": ("money", 10 ** 3),
    "lakh": ("money", 10 ** 5), "lakhs": ("money", 10 ** 5),
    "crore": ("money", 10 ** 7), "crores": ("money", 10 ** 7),
    "million": ("money", 10 ** 6), "millions": ("money", 10 ** 6),
    "billion": ("money", 10 ** 9), "billions": ("money", 10 ** 9),
    "people": ("count", 1), "persons": ("count", 1), "occupants": ("count", 1),
}
LENGTH_WORDS = {"metres": "m", "kilometres": "km", "feet": "ft"}   # a field's unit, said
FIELD_LENGTH = {"m": "m", "metre": "m", "metres": "m", "meter": "m", "meters": "m",
                "km": "km", "kilometre": "km", "kilometres": "km", "ft": "ft", "feet": "ft"}
FIELD_MONEY = {"cost", "price", "worth", "insured", "premium", "valuation", "budget", "revenue",
               "turnover", "salary", "fee", "rent", "gbp", "usd", "eur", "inr", "rupees",
               "pounds", "dollars", "euros"}
FIELD_COUNT = {"capacity", "occupant", "occupants", "people", "persons", "population",
               "headcount"}
KINDS = {"length": "a length", "money": "an amount of money", "count": "a count"}
FIELD_AREA = {"sq", "square", "m2", "km2", "sqkm", "area", "hectares", "acres"}

# comparison words → (bound, inclusive); "between" and "exactly" are their own patterns
_COMPARE = {
    **dict.fromkeys(("over", "more than", "above", "greater than", "exceeding", "taller than",
                     "bigger than"), (">", False)),
    **dict.fromkeys(("under", "less than", "below", "fewer than", "shorter than",
                     "smaller than"), ("<", False)),
    **dict.fromkeys(("at least", "no less than", "a minimum of", "room for", "holds", "hold",
                     "capacity of"), (">", True)),
    **dict.fromkeys(("at most", "no more than", "up to", "a maximum of"), ("<", True)),
    **dict.fromkeys(("exactly", "of"), ("=", True)),
}
# what a comparison word or trailing adjective says the field is: a word of its name, or a kind
CUES = {"taller than": {"height"}, "shorter than": {"height", "length"}, "tall": {"height"},
        "high": {"height"}, "long": {"length"}, "wide": {"width"},
        "room for": "count", "holds": "count", "hold": "count", "capacity of": "count",
        "worth": "money"}

_NUM = r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?"
_UNIT = "|".join(sorted(map(re.escape, UNITS), key=len, reverse=True))
_AMOUNT = rf"({_NUM})(?:\s*({_UNIT}))?(?![a-z0-9])"
_WORDS = "|".join(sorted((re.escape(w).replace(r"\ ", r"\s+") for w in _COMPARE),
                         key=len, reverse=True))
_B = r"(?<![a-z0-9-])"
_TAIL = r"(?:\s+(tall|high|long|wide)(?![a-z0-9]))?"
_PATTERNS = [
    ("between", re.compile(rf"{_B}(?:(worth)\s+)?between\s+{_AMOUNT}\s+and\s+{_AMOUNT}{_TAIL}")),
    ("compare", re.compile(rf"{_B}(?:(worth)\s+)?({_WORDS})\s+{_AMOUNT}{_TAIL}")),
]
# comparisons a date reading may also claim ("of 1900", "between 1800 and 1850"): a date
# wins those unless a unit or a cue says it is a number
DATE_SHARED = {"of", "between"}


@dataclass
class NumberMatch:
    start: int
    end: int
    phrase: str
    lo: float | None
    hi: float | None
    lo_inclusive: bool
    hi_inclusive: bool
    unit: str                        # as said ("metres", "crore"), or ""
    cue: object = None               # a set of field-name words, or a kind ("count", "money")
    compare: str = ""                # the comparison word ("over", "between")


def _value(text: str) -> float:
    return float(text.replace(",", ""))


def _cue(*words: str | None):
    """The field the words say, if any: a kind wins over a name word."""
    found = [CUES[w] for w in words if w and w in CUES]
    return next((c for c in found if isinstance(c, str)), found[0] if found else None)


def find(raw: str, taken: list[tuple[int, int]]) -> list[NumberMatch]:
    """Every comparison of a number in `raw` (lowercase), skipping spans in `taken`."""
    out = []
    claimed = list(taken)
    for kind, rx in _PATTERNS:
        for m in rx.finditer(raw):
            if overlaps(m.start(), m.end(), claimed):
                continue
            if kind == "between":
                worth, a, unit_a, b, unit_b, tail = m.groups()
                if unit_a and unit_b and UNITS[unit_a][0] != UNITS[unit_b][0]:
                    continue
                unit = unit_b or unit_a or ""
                lo = _value(a) * (UNITS[unit_a][1] / UNITS[unit][1] if unit_a else 1)
                match = NumberMatch(m.start(), m.end(), m.group(), lo, _value(b), True, True,
                                    unit or "", _cue(worth, tail), "between")
            else:
                worth, word, n, unit, tail = m.groups()
                word = " ".join(word.split())
                bound, inclusive = _COMPARE[word]
                v = _value(n)
                lo = v if bound in (">", "=") else None
                hi = v if bound in ("<", "=") else None
                match = NumberMatch(m.start(), m.end(), m.group(), lo, hi,
                                    inclusive or lo is None, inclusive or hi is None,
                                    unit or "", _cue(worth, word, tail), word)
            claimed.append((m.start(), m.end()))
            out.append(match)
    return sorted(out, key=lambda x: x.start)


def not_dates(raw: str, taken: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """The spans of comparisons that are numbers, not dates: a number comparison word, a
    unit, or a cue ("capacity over 1500" is no year)."""
    return [(x.start, x.end) for x in find(raw, taken)
            if x.compare not in DATE_SHARED or x.unit or x.cue]


def kind(unit: str) -> str:
    """'length', 'money' or 'count' for a unit said or a field's unit; '' for none."""
    return UNITS[unit][0] if unit in UNITS else unit


def field_unit(text: str) -> str:
    """A number field's unit from its name, description, config or phrasings: 'm', 'km',
    'ft', 'money', 'count', or '' when nothing says, or two things disagree. Never guessed."""
    words = set(re.findall(r"[a-z0-9]+", text.lower()))
    if words & FIELD_AREA:
        return ""
    found = {FIELD_LENGTH[w] for w in words if w in FIELD_LENGTH}
    if words & FIELD_MONEY:
        found.add("money")
    if words & FIELD_COUNT:
        found.add("count")
    return found.pop() if len(found) == 1 else ""


def convert(v: float, said: str, unit: str) -> float:
    """`v` in the unit said ('' for none), as the field's unit holds it."""
    if not said:
        return v
    factor = UNITS[said][1]
    if kind(unit) == "length":
        factor /= UNITS[unit][1]
    return float(Decimal(repr(v)) * Decimal(repr(factor)))


def fmt(v: float) -> str:
    return format(Decimal(repr(float(v))).normalize(), "f")


def label(lo: float | None, hi: float | None, lo_inclusive: bool = True,
          hi_inclusive: bool = True, unit: str = "") -> str:
    """The canonical words for a bound, always saying whether it is strict: 'more than
    200', 'at least 200', 'between 10 and 30 metres (inclusive)', 'exactly 30'."""
    said = f" {next((w for w, u in LENGTH_WORDS.items() if u == unit), '')}".rstrip()
    if lo is not None and hi is not None:
        if lo == hi and lo_inclusive and hi_inclusive:
            return f"exactly {fmt(lo)}{said}"
        if lo_inclusive and hi_inclusive:
            return f"between {fmt(lo)} and {fmt(hi)}{said} (inclusive)"
    parts = []
    if lo is not None:
        parts.append(f"{'at least' if lo_inclusive else 'more than'} {fmt(lo)}{said}")
    if hi is not None:
        parts.append(f"{'at most' if hi_inclusive else 'less than'} {fmt(hi)}{said}")
    return " and ".join(parts) or "any number"
