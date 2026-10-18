"""Anomaly diagnosis, the Gemini part (F5): one line of 'why' per tested cause, up to two untested ideas, and a summary.

Code has already tested every cause and fixed the order (backend/tools/diagnose_anomaly.py). Gemini sees the finding's
rounded figure and the test results, never calculation text, source ids or anything about people. It cannot set a
status or reorder: its 'why' lines are matched to the menu by id (an id not on the menu is rejected), and each line is
checked like the summary (numbers traced to the facts, labels, no "proven"/"confirmed"); a failing line is dropped.
Extra ideas are capped at two and always shown as untested. The summary goes through narrate_with_audit and falls
back to fixed wording with no numbers.
"""
from __future__ import annotations

import re

from backend.agent.gemini_text import Generate, gemini_json
from backend.agent.narrate import _problems, clean_facts, facts_json, narrate_with_audit
from backend.agent.statement_text import _r
from backend.tools.diagnose_anomaly import STATUS_TEXT, order

FORBIDDEN = re.compile(r"\b(prove|proven|proves|confirmed|confirms|root cause)\b", re.IGNORECASE)
BRACKET = re.compile(r"\[([^\]]*)\]")
BRACKET_LABELS = {"measured", "allocated", "estimated"}
MAX_WORDS = 25
MAX_EXTRAS = 2
GEMINI_TAG = "Suggested by Gemini"

PROMPT = """You help a fleet manager understand a fuel finding. FINDING and TESTS are produced by code.
You do not decide results. In TESTS, "measures" says what each evidence figure counts and
reads on from its number and unit (e.g. "N L [measured] dispensed to this machine at night"), and "explains_pct" is the
share of the finding's figure that the evidence accounts for (worked out by code).
1. For each hypothesis id in MENU, write one short reason (up to 25 words) why it is or is not
   a plausible explanation. Say what the evidence shows, using its "measures" text; do not just repeat the result.
   A figure you quote needs its label in brackets, as in the summary. Do not use the words "verify" or "verified".
   Use only facts in TESTS. Do not change any status. Do not mention people.
2. You may add up to 2 extra ideas that are not in MENU. Each needs a title and a reason.
   They will be shown as untested.
3. Write a summary of 2 or 3 sentences using only numbers in TESTS. Describe each figure exactly as its "measures"
   text does, and write its label (measured, allocated or estimated) in brackets after it; these are the only
   labels. Write an explains_pct value as a percentage in the same sentence as its evidence figure.
   Do not say "proven", "confirmed" or "root cause". Digits 0-9, dot decimals, comma thousands.
   Never calculate, add or compare numbers.
FINDING: {finding}
MENU: {menu}
TESTS: {tests}
Return JSON matching the schema."""


def schema(menu: list[str]) -> dict:
    """The answer's shape; the menu ids are an enum, so a live model cannot invent one."""
    why = {"type": "object", "properties": {"id": {"type": "string", "enum": menu}, "text": {"type": "string"}},
           "required": ["id", "text"]}
    idea = {"type": "object", "properties": {"title": {"type": "string"}, "reason": {"type": "string"}},
            "required": ["title", "reason"]}
    return {"type": "object", "properties": {"why": {"type": "array", "items": why},
                                             "extra_ideas": {"type": "array", "items": idea, "maxItems": MAX_EXTRAS},
                                             "summary": {"type": "string"}},
            "required": ["why", "extra_ideas", "summary"]}


# A count of one is given in the singular, so Gemini copies "1 month", not "1 months" (as the app shows it).
SINGULAR = {"notes": "note", "months": "month", "days": "day"}


def _fig(f: dict | None) -> dict | None:
    if f is None:
        return None
    unit = SINGULAR.get(f["unit"], f["unit"]) if f["value"] == 1 else f["unit"]
    return {"value": _r(f["value"]), "unit": unit, "label": f["label"]}


def gemini_facts(d: dict) -> dict:
    """What the model may quote: rounded figures with labels and the code's results, in the code's order."""
    return {"finding": {"title": d["title"], "kind": d["kind"], "figure": _fig(d["finding_figure"])},
            "tests": [{"id": h["id"], "title": h["title"], "result": h["status_text"], "evidence": _fig(h["evidence"]),
                       "measures": h.get("evidence_measures"),
                       "explains_pct": None if h["explains_pct"] is None else _r(h["explains_pct"])}
                      for h in d["hypotheses"]]}


def build_prompt(facts: dict) -> str:
    return PROMPT.format(finding=facts_json(facts["finding"]), menu=", ".join(t["id"] for t in facts["tests"]),
                         tests=facts_json(facts["tests"]))


def forbidden_words(text: str) -> str | None:
    """No claim of proof, and nothing in brackets except a label (a live run wrote "100 [explains_pct]")."""
    problems = []
    found = sorted({w.lower() for w in FORBIDDEN.findall(text)})
    if found:
        problems.append(f'Do not use these words: {", ".join(found)}. Say "supported by the data" instead.')
    odd = sorted({b for b in BRACKET.findall(text) if b.strip().lower() not in BRACKET_LABELS})
    if odd:
        problems.append(f'Only measured, allocated or estimated may go in brackets, not: {", ".join(odd)}.')
    return " ".join(problems) or None


def _line_ok(text: str, clean: dict) -> bool:
    """A 'why' line or extra idea passes the same checks as the summary, and is short."""
    return bool(text) and len(text.split()) <= MAX_WORDS and _problems(text, clean, forbidden_words)[0] is None


def template(facts: dict, language: str) -> tuple[str, str]:
    """Fixed wording with no numbers: which causes the data supports and which it does not."""
    def titles(result: str) -> str:
        return "; ".join(t["title"] for t in facts["tests"] if t["result"] == STATUS_TEXT[result])
    parts = [f"The data supports: {titles('supported')}." if titles("supported") else "The data supports none of the causes we can test.",
             f"The data does not support: {titles('not_supported')}." if titles("not_supported") else "",
             "Other causes cannot be tested with our data."]
    return " ".join(p for p in parts if p), "en"


def explain(d: dict, generate: Generate | None = None) -> dict:
    """The diagnosis with a `why` on each tested cause, up to two untested ideas, a checked summary and `rejected` ids.
    Statuses and order are the code's; if the model fails, the tests stay with no why lines."""
    facts = gemini_facts(d)
    clean = clean_facts(facts)
    menu = [h["id"] for h in d["hypotheses"]]
    first: dict = {}

    def write(clean_in: dict, rewrite: str | None) -> dict:
        prompt = build_prompt(clean_in)
        if rewrite:
            prompt += f"\n\nYour previous summary had problems. {rewrite}\nRewrite the summary and return the same JSON."
        r = gemini_json(prompt, schema(menu), generate)
        first.setdefault("data", r["data"])
        return {"text": str(r["data"].get("summary") or ""), "usage": r["usage"]}

    summary = narrate_with_audit(facts, write, template, "en", extra_check=forbidden_words)
    data = first.get("data") or {}

    why, rejected = {}, []
    for item in data.get("why") or []:
        hid, text = str(item.get("id") or ""), str(item.get("text") or "").strip()
        if hid not in menu:
            rejected.append(hid)
        elif hid not in why and _line_ok(text, clean):
            why[hid] = text
    rows = [{**h, "why": why.get(h["id"]), "tag": None} for h in d["hypotheses"]]

    extras = []
    for idea in data.get("extra_ideas") or []:
        title, reason = str(idea.get("title") or "").strip(), str(idea.get("reason") or "").strip()
        if len(extras) < MAX_EXTRAS and _line_ok(title, clean) and _line_ok(reason, clean):
            extras.append({"id": f"gemini_idea_{len(extras) + 1}", "title": title, "description": reason,
                           "status": "cannot_test", "status_text": STATUS_TEXT["cannot_test"], "evidence": None, "evidence_measures": None,
                           "explains_pct": None, "would_settle": None, "suggested_by": "gemini", "why": None, "tag": GEMINI_TAG})
    return {**d, "hypotheses": order(rows + extras), "summary": summary, "rejected": rejected}
