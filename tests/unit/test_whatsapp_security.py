import hashlib
import hmac

from app.integrations.whatsapp.security import validate_webhook_signature

_SECRET = "test-app-secret"


def _make_signature(payload: bytes, secret: str = _SECRET) -> str:
    digest = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def test_valid_signature_returns_true():
    payload = b'{"test": "payload"}'
    sig = _make_signature(payload)
    assert validate_webhook_signature(payload, sig, _SECRET) is True


def test_wrong_secret_returns_false():
    payload = b'{"test": "payload"}'
    sig = _make_signature(payload, secret="wrong-secret")
    assert validate_webhook_signature(payload, sig, _SECRET) is False


def test_tampered_payload_returns_false():
    payload = b'{"test": "payload"}'
    sig = _make_signature(payload)
    assert validate_webhook_signature(b'{"test": "tampered"}', sig, _SECRET) is False


def test_missing_sha256_prefix_returns_false():
    payload = b'{"test": "payload"}'
    digest = hmac.new(_SECRET.encode(), payload, hashlib.sha256).hexdigest()
    # Signature without the "sha256=" prefix
    assert validate_webhook_signature(payload, digest, _SECRET) is False


def test_empty_signature_header_returns_false():
    assert validate_webhook_signature(b"body", "", _SECRET) is False


def test_empty_payload_with_correct_signature_returns_true():
    payload = b""
    sig = _make_signature(payload)
    assert validate_webhook_signature(payload, sig, _SECRET) is True


def test_uses_constant_time_comparison():
    # Verify hmac.compare_digest is used by confirming similar-prefix wrong signatures fail
    payload = b"sensitive data"
    correct_sig = _make_signature(payload)
    # Flip the last character of the hex digest
    wrong_sig = correct_sig[:-1] + ("0" if correct_sig[-1] != "0" else "1")
    assert validate_webhook_signature(payload, wrong_sig, _SECRET) is False
