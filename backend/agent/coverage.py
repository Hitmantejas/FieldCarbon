"""Labels and citations in an answer: the same rules the eval harness scores (evals/run_all.py) and the agent checks.

A sentence with a figure must say its confidence label (CLAUDE.md principle 2), and an idea from fleet_opportunities
that the answer names must also name one of its research sources (principle 4). Deterministic: no model involved.
"""
from __future__ import annotations

import re

from backend.agent.faithfulness import find_numbers

LABEL_WORDS = re.compile(r"\b(measured|allocated|estimated)\b", re.IGNORECASE)
FIGURE_FAMILIES = {"litres", "kg", "gbp", "pct", "l_per_ha", "l_per_h", "ha", "hours"}


def sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


def _figure_count(sentence: str) -> int:
    return sum(1 for f in find_numbers(sentence) if f.family in FIGURE_FAMILIES)


def label_coverage(answer: str) -> tuple[int, int]:
    """Figures in the answer that carry a confidence label in the same sentence, and all figures."""
    total = labelled = 0
    for s in sentences(answer):
        n = _figure_count(s)
        total += n
        labelled += n if LABEL_WORDS.search(s) else 0
    return labelled, total


def unlabelled_sentences(answer: str) -> list[str]:
    return [s.strip() for s in sentences(answer) if _figure_count(s) and not LABEL_WORDS.search(s)]


# 100 or more with decimals ("16492.14 Liter"), or any number with four or more decimals ("3.38206").
UNROUNDED = re.compile(r"\d{3}[.,]\d{1,2}(?!\d)|\d[.,]\d{4,}")


def unrounded_numbers(answer: str) -> list[str]:
    """Figures written with more decimals than a person would use. A price per litre (£0.80) is fine."""
    return list(dict.fromkeys(f.text for f in find_numbers(answer) if f.family in FIGURE_FAMILIES and UNROUNDED.search(f.text)))


def _ideas(outputs: list) -> list[dict]:
    """Every idea with its evidence in the tool outputs; one per call, so an idea shown for two sites counts twice."""
    items = []

    def walk(node):
        if isinstance(node, dict):
            if node.get("evidence") and node.get("name"):
                items.append(node)
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
    for out in outputs:
        walk(out)
    return items


def _cites(idea: dict, text: str) -> bool:
    return any(e["source_id"].lower() in text or e["title"].lower()[:30] in text for e in idea["evidence"])


def citation_coverage(answer: str, outputs: list) -> tuple[int, int]:
    """Ideas named in the answer that also name one of their sources, and all ideas named."""
    text = answer.lower()
    named = [i for i in _ideas(outputs) if i["name"].lower() in text]
    return sum(_cites(i, text) for i in named), len(named)


def rewrite_request(unmatched, uncited=(), unlabelled=(), unrounded=()) -> str:
    """The one retry message. A number whose size is in the tools but whose saving/increase is turned round is named
    as such, so the model fixes the words instead of hunting for a number it already has. Ideas named without their
    source, sentences with a figure but no confidence label, and figures with needless decimals are named too.
    Used by the analyst agent and by narrate_with_audit (backend/agent/narrate.py)."""
    invented = ", ".join(dict.fromkeys(n.text for n in unmatched if not n.wrong_direction))
    flipped = ", ".join(dict.fromkeys(n.text for n in unmatched if n.wrong_direction))
    parts = []
    if invented:
        parts.append(f"These numbers in your answer did not come from the tools: {invented}. Rewrite them using only numbers "
                     "the tool results contain, written as they appear. If a number is not available, say so instead of working it out.")
    if flipped:
        parts.append(f"These numbers are in the tool results, but your answer gives them the opposite direction (a saving where "
                     f"the tools show an increase, or the other way round): {flipped}. Keep the numbers and describe the direction "
                     "the tools give.")
    if uncited:
        named = "; ".join(f'{g["name"]} (source: {" / ".join(g["titles"][:2])})' for g in uncited)
        parts.append(f"These ideas are named without their research source: {named}. Name the source title next to each idea, "
                     "every time it appears, including for a second site.")
    if unlabelled:
        quoted = " | ".join(s[:120] for s in unlabelled[:4])
        parts.append(f"These sentences give a figure without its confidence label: {quoted}. Add measured, allocated or "
                     "estimated in the same sentence, as the tool results give it.")
    if unrounded:
        parts.append(f"These figures have more decimals than a person would write: {', '.join(unrounded)}. Round them as a person "
                     "would (whole litres, whole pounds, tonnes with one decimal), with a comma for thousands in every language (16,492).")
    return " ".join(parts) + " Rewrite the whole answer."


def uncited_ideas(answer: str, outputs: list) -> list[dict]:
    """Ideas the answer names without any of their sources: {name, titles} once per idea name."""
    text, out = answer.lower(), {}
    for i in _ideas(outputs):
        if i["name"].lower() in text and not _cites(i, text):
            out.setdefault(i["name"], list(dict.fromkeys(e["title"] for e in i["evidence"])))
    return [{"name": n, "titles": t} for n, t in out.items()]
