"""Length units and dimension parsing (FR-CAT-005, FR-ROOM-003/004 conventions).

Pure functions with exact Decimal arithmetic so that, for example, 28 in is exactly
0.7112 m and 5 ft 6 in is exactly 1.6764 m. Display rounding never overwrites these.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

METRES_PER_UNIT: dict[str, Decimal] = {
    "m": Decimal("1"),
    "cm": Decimal("0.01"),
    "mm": Decimal("0.001"),
    "in": Decimal("0.0254"),
    "ft": Decimal("0.3048"),
}

UNIT_ALIASES: dict[str, str] = {
    "m": "m", "meter": "m", "meters": "m", "metre": "m", "metres": "m",
    "cm": "cm", "centimeter": "cm", "centimeters": "cm", "centimetre": "cm", "centimetres": "cm",
    "mm": "mm", "millimeter": "mm", "millimeters": "mm", "millimetre": "mm", "millimetres": "mm",
    "in": "in", "inch": "in", "inches": "in", '"': "in", "″": "in",
    "ft": "ft", "foot": "ft", "feet": "ft", "'": "ft", "′": "ft",
}

AXES = ("width", "depth", "height")


class UnitError(ValueError):
    """Raised when a value or unit cannot be interpreted without guessing."""


def _to_decimal(value: object) -> Decimal:
    try:
        d = Decimal(str(value).strip())
    except (InvalidOperation, ValueError) as exc:
        raise UnitError(f"'{value}' is not a number") from exc
    if not d.is_finite():
        raise UnitError(f"'{value}' is not a finite number")
    return d


def normalise_unit(unit: str | None) -> str:
    if unit is None or not str(unit).strip():
        raise UnitError("a unit is required; values are never assumed to be in a default unit")
    key = str(unit).strip().lower()
    if key in ("ft_in", "ft-in", "ftin"):
        return "ft_in"
    if key not in UNIT_ALIASES:
        raise UnitError(f"unknown unit '{unit}'")
    return UNIT_ALIASES[key]


def to_metres(value: object, unit: str, inches: object | None = None) -> Decimal:
    """Convert a positive length to metres.

    For unit 'ft_in', ``value`` is feet and ``inches`` is the inch part, so
    5 ft 6 in is to_metres(5, 'ft_in', 6). It is never read as decimal feet.
    """
    u = normalise_unit(unit)
    if u == "ft_in":
        feet = _to_decimal(value)
        inch = _to_decimal(inches if inches is not None else 0)
        if feet < 0 or inch < 0:
            raise UnitError("lengths must be positive")
        metres = feet * METRES_PER_UNIT["ft"] + inch * METRES_PER_UNIT["in"]
    else:
        d = _to_decimal(value)
        if d < 0:
            raise UnitError("lengths must be positive")
        metres = d * METRES_PER_UNIT[u]
    if metres <= 0:
        raise UnitError("lengths must be greater than zero")
    return metres


_FT_IN_RE = re.compile(
    r"""^\s*(?P<ft>\d+(?:\.\d+)?)\s*(?:ft|feet|foot|'|′)\s*(?:(?P<inch>\d+(?:\.\d+)?)\s*(?:in|inch|inches|"|″)?)?\s*$""",
    re.IGNORECASE,
)
_SIMPLE_RE = re.compile(r"^\s*(?P<num>\d+(?:\.\d+)?)\s*(?P<unit>[a-zA-Z\"'′″]+)?\s*$")


def parse_length(text: str, default_unit: str | None = None) -> Decimal:
    """Parse '6 ft 8 in', "6'8\"", '72 in', '180cm', '1.8 m'. A bare number needs ``default_unit``."""
    if text is None or not str(text).strip():
        raise UnitError("empty length")
    s = str(text).strip()
    m = _FT_IN_RE.match(s)
    if m:
        return to_metres(m.group("ft"), "ft_in", m.group("inch") or 0)
    m = _SIMPLE_RE.match(s)
    if not m:
        raise UnitError(f"cannot read length '{text}'")
    unit = m.group("unit") or default_unit
    if unit is None:
        raise UnitError(f"'{text}' has no unit")
    return to_metres(m.group("num"), unit)


@dataclass(frozen=True)
class EnteredLength:
    value: Decimal
    unit: str
    inches: Decimal | None = None

    def metres(self) -> Decimal:
        return to_metres(self.value, self.unit, self.inches)

    def as_json(self) -> dict:
        out: dict = {"value": str(self.value), "unit": self.unit}
        if self.inches is not None:
            out["inches"] = str(self.inches)
        return out


def entered_from_payload(payload: dict | None) -> EnteredLength | None:
    """Payload shape: {"value": 72, "unit": "in"} or {"value": 6, "unit": "ft_in", "inches": 8}."""
    if not payload:
        return None
    if payload.get("value") in (None, ""):
        return None
    unit = normalise_unit(payload.get("unit"))
    inches = payload.get("inches")
    return EnteredLength(_to_decimal(payload["value"]), unit, _to_decimal(inches) if inches not in (None, "") else None)


# --------------------------------------------------------------------------- listing text
_LABELS = {
    "w": "width", "width": "width", "l": "width", "length": "width",
    "d": "depth", "depth": "depth",
    "h": "height", "height": "height", "ht": "height",
}
_LABELLED_RE = re.compile(
    r"(?P<label>width|depth|height|length|ht|w|d|h|l)\s*[:=]?\s*(?P<num>\d+(?:\.\d+)?)\s*(?P<unit>cm|mm|m|in(?:ch(?:es)?)?|ft|feet|\"|')?",
    re.IGNORECASE,
)
_TRAILING_UNIT_RE = re.compile(r"(cm|mm|m|inches|inch|in|ft|feet)\s*\.?\s*$", re.IGNORECASE)


def parse_labelled_dimensions(text: str, default_unit: str | None = None) -> dict[str, Decimal] | None:
    """Read 'W 72 x D 36 x H 30 in' or 'Height: 75cm, Width: 120cm, Depth: 60cm'.

    Only values that carry an explicit axis label are returned. An unlabelled
    '72 x 36 x 30' returns None: the axis order must then be confirmed by the
    curator (FR-CAT-005 scenario 2: never assume the first value is width).
    Note 'L' (length) is read as width, the common furniture-listing convention.
    """
    if not text:
        return None
    trailing = _TRAILING_UNIT_RE.search(text)
    fallback_unit = trailing.group(1) if trailing else default_unit
    found: dict[str, Decimal] = {}
    for m in _LABELLED_RE.finditer(text):
        axis = _LABELS[m.group("label").lower()]
        unit = m.group("unit") or fallback_unit
        if unit is None:
            raise UnitError(f"no unit for {axis} in '{text}'")
        if axis in found:
            raise UnitError(f"{axis} appears twice in '{text}'")
        found[axis] = to_metres(m.group("num"), unit)
    return found or None


def parse_ordered_dimensions(text: str, axis_order: str, default_unit: str | None = None) -> dict[str, Decimal]:
    """Read unlabelled 'a x b x c <unit>' using a curator-confirmed axis order such as 'WxDxH' or 'H x W x D'."""
    order = [c for c in re.sub(r"[^WDHL]", "", axis_order.upper())]
    mapping = {"W": "width", "L": "width", "D": "depth", "H": "height"}
    if len(order) != 3 or len({mapping[c] for c in order}) != 3:
        raise UnitError(f"axis order '{axis_order}' must name width, depth and height once each")
    nums = re.findall(r"\d+(?:\.\d+)?", text)
    if len(nums) != 3:
        raise UnitError(f"expected three numbers in '{text}'")
    trailing = _TRAILING_UNIT_RE.search(text)
    unit = trailing.group(1) if trailing else default_unit
    if unit is None:
        raise UnitError(f"'{text}' has no unit")
    return {mapping[c]: to_metres(n, unit) for c, n in zip(order, nums)}


def round_display(metres: Decimal, places: int = 3) -> str:
    """Formatting helper only; never store its result."""
    q = Decimal(1).scaleb(-places)
    return str(metres.quantize(q))
