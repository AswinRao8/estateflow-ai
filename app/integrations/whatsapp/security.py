import hashlib
import hmac


def validate_webhook_signature(payload: bytes, signature_header: str, secret: str) -> bool:
    """Return True if signature_header is a valid HMAC-SHA256 signature of payload.

    WhatsApp sends: X-Hub-Signature-256: sha256=<hex_digest>
    Computed as:    HMAC-SHA256(app_secret, raw_request_body)
    """
    if not signature_header.startswith("sha256="):
        return False
    received = signature_header[len("sha256="):]
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, received)
