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


def uncited_ideas(answer: str, outputs: list) -> list[dict]:
    """Ideas the answer names without any of their sources: {name, titles} once per idea name."""
    text, out = answer.lower(), {}
    for i in _ideas(outputs):
        if i["name"].lower() in text and not _cites(i, text):
            out.setdefault(i["name"], list(dict.fromkeys(e["title"] for e in i["evidence"])))
    return [{"name": n, "titles": t} for n, t in out.items()]
