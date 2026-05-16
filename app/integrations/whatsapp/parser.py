from datetime import datetime, timezone

from app.integrations.whatsapp.types import DeliveryStatus, InboundMessage


def parse_inbound_payload(payload: dict) -> list[InboundMessage]:
    """Extract InboundMessage objects from a raw WhatsApp Cloud API webhook payload.

    Returns only text messages. Silently skips non-text types (image, audio, etc.)
    and any malformed entries — the caller always gets a clean list or an empty one.
    """
    messages: list[InboundMessage] = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            for raw in value.get("messages", []):
                if raw.get("type") != "text":
                    continue
                body = (raw.get("text") or {}).get("body", "").strip()
                if not body:
                    continue
                listing_ref = _extract_listing_ref(raw)
                try:
                    messages.append(InboundMessage(
                        phone_number=raw["from"],
                        message_id=raw["id"],
                        body=body,
                        timestamp=datetime.fromtimestamp(
                            int(raw["timestamp"]), tz=timezone.utc
                        ),
                        listing_ref=listing_ref,
                    ))
                except (KeyError, ValueError, TypeError):
                    continue
    return messages


def parse_delivery_status(payload: dict) -> list[DeliveryStatus]:
    """Extract DeliveryStatus objects from a raw WhatsApp Cloud API webhook payload."""
    statuses: list[DeliveryStatus] = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            for raw in value.get("statuses", []):
                try:
                    statuses.append(DeliveryStatus(
                        message_id=raw["id"],
                        recipient_phone_number=raw["recipient_id"],
                        status=raw["status"],
                        timestamp=datetime.fromtimestamp(
                            int(raw["timestamp"]), tz=timezone.utc
                        ),
                    ))
                except (KeyError, ValueError, TypeError):
                    continue
    return statuses


def _extract_listing_ref(raw_message: dict) -> str | None:
    """Pull listing_ref from a WhatsApp referral object if present.

    Referrals are attached to messages that originate from click-to-chat links
    or QR codes. The source_url is stored as-is; session creation resolves it
    to a listing reference code.
    """
    referral = raw_message.get("referral")
    if not referral:
        return None
    return referral.get("source_url") or None
