"""Smoke tests for the /webhook/inbound and /webhook/status endpoints.

POST /webhook/inbound  — process_inbound_message is patched at the router
                         module level so the full AI pipeline is never invoked.
                         Tests verify routing logic: message parsing, per-message
                         error swallowing, and always-200 contract.

POST /webhook/status   — no pipeline involvement; tests verify the endpoint
                         accepts well-formed delivery status payloads and always
                         returns 200 (malformed entries are silently skipped by
                         the parser).
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.asyncio

_INBOUND = "/webhook/inbound"
_STATUS = "/webhook/status"

# ---------------------------------------------------------------------------
# Shared payload fixtures
# ---------------------------------------------------------------------------

_TEXT_PAYLOAD = {
    "object": "whatsapp_business_account",
    "entry": [
        {
            "id": "102290129340398",
            "changes": [
                {
                    "value": {
                        "messaging_product": "whatsapp",
                        "metadata": {
                            "display_phone_number": "15550000000",
                            "phone_number_id": "106540352242922",
                        },
                        "contacts": [{"profile": {"name": "Test User"}, "wa_id": "971500000001"}],
                        "messages": [
                            {
                                "from": "971500000001",
                                "id": "wamid.smoketest001",
                                "timestamp": "1716912000",
                                "type": "text",
                                "text": {"body": "Hi, I am interested in a property"},
                            }
                        ],
                    },
                    "field": "messages",
                }
            ],
        }
    ],
}

_IMAGE_PAYLOAD = {
    "object": "whatsapp_business_account",
    "entry": [
        {
            "id": "102290129340398",
            "changes": [
                {
                    "value": {
                        "messaging_product": "whatsapp",
                        "messages": [
                            {
                                "from": "971500000002",
                                "id": "wamid.smoketest002",
                                "timestamp": "1716912000",
                                "type": "image",
                            }
                        ],
                    },
                    "field": "messages",
                }
            ],
        }
    ],
}

_EMPTY_MESSAGES_PAYLOAD = {
    "object": "whatsapp_business_account",
    "entry": [
        {
            "id": "102290129340398",
            "changes": [
                {
                    "value": {"messaging_product": "whatsapp", "messages": []},
                    "field": "messages",
                }
            ],
        }
    ],
}

_STATUS_PAYLOAD = {
    "object": "whatsapp_business_account",
    "entry": [
        {
            "id": "102290129340398",
            "changes": [
                {
                    "value": {
                        "messaging_product": "whatsapp",
                        "statuses": [
                            {
                                "id": "wamid.smoketest001",
                                "recipient_id": "971500000001",
                                "status": "delivered",
                                "timestamp": "1716912060",
                            }
                        ],
                    },
                    "field": "messages",
                }
            ],
        }
    ],
}


def _mock_pipeline_result(is_human_active: bool = False):
    result = MagicMock()
    result.is_human_active = is_human_active
    return result


# ---------------------------------------------------------------------------
# POST /webhook/inbound
# ---------------------------------------------------------------------------


async def test_inbound_valid_text_message_returns_200(http_client):
    mock = AsyncMock(return_value=_mock_pipeline_result())
    with patch("app.routers.whatsapp_router.process_inbound_message", new=mock):
        resp = await http_client.post(_INBOUND, json=_TEXT_PAYLOAD)
    assert resp.status_code == 200
    mock.assert_awaited_once()


async def test_inbound_pipeline_called_with_correct_phone(http_client):
    mock = AsyncMock(return_value=_mock_pipeline_result())
    with patch("app.routers.whatsapp_router.process_inbound_message", new=mock):
        await http_client.post(_INBOUND, json=_TEXT_PAYLOAD)
    _, kwargs = mock.call_args
    assert kwargs["message"].phone_number == "971500000001"
    assert kwargs["message"].body == "Hi, I am interested in a property"


async def test_inbound_non_text_message_skipped_by_parser(http_client):
    # Image messages are dropped by parse_inbound_payload before the pipeline runs.
    mock = AsyncMock(return_value=_mock_pipeline_result())
    with patch("app.routers.whatsapp_router.process_inbound_message", new=mock):
        resp = await http_client.post(_INBOUND, json=_IMAGE_PAYLOAD)
    assert resp.status_code == 200
    mock.assert_not_awaited()


async def test_inbound_empty_messages_not_dispatched(http_client):
    mock = AsyncMock(return_value=_mock_pipeline_result())
    with patch("app.routers.whatsapp_router.process_inbound_message", new=mock):
        resp = await http_client.post(_INBOUND, json=_EMPTY_MESSAGES_PAYLOAD)
    assert resp.status_code == 200
    mock.assert_not_awaited()


async def test_inbound_pipeline_exception_swallowed_returns_200(http_client):
    # Per spec: per-message errors are caught and logged; 200 is always returned
    # so WhatsApp does not retry a message that would fail for the same reason.
    mock = AsyncMock(side_effect=RuntimeError("AI service unavailable"))
    with patch("app.routers.whatsapp_router.process_inbound_message", new=mock):
        resp = await http_client.post(_INBOUND, json=_TEXT_PAYLOAD)
    assert resp.status_code == 200


async def test_inbound_human_active_lead_still_returns_200(http_client):
    mock = AsyncMock(return_value=_mock_pipeline_result(is_human_active=True))
    with patch("app.routers.whatsapp_router.process_inbound_message", new=mock):
        resp = await http_client.post(_INBOUND, json=_TEXT_PAYLOAD)
    assert resp.status_code == 200


async def test_inbound_missing_entry_field_returns_422(http_client):
    resp = await http_client.post(_INBOUND, json={"object": "whatsapp_business_account"})
    assert resp.status_code == 422
    assert resp.json()["success"] is False


# ---------------------------------------------------------------------------
# POST /webhook/status
# ---------------------------------------------------------------------------


async def test_status_delivered_event_returns_200(http_client):
    resp = await http_client.post(_STATUS, json=_STATUS_PAYLOAD)
    assert resp.status_code == 200


async def test_status_read_event_returns_200(http_client):
    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "102290129340398",
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "statuses": [
                                {
                                    "id": "wamid.smoketest001",
                                    "recipient_id": "971500000001",
                                    "status": "read",
                                    "timestamp": "1716912120",
                                }
                            ],
                        },
                        "field": "messages",
                    }
                ],
            }
        ],
    }
    resp = await http_client.post(_STATUS, json=payload)
    assert resp.status_code == 200


async def test_status_empty_statuses_returns_200(http_client):
    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "102290129340398",
                "changes": [
                    {
                        "value": {"messaging_product": "whatsapp", "statuses": []},
                        "field": "messages",
                    }
                ],
            }
        ],
    }
    resp = await http_client.post(_STATUS, json=payload)
    assert resp.status_code == 200


async def test_status_malformed_status_entry_skipped_returns_200(http_client):
    # Parser skips entries missing required fields; endpoint still returns 200.
    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "102290129340398",
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "statuses": [{"id": "wamid.partial"}],  # missing recipient_id, status, timestamp
                        },
                        "field": "messages",
                    }
                ],
            }
        ],
    }
    resp = await http_client.post(_STATUS, json=payload)
    assert resp.status_code == 200
