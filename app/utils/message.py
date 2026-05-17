import re

_AGENT_REQUEST_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bhuman\b", re.IGNORECASE),
    re.compile(r"\bagent\b", re.IGNORECASE),
    re.compile(r"\bspeak to (a |an |the )?person\b", re.IGNORECASE),
    re.compile(r"\btalk to (a |an |the )?person\b", re.IGNORECASE),
    re.compile(r"\breal person\b", re.IGNORECASE),
    re.compile(r"\breal agent\b", re.IGNORECASE),
    re.compile(r"\bnot (a |an )?bot\b", re.IGNORECASE),
    re.compile(r"\bsomeone (from|at)\b", re.IGNORECASE),
    re.compile(r"\bcall me\b", re.IGNORECASE),
]


def is_agent_request(body: str) -> bool:
    """Return True if the message body contains a recognisable agent-request signal.

    Pre-LLM fast-path check. Intentionally broad — false positives are safe
    because escalation is the correct default when the signal is ambiguous.
    """
    return any(pattern.search(body) for pattern in _AGENT_REQUEST_PATTERNS)
