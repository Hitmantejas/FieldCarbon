"""The client statement's short summary (F4): Gemini writes it in the client's language, code checks every number.

`gemini_facts` is the only thing the model sees: rounded numbers with their labels, under key names the auditor reads
with the right unit (co2e_kg_per_ha, not co2e_per_ha, which it would read as hectares). Nothing is divided or added in
the prompt. If the text fails the checks twice, or the model cannot be reached, the fixed wording below is shown in the
same language and marked as standard wording (backend/agent/narrate.py).
"""
from __future__ import annotations

from backend.agent.gemini_text import Generate
from backend.agent.narrate import Write, facts_json, json_writer, narrate_with_audit

LANGUAGES = ("en", "de", "es", "hi")
LANGUAGE_NAMES = {"en": "English", "de": "German", "es": "Spanish", "hi": "Hindi"}

PROMPT = """You write a short statement for a farmer about the machinery emissions from work done on their farm.
FACTS is the only source of numbers.
Rules:
1. Use only numbers that appear in FACTS. Copy each number exactly as written there.
   Never calculate, round differently, add, subtract or compare.
2. Write digits 0-9 only. Use a full stop for decimals and a comma for thousands in every
   language (for example 16,492 and 29.8).
3. After each figure, write its label in English in brackets, exactly as given:
   (measured), (allocated) or (estimated).
4. Do not give advice, forecasts or comparisons that are not in FACTS. Do not mention people.
5. Plain, short sentences for a reader who may not read easily. At most 120 words.
6. Write in {language}.
FACTS: {facts}
Return JSON: {{"text": "..."}}"""


def _r(value: float) -> int | float:
    """Rounded as a person would write it: whole numbers from 100 up, one decimal below."""
    return int(round(value)) if abs(value) >= 100 else round(value, 1)


def _fig(f: dict | None) -> dict | None:
    return None if f is None else {"value": _r(f["value"]), "unit": f["unit"], "label": f["label"]}


def gemini_facts(s: dict) -> dict:
    """What the model may quote. No how text, no source ids, nothing about operators."""
    t = s["totals"]
    facts = {
        "client_name": s["client_name"], "period": s["period"],
        "litres": _fig(t["litres"]), "co2e_kg": _fig(t["co2e_kg"]), "cost_gbp": _fig(t["cost_gbp"]),
        "area_ha": _fig(s["area_ha"]), "co2e_kg_per_ha": _fig(s["co2e_per_ha"]), "co2e_kg_per_job": _fig(s["co2e_per_job"]),
        "jobs": s["jobs"],
        "by_operation": [{"operation": o["operation"], "litres": _fig(o["litres"]), "share_pct": _r(o["share_pct"])}
                         for o in s["by_operation"]],
    }
    return {k: v for k, v in facts.items() if v is not None}


def build_prompt(facts: dict, language: str) -> str:
    return PROMPT.format(language=LANGUAGE_NAMES.get(language, language), facts=facts_json(facts))


# Fixed wording, one sentence per key; {x} is a number written 0-9 with comma thousands, {x_l} its label.
TEMPLATES = {
    "en": {
        "head": "{name}: machinery emissions from work on your fields, {start} to {end}.",
        "litres": "Our machines used {litres} litres of diesel on your fields ({litres_l}).",
        "co2e_area": "That is {co2e} kg CO2e ({co2e_l}), or {per_ha} kg CO2e per hectare ({per_ha_l}) over {area} hectares ({area_l}).",
        "co2e": "That is {co2e} kg CO2e ({co2e_l}).",
        "jobs": "Over {jobs} jobs, that is {per_job} kg CO2e per job ({per_job_l}).",
        "cost": "The fuel cost £{cost} ({cost_l}).",
        "top": "The largest part was {op}, with {share}% of the litres ({op_l}).",
    },
    "de": {
        "head": "{name}: Emissionen der Maschinenarbeit auf Ihren Flächen, {start} bis {end}.",
        "litres": "Unsere Maschinen haben auf Ihren Flächen {litres} Liter Diesel verbraucht ({litres_l}).",
        "co2e_area": "Das sind {co2e} kg CO2e ({co2e_l}), also {per_ha} kg CO2e pro Hektar ({per_ha_l}) auf {area} Hektar ({area_l}).",
        "co2e": "Das sind {co2e} kg CO2e ({co2e_l}).",
        "jobs": "Bei {jobs} Einsätzen sind das {per_job} kg CO2e pro Einsatz ({per_job_l}).",
        "cost": "Der Kraftstoff kostete £{cost} ({cost_l}).",
        "top": "Den größten Anteil hatte {op}, mit {share}% der Liter ({op_l}).",
    },
    "es": {
        "head": "{name}: emisiones del trabajo con maquinaria en sus campos, de {start} a {end}.",
        "litres": "Nuestras máquinas usaron {litres} litros de gasóleo en sus campos ({litres_l}).",
        "co2e_area": "Eso equivale a {co2e} kg de CO2e ({co2e_l}), es decir {per_ha} kg de CO2e por hectárea ({per_ha_l}) en {area} "
                     "hectáreas ({area_l}).",
        "co2e": "Eso equivale a {co2e} kg de CO2e ({co2e_l}).",
        "jobs": "En {jobs} trabajos, son {per_job} kg de CO2e por trabajo ({per_job_l}).",
        "cost": "El combustible costó £{cost} ({cost_l}).",
        "top": "La mayor parte fue {op}, con el {share}% de los litros ({op_l}).",
    },
    "hi": {
        "head": "{name}: आपके खेतों पर मशीनों के काम से उत्सर्जन, {start} से {end} तक।",
        "litres": "हमारी मशीनों ने आपके खेतों पर {litres} लीटर डीज़ल इस्तेमाल किया ({litres_l})।",
        "co2e_area": "यह {co2e} kg CO2e है ({co2e_l}), यानी {area} हेक्टेयर ({area_l}) पर {per_ha} kg CO2e प्रति हेक्टेयर ({per_ha_l})।",
        "co2e": "यह {co2e} kg CO2e है ({co2e_l})।",
        "jobs": "{jobs} कामों में यह {per_job} kg CO2e प्रति काम है ({per_job_l})।",
        "cost": "ईंधन की लागत £{cost} रही ({cost_l})।",
        "top": "सबसे बड़ा हिस्सा {op} का था, लीटर का {share}% ({op_l})।",
    },
}


def _n(value) -> str:
    return f"{value:,}" if isinstance(value, int) else f"{value:,.1f}"


def template(facts: dict, language: str) -> tuple[str, str]:
    """The fixed wording, in `language` when there is a phrase table for it, otherwise English."""
    written_in = language if language in TEMPLATES else "en"
    t = TEMPLATES[written_in]
    v = {"name": facts["client_name"], "start": facts["period"]["from"], "end": facts["period"]["to"], "jobs": facts["jobs"]}
    for key, name in (("litres", "litres"), ("co2e_kg", "co2e"), ("cost_gbp", "cost"), ("area_ha", "area"),
                      ("co2e_kg_per_ha", "per_ha"), ("co2e_kg_per_job", "per_job")):
        if key in facts:
            v[name], v[f"{name}_l"] = _n(facts[key]["value"]), facts[key]["label"]
    parts = [t["head"], t["litres"], t["co2e_area"] if "per_ha" in v else t["co2e"]]
    if "per_job" in v:
        parts.append(t["jobs"])
    parts.append(t["cost"])
    if facts["by_operation"]:
        top = facts["by_operation"][0]
        v.update(op=top["operation"], share=_n(top["share_pct"]), op_l=top["litres"]["label"])
        parts.append(t["top"])
    return " ".join(p.format(**v) for p in parts), written_in


def writer(language: str, generate: Generate | None = None) -> Write:
    """Gemini as the writer for one language (a live call; tests pass their own writer)."""
    return json_writer(lambda facts: build_prompt(facts, language), generate)


def narrate_statement(statement: dict, language: str, write: Write | None = None) -> dict:
    """{text, narrative_source, narrative_language, audited, attempts, numbers_checked, usage, error}."""
    return narrate_with_audit(gemini_facts(statement), write or writer(language), template, language)
