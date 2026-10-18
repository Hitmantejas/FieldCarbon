"""Text in both themes keeps WCAG AA contrast (4.5:1), read from the colour tokens in frontend/src/index.css."""
import math
import re
from pathlib import Path

import pytest

CSS = (Path(__file__).resolve().parents[1] / "frontend" / "src" / "index.css").read_text(encoding="utf-8")
OKLCH = re.compile(r"--([a-z-]+):\s*oklch\(([\d.]+)%\s+([\d.]+)\s+([\d.]+)\)")
# Text and the surface it sits on. Dividers and the lime fill are not text; the range bar and flagged rows also carry text.
TEXT_ON = [("ink", "paper"), ("ink-soft", "paper"), ("ink", "desk"), ("ink-soft", "desk"), ("on-mark", "mark"),
           ("moss", "paper"), ("clay", "paper"), ("ink", "tint"), ("ink-soft", "tint")]


def _linear_srgb(lightness: float, chroma: float, hue: float) -> list[float]:
    a, b = chroma * math.cos(math.radians(hue)), chroma * math.sin(math.radians(hue))
    l_, m_, s_ = (lightness + 0.3963377774 * a + 0.2158037573 * b) ** 3, (lightness - 0.1055613458 * a - 0.0638541728 * b) ** 3, \
                 (lightness - 0.0894841775 * a - 1.2914855480 * b) ** 3
    rgb = (4.0767416621 * l_ - 3.3077115913 * m_ + 0.2309699292 * s_, -1.2684380046 * l_ + 2.6097574011 * m_ - 0.3413193965 * s_,
           -0.0041960863 * l_ - 0.7034186147 * m_ + 1.7076147010 * s_)
    return [min(1.0, max(0.0, v)) for v in rgb]


def _luminance(rgb: list[float]) -> float:
    return 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]


def _tokens(start: str, end: str) -> dict[str, list[float]]:
    block = CSS[CSS.index(start):CSS.index(end, CSS.index(start))]
    return {k: _linear_srgb(float(l) / 100, float(c), float(h)) for k, l, c, h in OKLCH.findall(block)}


THEMES = {"light": _tokens(":root {", "}"), "dark": _tokens(':root[data-theme="dark"]', "}")}


@pytest.mark.parametrize("theme", THEMES)
@pytest.mark.parametrize("fg,bg", TEXT_ON)
def test_text_keeps_aa_contrast(theme, fg, bg):
    lighter, darker = sorted((_luminance(THEMES[theme][fg]), _luminance(THEMES[theme][bg])), reverse=True)
    assert (lighter + 0.05) / (darker + 0.05) >= 4.5, f"{fg} on {bg} in the {theme} theme"
