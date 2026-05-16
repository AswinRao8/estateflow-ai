from urllib.parse import urlparse


def extract_listing_ref_code(url: str | None) -> str | None:
    """Extract a listing reference code from a WhatsApp click-to-chat referral URL.

    The source_url from a WhatsApp referral is an agency-configured entry link.
    Reference codes are conventionally the terminal path segment
    (e.g. https://agency.com/listings/REF-001 → "REF-001").

    Returns the candidate segment, or None if the URL is absent or has no usable path.
    The returned value is unvalidated — callers must confirm the code exists in the
    listings table before using it as listing context.
    """
    if not url:
        return None
    path = urlparse(url).path.rstrip("/")
    if not path:
        return None
    _, _, segment = path.rpartition("/")
    return segment or None
