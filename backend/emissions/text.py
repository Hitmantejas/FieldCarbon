from datetime import datetime


def bullets(*lines: str) -> str:
    """An explanation as short bullets. **Bold** marks the facts worth noticing; the sheet renders both."""
    return "\n".join(f"- {line}" for line in lines)


def month_name(iso: str) -> str:
    return datetime.strptime(iso, "%Y-%m").strftime("%B %Y")
