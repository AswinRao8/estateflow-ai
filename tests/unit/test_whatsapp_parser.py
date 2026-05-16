from datetime import datetime, timezone

from app.integrations.whatsapp.parser import parse_delivery_status, parse_inbound_payload

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _text_payload(body: str = "Hello", from_: str = "+15550001234", referral: dict | None = None) -> dict:
    msg: dict = {
        "from": from_,
        "id": "wamid.test001",
        "timestamp": "1700000000",
        "type": "text",
        "text": {"body": body},
    }
    if referral:
        msg["referral"] = referral
    return {
        "object": "whatsapp_business_account",
        "entry": [{"id": "biz123", "changes": [{"value": {"messages": [msg]}, "field": "messages"}]}],
    }


def _status_payload(status: str = "delivered") -> dict:
    return {
        "object": "whatsapp_business_account",
        "entry": [{"id": "biz123", "changes": [{"value": {
            "statuses": [{
                "id": "wamid.test001",
                "status": status,
                "timestamp": "1700000000",
                "recipient_id": "+15550001234",
            }]
        }, "field": "messages"}]}],
    }


# ---------------------------------------------------------------------------
# parse_inbound_payload
# ---------------------------------------------------------------------------

def test_parses_text_message():
    msgs = parse_inbound_payload(_text_payload("I'm interested"))
    assert len(msgs) == 1
    m = msgs[0]
    assert m.phone_number == "+15550001234"
    assert m.message_id == "wamid.test001"
    assert m.body == "I'm interested"
    assert m.listing_ref is None
    assert isinstance(m.timestamp, datetime)
    assert m.timestamp.tzinfo == timezone.utc


def test_timestamp_converts_unix_epoch():
    msgs = parse_inbound_payload(_text_payload())
    assert msgs[0].timestamp == datetime(2023, 11, 14, 22, 13, 20, tzinfo=timezone.utc)


def test_skips_non_text_message_type():
    payload = {
        "object": "whatsapp_business_account",
        "entry": [{"changes": [{"value": {"messages": [{
            "from": "+1555",
            "id": "wamid.img",
            "timestamp": "1700000000",
            "type": "image",
            "image": {"id": "img123"},
        }]}}]}],
    }
    assert parse_inbound_payload(payload) == []


def test_skips_empty_text_body():
    payload = {
        "object": "whatsapp_business_account",
        "entry": [{"changes": [{"value": {"messages": [{
            "from": "+1555",
            "id": "wamid.empty",
            "timestamp": "1700000000",
            "type": "text",
            "text": {"body": "   "},
        }]}}]}],
    }
    assert parse_inbound_payload(payload) == []


def test_returns_empty_list_when_no_messages_key():
    payload = {"object": "whatsapp_business_account", "entry": [{"changes": [{"value": {}}]}]}
    assert parse_inbound_payload(payload) == []


def test_returns_empty_list_on_empty_payload():
    assert parse_inbound_payload({}) == []


def test_skips_malformed_entry_without_raising():
    payload = {
        "object": "whatsapp_business_account",
        "entry": [{"changes": [{"value": {"messages": [{"type": "text"}]}}]}],
    }
    # Missing "from", "id", "timestamp" — should silently skip, not raise
    result = parse_inbound_payload(payload)
    assert result == []


def test_extracts_listing_ref_from_referral():
    referral = {"source_url": "https://agency.com/listings/villa-123", "source_type": "url"}
    msgs = parse_inbound_payload(_text_payload(referral=referral))
    assert msgs[0].listing_ref == "https://agency.com/listings/villa-123"


def test_listing_ref_none_when_no_referral():
    msgs = parse_inbound_payload(_text_payload())
    assert msgs[0].listing_ref is None


def test_parses_multiple_messages_in_one_payload():
    msgs_raw = [
        {"from": "+1555000001", "id": "wamid.a", "timestamp": "1700000001", "type": "text", "text": {"body": "Hi"}},
        {"from": "+1555000002", "id": "wamid.b", "timestamp": "1700000002", "type": "text", "text": {"body": "Hello"}},
    ]
    payload = {"object": "whatsapp_business_account", "entry": [{"changes": [{"value": {"messages": msgs_raw}}]}]}
    result = parse_inbound_payload(payload)
    assert len(result) == 2
    assert result[0].phone_number == "+1555000001"
    assert result[1].phone_number == "+1555000002"


# ---------------------------------------------------------------------------
# parse_delivery_status
# ---------------------------------------------------------------------------

def test_parses_delivered_status():
    statuses = parse_delivery_status(_status_payload("delivered"))
    assert len(statuses) == 1
    s = statuses[0]
    assert s.message_id == "wamid.test001"
    assert s.status == "delivered"
    assert s.recipient_phone_number == "+15550001234"
    assert isinstance(s.timestamp, datetime)


def test_parses_read_status():
    statuses = parse_delivery_status(_status_payload("read"))
    assert statuses[0].status == "read"


def test_returns_empty_list_when_no_statuses():
    assert parse_delivery_status(_text_payload()) == []


def test_skips_malformed_status_entry_without_raising():
    payload = {"entry": [{"changes": [{"value": {"statuses": [{"incomplete": True}]}}]}]}
    assert parse_delivery_status(payload) == []
