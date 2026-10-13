"""Auditor: every number in an agent answer must come from a tool output (CLAUDE.md principle 6).

Strict by design: Gemini never does the maths, so a number the tools did not produce fails, even a
correct sum. A number may be rounded as displayed ("10,814 L" for 10,813.69; "36.6 t" for 36,572 kg;
"£8.1k" for 8,099) and may be any number the user wrote in the question. Years, dates, ids such as
S1-T4 or A3-27, and list numbering are not figures and are ignored.

Pure Python: the agent calls `guard()` before replying; the eval harness calls `audit()` on recorded runs.
"""
from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field

# Unit word -> (family, factor to the family's base unit). Longest alternatives first in the regex.
UNITS: dict[str, tuple[str, float]] = {
    "l/ha": ("l_per_ha", 1), "litres per hectare": ("l_per_ha", 1), "litres a hectare": ("l_per_ha", 1),
    "l/h": ("l_per_h", 1), "litres per hour": ("l_per_h", 1), "litres an hour": ("l_per_h", 1),
    "litres": ("litres", 1), "litre": ("litres", 1), "liters": ("litres", 1), "liter": ("litres", 1), "l": ("litres", 1),
    "tonnes": ("kg", 1000), "tonne": ("kg", 1000), "tons": ("kg", 1000), "ton": ("kg", 1000), "t": ("kg", 1000),
    "kg": ("kg", 1), "kilograms": ("kg", 1),
    "%": ("pct", 1), "percent": ("pct", 1), "per cent": ("pct", 1),
    "hectares": ("ha", 1), "hectare": ("ha", 1), "ha": ("ha", 1),
    "hours": ("hours", 1), "hour": ("hours", 1), "hrs": ("hours", 1), "h": ("hours", 1),
    "kw": ("kw", 1), "years": ("years", 1), "year": ("years", 1),
    "gbp": ("gbp", 1), "pounds": ("gbp", 1),
}
SCALE = {"k": 1e3, "m": 1e6, "bn": 1e9}
MONTHS = ("january|february|march|april|may|june|july|august|september|october|november|december|"
          "jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec")

_unit_alt = "|".join(re.escape(u) for u in sorted(UNITS, key=len, reverse=True))
NUMBER = re.compile(
    r"(?P<cur>£|GBP\s?)?"
    r"(?P<num>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
    r"(?:(?P<scale>k|m|bn)(?![a-z]))?"  # 8.1k, £2m; not the k of kg or kW
    r"(?:\s?(?P<unit>" + _unit_alt + r")(?![a-z]))?",
    re.IGNORECASE,
)
DATE = re.compile(r"\b\d{4}-\d{2}(?:-\d{2})?\b|\b\d{1,2}/\d{1,2}/\d{2,4}\b")
LIST_MARKER = re.compile(r"(?m)^\s*\d+[.)]\s")
DAY_BEFORE_MONTH = re.compile(rf"\b\d{{1,2}}(?:st|nd|rd|th)?\s+(?:{MONTHS})\b", re.IGNORECASE)

# Tool-output keys whose bare numbers have a known unit family.
KEY_FAMILIES = [("l_per_ha", "l_per_ha"), ("l_per_h", "l_per_h"), ("litres", "litres"), ("kg", "kg"),
                ("gbp", "gbp"), ("cost", "gbp"), ("pct", "pct"), ("share", "pct"), ("hectares", "ha"),
                ("area", "ha"), ("_ha", "ha"), ("hours", "hours"), ("kw", "kw"), ("years", "years")]
FIGURE_UNITS = {"L": "litres", "kg CO2e": "kg", "GBP": "gbp", "% of your emissions": "pct", "ha": "ha"}


@dataclass(frozen=True)
class Found:
    text: str
    value: float          # in the family's base unit
    family: str | None    # None = no unit stated (a count, or a bare number)
    tolerance: float      # half a unit of the last digit shown, in base units


@dataclass(frozen=True)
class NumberCheck:
    text: str
    value: float
    family: str | None
    matched: bool
    source: str | None    # where in the tool outputs it was found (json path), or "question"


@dataclass(frozen=True)
class Audit:
    faithful: bool
    checked: int
    numbers: tuple[NumberCheck, ...] = field(default=())

    @property
    def unmatched(self) -> list[NumberCheck]:
        return [n for n in self.numbers if not n.matched]


def _tolerance(num: str, scale: float) -> float:
    digits = num.replace(",", "")
    if "." in digits:
        step = 10 ** -len(digits.split(".")[1])
    else:  # trailing zeros of a whole number are a rounding: 11,000 means "to the nearest thousand"
        stripped = digits.rstrip("0")
        step = 10 ** (len(digits) - len(stripped)) if stripped else 1
    return 0.5 * step * scale


def _ignored_spans(text: str) -> list[tuple[int, int]]:
    spans = [m.span() for m in DATE.finditer(text)]
    spans += [m.span() for m in LIST_MARKER.finditer(text)]
    spans += [(m.start(), m.start() + len(m.group(0).split()[0])) for m in DAY_BEFORE_MONTH.finditer(text)]
    return spans


def find_numbers(text: str) -> list[Found]:
    """Numbers stated as figures in `text`, with unit family and display tolerance."""
    out, skip = [], _ignored_spans(text)
    for m in NUMBER.finditer(text):
        start, end = m.span("num")
        if any(a <= start < b for a, b in skip):
            continue
        before = text[max(0, start - 2):start]
        if re.search(r"[A-Za-z]$", before) or re.search(r"[A-Za-z0-9]-$", before):
            continue  # part of an id or a name: S1, CO2, A3-27, OP-01
        after = text[m.end():m.end() + 1]
        if not m.group("unit") and not m.group("scale") and re.match(r"[A-Za-z]", after or " "):
            continue  # 2nd, 4x4 and other words that start with digits
        num, scale_word = m.group("num"), (m.group("scale") or "").lower()
        if len(num) > 1 and num[0] == "0" and num[1] != ".":
            continue  # a number in a name: Client farm 09, Field 007
        scale = SCALE.get(scale_word, 1.0)
        raw = float(num.replace(",", "")) * scale
        family, factor = UNITS.get((m.group("unit") or "").lower(), (None, 1.0))
        if m.group("cur"):
            family, factor = "gbp", 1.0
        if family is None and "." not in num and "," not in num and not scale_word and 1900 <= raw <= 2100:
            continue  # a year
        out.append({"span": m.span(), "text": m.group(0).strip(), "raw": raw, "tol": _tolerance(num, scale),
                    "family": family, "factor": factor})
    # A range shares its unit: in "1,214 to 2,054 litres" the first number is litres too.
    for a, b in zip(out, out[1:]):
        between = text[a["span"][1]:b["span"][0]].strip().lower()
        if a["family"] is None and b["family"] and between in ("to", "-", "–", "and"):
            a["family"], a["factor"] = b["family"], b["factor"]
    return [Found(n["text"], n["raw"] * n["factor"], n["family"], n["tol"] * n["factor"]) for n in out]


def _key_family(key: str) -> str | None:
    k = key.lower()
    return next((fam for part, fam in KEY_FAMILIES if part in k), None)


def tool_values(outputs: Iterable, path: str = "") -> list[tuple[float, str | None, str]]:
    """Every number a tool produced: raw fields (unit from the Figure or the key) and numbers written in its text."""
    found: list[tuple[float, str | None, str]] = []

    def walk(node, path: str, family: str | None) -> None:
        if isinstance(node, bool) or node is None:
            return
        if isinstance(node, (int, float)):
            found.append((float(node), family, path))
        elif isinstance(node, str):
            found.extend((f.value, f.family, f"{path}:text") for f in find_numbers(node))
        elif isinstance(node, dict):
            fig_family = FIGURE_UNITS.get(node.get("unit")) if {"label", "how"} <= node.keys() else None
            for k, v in node.items():
                child = fig_family if k in ("value", "low", "high") and fig_family else _key_family(str(k)) or family
                walk(v, f"{path}.{k}" if path else str(k), child)
        elif isinstance(node, (list, tuple)):
            for i, v in enumerate(node):
                walk(v, f"{path}[{i}]", family)

    for i, out in enumerate(outputs):
        walk(out, f"{path}tool[{i}]", None)
    return found


def _compatible(answer: str | None, tool: str | None) -> bool:
    return answer is None or tool is None or answer == tool


def audit(answer: str, tool_outputs: Iterable, question: str = "") -> Audit:
    values = tool_values(list(tool_outputs))
    asked = find_numbers(question)
    checks = []
    for f in find_numbers(answer):
        hit = next((p for v, fam, p in values if _compatible(f.family, fam) and abs(v - f.value) <= f.tolerance + 1e-9),
                   None)
        if hit is None and any(abs(q.value - f.value) <= max(q.tolerance, f.tolerance) for q in asked):
            hit = "question"
        checks.append(NumberCheck(f.text, f.value, f.family, hit is not None, hit))
    return Audit(all(c.matched for c in checks), len(checks), tuple(checks))


def guard(answer: str, tool_outputs: Iterable, question: str = "") -> tuple[bool, str | None]:
    """For the agent, before it replies: (faithful, note). On failure, regenerate, or append the note so the
    user sees which numbers could not be traced to a tool result."""
    a = audit(answer, tool_outputs, question)
    if a.faithful:
        return True, None
    listed = ", ".join(dict.fromkeys(n.text for n in a.unmatched))
    return False, (f"Check needed: these numbers could not be traced to FieldCarbon's calculations: {listed}. "
                   "Please treat them with care.")
