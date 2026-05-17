import re

_MARKDOWN_HEADERS = re.compile(r"^#{1,6}\s+", re.MULTILINE)
_MARKDOWN_BOLD = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)
_MARKDOWN_ITALIC = re.compile(r"\*(.+?)\*", re.DOTALL)
_MARKDOWN_CODE = re.compile(r"`(.+?)`", re.DOTALL)
_MARKDOWN_BULLETS = re.compile(r"^[*\-]\s+", re.MULTILINE)
_PRICE_LIKE = re.compile(r"\b(\d[\d,\.]{4,})\b")

MAX_RESPONSE_LENGTH = 1000


def sanitize_response(text: str, listing_price: float | None = None) -> str:
    """Strip markdown formatting, enforce length limit, and guard against price hallucination.

    WhatsApp renders markdown literally — asterisks, hashes, and backticks
    appear as raw characters and degrade the message quality.
    """
    text = _MARKDOWN_HEADERS.sub("", text)
    text = _MARKDOWN_BOLD.sub(r"\1", text)
    text = _MARKDOWN_ITALIC.sub(r"\1", text)
    text = _MARKDOWN_CODE.sub(r"\1", text)
    text = _MARKDOWN_BULLETS.sub("• ", text)
    text = text.strip()

    if listing_price is not None:
        text = _check_price_hallucination(text, listing_price)

    if len(text) > MAX_RESPONSE_LENGTH:
        text = text[:MAX_RESPONSE_LENGTH].rsplit(" ", 1)[0] + "…"

    return text


def _check_price_hallucination(text: str, known_price: float) -> str:
    """Replace any price-like number that deviates >1% from the known listing price.

    Only fires when the response contains a number with 5+ digits that does
    not match the known price. Avoids the most common hallucination pattern
    where the model invents a plausible-looking price.
    """
    for raw in _PRICE_LIKE.findall(text):
        try:
            value = float(raw.replace(",", ""))
        except ValueError:
            continue
        deviation = abs(value - known_price) / max(known_price, 1)
        if deviation > 0.01:
            text = text.replace(raw, "[price on request]", 1)
    return text
