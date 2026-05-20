"""Pydantic models for the Meta WhatsApp Cloud API webhook payload.

These models exist for two purposes:
  1. Swagger UI documentation — FastAPI generates a JSON schema and example
     request body editor from them.
  2. Light structural validation at the router boundary.

They are NOT the internal domain representation.  The parser
(integrations.whatsapp.parser) converts these provider shapes into the
internal InboundMessage / DeliveryStatus types that the rest of the app uses.

extra="allow" is set on every model so that Meta fields not modelled here
(context, reaction, interactive, etc.) are accepted without errors.  The parser
already silently skips message types it does not handle.

The "from" field on WhatsAppMessage uses alias="from" because "from" is a
Python keyword.  Always call .model_dump(by_alias=True) before passing the
payload dict to the parser.
"""
from pydantic import BaseModel, ConfigDict, Field


class _Extra(BaseModel):
    model_config = ConfigDict(extra="allow")


class WhatsAppTextBody(_Extra):
    body: str


class WhatsAppReferral(_Extra):
    source_url: str
    source_type: str = "url"


class WhatsAppMessage(_Extra):
    from_number: str = Field(alias="from")
    id: str
    timestamp: str
    type: str
    text: WhatsAppTextBody | None = None
    referral: WhatsAppReferral | None = None


class WhatsAppMetadata(_Extra):
    display_phone_number: str
    phone_number_id: str


class WhatsAppContactProfile(_Extra):
    name: str


class WhatsAppContact(_Extra):
    profile: WhatsAppContactProfile | None = None
    wa_id: str


class WhatsAppValue(_Extra):
    messaging_product: str = "whatsapp"
    metadata: WhatsAppMetadata | None = None
    contacts: list[WhatsAppContact] = []
    messages: list[WhatsAppMessage] = []


class WhatsAppChange(_Extra):
    value: WhatsAppValue
    field: str = "messages"


class WhatsAppEntry(_Extra):
    id: str
    changes: list[WhatsAppChange]


_EXAMPLE_TEXT = {
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
                        "contacts": [
                            {"profile": {"name": "Ahmed Al-Rashidi"}, "wa_id": "971501234567"}
                        ],
                        "messages": [
                            {
                                "from": "971501234567",
                                "id": "wamid.HBgNOTcxNTAxMjM0NTY3FQIAERgSM0E4N0Y0OTY1M0FDOUI5NTQAA",
                                "timestamp": "1716912000",
                                "type": "text",
                                "text": {
                                    "body": "Hi, I'm interested in the Marina Quarter apartment."
                                },
                            }
                        ],
                    },
                    "field": "messages",
                }
            ],
        }
    ],
}

_EXAMPLE_REFERRAL = {
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
                        "contacts": [
                            {"profile": {"name": "Sarah Chen"}, "wa_id": "6591234568"}
                        ],
                        "messages": [
                            {
                                "from": "6591234568",
                                "id": "wamid.HBgNNjU5MTIzNDU2OAIAERgSREVBREJFRUYwMDAwMDAwMAA",
                                "timestamp": "1716998400",
                                "type": "text",
                                "text": {"body": "Hello, I'd like more info on this property."},
                                "referral": {
                                    "source_url": "https://agency.com/listings/REF-003",
                                    "source_type": "url",
                                },
                            }
                        ],
                    },
                    "field": "messages",
                }
            ],
        }
    ],
}


class WhatsAppWebhookPayload(_Extra):
    """Meta WhatsApp Cloud API inbound webhook payload.

    Sent by Meta for every inbound message and notification event.
    The `entry` array can contain multiple business accounts; `changes` within
    each entry can contain multiple message batches.
    """
    object: str = "whatsapp_business_account"
    entry: list[WhatsAppEntry]


# OpenAPI example objects — referenced by the router via Body(openapi_examples=...).
# Defined here to keep all provider-shape knowledge in one place.
WEBHOOK_EXAMPLES: dict = {
    "plain_text_message": {
        "summary": "Plain text message",
        "value": _EXAMPLE_TEXT,
    },
    "click_to_chat_with_listing_referral": {
        "summary": "Click-to-chat via listing link (with referral)",
        "value": _EXAMPLE_REFERRAL,
    },
}
