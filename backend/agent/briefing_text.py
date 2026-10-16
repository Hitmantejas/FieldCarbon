"""The weekly briefing's short intro (F6): Gemini writes it in the manager's language, code checks every number.

The items are chosen by code (backend/tools/weekly_briefing.py). The model sees only a number-free topic per item and
its figure, rounded, under a key the auditor reads with the right unit (litres, hours, cost_gbp, litres_per_year).
It may mention the items by topic and quote their figures; it never chooses, orders or adds. If the text fails the
checks twice, or the model cannot be reached, the fixed wording below (no numbers at all) is shown instead.
"""
from __future__ import annotations

import re

from backend.agent.gemini_text import Generate
from backend.agent.narrate import Write, facts_json, json_writer, narrate_with_audit
from backend.agent.statement_text import LANGUAGE_NAMES, LANGUAGES, _r

__all__ = ["LANGUAGES", "gemini_facts", "build_prompt", "template", "writer", "narrate_briefing"]

MAX_WORDS = 60

# Appendix B.3, with the facts key named ITEMS.
PROMPT = """Write a 2 to 3 sentence introduction (at most 60 words) to a weekly briefing for a fleet manager.
Mention the three items by topic only, using the topics in ITEMS.
Use only numbers that appear in ITEMS, copied exactly, each followed by its unit and then its
label in English in brackets: (measured), (allocated) or (estimated). For example: 900 litres (measured), 352 to
1,645 litres (estimated).
No advice, no predictions. Do not mention people. Do not say "this week": the figures cover the company year to date.
Digits 0-9, dot decimals, comma thousands (1,645, not 1645).
Write in {language}.
ITEMS: {items}
Return JSON: {{"text": "..."}}"""

# A topic per kind with no numbers in it, so the model has nothing to misquote from a title.
TOPICS = {
    "duplicate_delivery_note": "a delivery note entered twice", "entered_twice": "a delivery note entered twice",
    "stock_gap": "a gap between a depot's books and its tank", "stock_surplus": "more fuel in a depot tank than the books show",
    "machine_over_dispense": "a machine given more fuel than it burned", "night_dispense": "fuel taken at night",
    "machine_under_dispense": "a machine that burned more fuel than it was given",
    "price_differs": "a delivery-note price that differs from the fuel log",
    "litres_differ": "delivery-note litres that differ from the fuel log",
    "note_not_in_log": "a delivery note missing from the fuel log", "log_row_without_note": "a fuel log entry with no note",
    "note_needs_review": "a delivery note that could not be read with confidence",
    "data_gap": "a tractor recorder that froze", "data_quality": "hours of frozen recorder data",
    "job_outlier": "a job with unusual fuel use per hour", "high_non_work_share": "a tractor with heavy fuel use between jobs",
    "benchmark": "machines burning more per hectare than their peers", "opportunity": "a fuel-saving idea backed by research",
}
FAMILY_TOPICS = {"control": "a fuel control finding", "data": "a data quality finding", "benchmark": "a peer comparison",
                 "opportunity": "a fuel-saving idea backed by research"}
# The fact key for each unit, so the auditor reads the number with that unit.
UNIT_KEYS = {"L": "litres", "h": "hours", "GBP": "cost_gbp", "L per year": "litres_per_year"}


def _topic(item: dict) -> str:
    return TOPICS.get(item["kind"]) or FAMILY_TOPICS.get(item["family"], "a finding")


def _figure(f: dict) -> dict:
    out = {"value": _r(f["value"])} if f["value"] is not None else {"low": _r(f["low"]), "high": _r(f["high"])}
    return {**out, "label": f["label"]}


def gemini_facts(briefing: dict) -> dict:
    """What the model may quote: a topic and one figure per item. No titles, how text, source ids or ids."""
    items = []
    for i in briefing["items"]:
        fact = {"topic": _topic(i), "family": i["family"], "severity": i["severity"]}
        key = UNIT_KEYS.get(i["figure"]["unit"])
        if key:
            fact[key] = _figure(i["figure"])
        items.append(fact)
    return {"period": briefing["period"], "items": items}


def build_prompt(facts: dict, language: str) -> str:
    return PROMPT.format(language=LANGUAGE_NAMES.get(language, language), items=facts_json(facts))


# Fixed wording with no numbers; the items' figures are on the cards underneath.
TEMPLATES = {
    "en": ("This summary covers the company year to date. It lists the {n} things to look at first, chosen by fixed "
           "rules: {topics}. The figures and their labels are on each card."),
    "de": ("Diese Übersicht gilt für das bisherige Geschäftsjahr. Sie zeigt die {n} Punkte, die zuerst geprüft werden "
           "sollten, nach festen Regeln gewählt: {topics}. Die Zahlen und ihre Kennzeichnung stehen auf jeder Karte."),
    "es": ("Este resumen abarca el año de la empresa hasta la fecha. Muestra los {n} puntos que conviene revisar primero, "
           "elegidos con reglas fijas: {topics}. Las cifras y sus etiquetas están en cada tarjeta."),
    "hi": ("यह सारांश कंपनी के अब तक के वर्ष का है। इसमें सबसे पहले देखने लायक {n} बातें हैं, जो तय नियमों से चुनी गईं: "
           "{topics}। आँकड़े और उनके लेबल हर कार्ड पर हैं।"),
}
COUNT_WORDS = {"en": ("one", "two", "three"), "de": ("eine", "zwei", "drei"), "es": ("uno", "dos", "tres"),
               "hi": ("एक", "दो", "तीन")}
FAMILY_NAMES = {
    "en": {"control": "fuel control", "data": "data quality", "benchmark": "peer comparison", "opportunity": "a fuel-saving idea"},
    "de": {"control": "Kraftstoffkontrolle", "data": "Datenqualität", "benchmark": "Vergleich mit anderen Maschinen",
           "opportunity": "eine Idee zum Kraftstoffsparen"},
    "es": {"control": "control de combustible", "data": "calidad de los datos", "benchmark": "comparación entre máquinas",
           "opportunity": "una idea para ahorrar combustible"},
    "hi": {"control": "ईंधन नियंत्रण", "data": "डेटा की गुणवत्ता", "benchmark": "मशीनों की तुलना", "opportunity": "ईंधन बचाने का एक विचार"},
}
OTHER = {"en": "other findings", "de": "weitere Befunde", "es": "otros hallazgos", "hi": "अन्य निष्कर्ष"}


def template(facts: dict, language: str) -> tuple[str, str]:
    """The fixed intro, in `language` when there is a phrase table for it, otherwise English. Items are named by
    family, in the language, so the text carries no numbers."""
    written_in = language if language in TEMPLATES else "en"
    names = FAMILY_NAMES[written_in]
    topics = list(dict.fromkeys(names.get(i["family"], OTHER[written_in]) for i in facts["items"]))
    n = len(facts["items"])
    count = COUNT_WORDS[written_in][n - 1] if 1 <= n <= 3 else ""
    return TEMPLATES[written_in].format(n=count, topics=", ".join(topics)), written_in


def _short_enough(text: str) -> str | None:
    words = len(re.findall(r"\S+", text))
    return None if words <= MAX_WORDS else f"The text has {words} words; use at most {MAX_WORDS}."


def writer(language: str, generate: Generate | None = None) -> Write:
    """Gemini as the writer for one language (a live call; tests pass their own writer)."""
    return json_writer(lambda facts: build_prompt(facts, language), generate)


def narrate_briefing(briefing: dict, language: str, write: Write | None = None) -> dict:
    """{text, narrative_source, narrative_language, audited, attempts, numbers_checked, usage, error}."""
    return narrate_with_audit(gemini_facts(briefing), write or writer(language), template, language, extra_check=_short_enough)
