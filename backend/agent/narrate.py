"""Gemini writes the words, code checks the numbers: write, audit, one rewrite, then fixed wording.

`narrate_with_audit` is the one path for any Gemini text shown to a user outside the analyst chat (client statement,
diagnosis summary, briefing intro). The text passes only if every number traces to the facts (the auditor), every
figure has its label in the same sentence, nothing is over-precise, numbers are written 0-9 with a dot for decimals,
and the word "verified" is absent. One rewrite names the problems; if the text still fails, the caller's fixed wording
is shown and marked as such, so model text is never presented as checked when it was not.
"""
from __future__ import annotations

import json
import re
from collections.abc import Callable

from backend.agent.coverage import rewrite_request, unlabelled_sentences, unrounded_numbers
from backend.agent.faithfulness import audit
from backend.agent.gemini_text import Generate, gemini_json

# write(clean facts, rewrite message or None) -> {"text": str, "usage": {...}}
Write = Callable[[dict, str | None], dict]
# template(facts, language) -> (text, language it is written in)
Template = Callable[[dict, str], tuple[str, str]]

OPERATOR_ID = re.compile(r"\bOP-\d+\b")
DROPPED_KEYS = {"how", "source_ids", "source_id"}
NUMBER_TOKEN = re.compile(r"\d[\d,.]*")
WESTERN = re.compile(r"\d+(?:\.\d+)?|\d{1,3}(?:,\d{3})+(?:\.\d+)?")
FORBIDDEN_WORDS = re.compile(r"\bverif(?:y|ied|ies|ication)\b", re.IGNORECASE)
MODEL_ERROR = "The model could not be reached, so standard wording is shown."
TEXT_SCHEMA = {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}
USAGE_KEYS = ("input_tokens", "output_tokens", "thinking_tokens")


def clean_facts(node):
    """Only what Gemini may quote: numbers, units, labels and plain names. Drops calculation text, source ids, empty
    range ends and anything about operators; an operator id left inside a text is a bug and raises."""
    if isinstance(node, dict):
        return {k: clean_facts(v) for k, v in node.items()
                if k not in DROPPED_KEYS and "operator" not in k.lower() and v is not None}
    if isinstance(node, list):
        return [clean_facts(v) for v in node]
    if isinstance(node, str) and OPERATOR_ID.search(node):
        raise ValueError("an operator id must never be sent to Gemini")
    return node


def foreign_number_format(text: str) -> list[str]:
    """Numbers not written as 16,492 or 29.8: a decimal comma (29,8) or digits other than 0-9 (३,२००). The auditor reads
    only the Western format, so such numbers could slip past it or be misread."""
    out = []
    for m in NUMBER_TOKEN.finditer(text):
        token = m.group(0).rstrip(",.")
        if not token.isascii() or not WESTERN.fullmatch(token):
            out.append(token)
    return list(dict.fromkeys(out))


def _problems(text: str, facts: dict) -> tuple[str | None, int]:
    """The rewrite message for every problem in `text` (None if it passes), and how many numbers were checked."""
    verdict = audit(text, [facts])
    unlabelled, unrounded = unlabelled_sentences(text), unrounded_numbers(text)
    foreign, forbidden = foreign_number_format(text), FORBIDDEN_WORDS.findall(text)
    if verdict.faithful and not (unlabelled or unrounded or foreign or forbidden):
        return None, verdict.checked
    parts = []
    if foreign:
        parts.append(f"These numbers are not written the required way: {', '.join(foreign)}. Use the digits 0-9, a full stop "
                     "for decimals and a comma for thousands in every language (16,492 and 29.8).")
    if forbidden:
        parts.append('Do not use the word "verified"; say "traceable" if needed.')
    if not verdict.faithful or unlabelled or unrounded:
        parts.append(rewrite_request(verdict.unmatched, unlabelled=unlabelled, unrounded=unrounded).replace("the tools", "FACTS")
                     .replace("tool results", "FACTS"))
    return f"Your previous text was: {text}\n" + " ".join(parts), verdict.checked


def _add(total: dict, usage: dict | None) -> None:
    for k in USAGE_KEYS:
        total[k] += (usage or {}).get(k) or 0


def narrate_with_audit(facts: dict, write: Write, template: Template, language: str = "en") -> dict:
    """{text, narrative_source: gemini | template, narrative_language, audited, attempts, numbers_checked, usage, error}."""
    clean = clean_facts(facts)
    usage = dict.fromkeys(USAGE_KEYS, 0)
    rewrite, attempts, error, checked = None, 0, None, 0
    for _ in range(2):
        attempts += 1
        try:
            r = write(clean, rewrite)
        except Exception:  # noqa: BLE001 - any model failure shows the fixed wording; details stay out of the page
            error = MODEL_ERROR
            break
        _add(usage, r.get("usage"))
        text = (r.get("text") or "").strip()
        rewrite, checked = _problems(text, clean) if text else ("Your previous text was empty. Write the text.", 0)
        if rewrite is None:
            return {"text": text, "narrative_source": "gemini", "narrative_language": language, "audited": True,
                    "attempts": attempts, "numbers_checked": checked, "usage": usage, "error": None}
    text, written_in = template(facts, language)
    return {"text": text, "narrative_source": "template", "narrative_language": written_in, "audited": False,
            "attempts": attempts, "numbers_checked": 0, "usage": usage, "error": error}


def json_writer(build_prompt: Callable[[dict], str], generate: Generate | None = None) -> Write:
    """A `write` for narrate_with_audit: the feature's prompt with the facts, plus the rewrite message on the second try.
    Gemini returns {"text": "..."} under a JSON schema."""
    def write(facts: dict, rewrite: str | None) -> dict:
        prompt = build_prompt(facts)
        if rewrite:
            prompt += f"\n\nYour previous text had problems. {rewrite}\nRewrite the whole text and return the same JSON."
        r = gemini_json(prompt, TEXT_SCHEMA, generate)
        return {"text": str(r["data"].get("text") or ""), "usage": r["usage"]}
    return write


def facts_json(facts: dict) -> str:
    """Facts as compact JSON for a prompt."""
    return json.dumps(facts, ensure_ascii=False, separators=(",", ":"))
