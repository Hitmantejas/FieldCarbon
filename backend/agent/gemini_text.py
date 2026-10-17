"""Gemini for short texts: one prompt in, text or JSON out, with the tokens Vertex AI reported.

Shared by the Gemini-backed features (client statement, diagnosis, briefing). Modelled on
`extract_receipt.gemini_generate`: the SDK is imported only when a live call is made, temperature is 0, and JSON output
is constrained by a schema. Every function takes an injectable `generate(prompt, schema)` so tests use a stub and never
reach the network. Gemini writes words only; the numbers it may use come from code (CLAUDE.md principle 1).
"""
from __future__ import annotations

import json
from collections.abc import Callable

from backend.tools.extract_receipt import LOCATION, MODEL, PROJECT

# generate(prompt, schema or None) -> {"text": raw model text, "usage": {...}, "model_version": str}
Generate = Callable[[str, dict | None], dict]


def vertex_generate(prompt: str, schema: dict | None) -> dict:
    """One live call to Gemini on Vertex AI (ADC credentials, no keys)."""
    from google import genai
    from google.genai import types

    client = genai.Client(vertexai=True, project=PROJECT, location=LOCATION)
    config = types.GenerateContentConfig(temperature=0)
    if schema is not None:
        config = types.GenerateContentConfig(temperature=0, response_mime_type="application/json", response_json_schema=schema)
    response = client.models.generate_content(model=MODEL, contents=[prompt], config=config)
    u = response.usage_metadata
    return {"text": response.text or "",
            "usage": {"input_tokens": u.prompt_token_count or 0, "output_tokens": u.candidates_token_count or 0,
                      "thinking_tokens": u.thoughts_token_count or 0},
            "model_version": response.model_version}


def gemini_text(prompt: str, generate: Generate | None = None) -> dict:
    """Plain text: {text, usage, model_version}."""
    r = (generate or vertex_generate)(prompt, None)
    return {"text": (r.get("text") or "").strip(), "usage": r.get("usage") or {}, "model_version": r.get("model_version")}


def gemini_json(prompt: str, schema: dict, generate: Generate | None = None) -> dict:
    """JSON matching `schema`: {data, usage, model_version}. Text that is not a JSON object raises ValueError."""
    r = (generate or vertex_generate)(prompt, schema)
    try:
        data = json.loads(r.get("text") or "")
    except json.JSONDecodeError as e:
        raise ValueError("Gemini did not return JSON") from e
    if not isinstance(data, dict):
        raise ValueError("Gemini did not return a JSON object")
    return {"data": data, "usage": r.get("usage") or {}, "model_version": r.get("model_version")}
