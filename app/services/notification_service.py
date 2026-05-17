from app.config import get_settings
from app.integrations.whatsapp.client import WhatsAppClient
from app.utils.logging import get_logger

logger = get_logger(__name__)

_client: WhatsAppClient | None = None


def _get_client() -> WhatsAppClient:
    global _client
    if _client is None:
        _client = WhatsAppClient(get_settings())
    return _client


async def send_whatsapp_text(phone_number: str, body: str) -> str | None:
    """Send a WhatsApp text message. Returns the provider message ID, or None on failure.

    Errors are logged and swallowed — a delivery failure must not crash the
    inbound pipeline. The message is still persisted in the database regardless
    of whether the send succeeded.
    """
    try:
        provider_id = await _get_client().send_text(to=phone_number, body=body)
        logger.info("Sent WhatsApp message | to=%s | provider_id=%s", phone_number, provider_id)
        return provider_id
    except Exception:
        logger.exception("WhatsApp send failed | to=%s", phone_number)
        return None
