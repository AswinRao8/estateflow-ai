from typing import Annotated

from fastapi import APIRouter, Body, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse, Response

from app.dependencies import DbSessionDep, SettingsDep
from app.integrations.whatsapp.parser import parse_delivery_status, parse_inbound_payload
from app.integrations.whatsapp.security import validate_webhook_signature
from app.integrations.whatsapp.webhook_schema import WEBHOOK_EXAMPLES, WhatsAppWebhookPayload
from app.utils.logging import get_logger
from app.workflows.inbound_message_workflow import process_inbound_message

router = APIRouter(prefix="/webhook", tags=["WhatsApp"])
logger = get_logger(__name__)


@router.get("/inbound", summary="WhatsApp webhook verification")
async def verify_webhook(
    settings: SettingsDep,
    hub_mode: str = Query(alias="hub.mode", default=""),
    hub_challenge: str = Query(alias="hub.challenge", default=""),
    hub_verify_token: str = Query(alias="hub.verify_token", default=""),
) -> PlainTextResponse:
    """Meta sends a GET with hub.challenge when first configuring the webhook URL.
    Return the challenge value as plain text to confirm ownership."""
    if hub_mode != "subscribe" or hub_verify_token != settings.whatsapp_webhook_verify_token:
        raise HTTPException(status_code=403, detail="Webhook verification failed")
    return PlainTextResponse(hub_challenge)


@router.post("/inbound", summary="Receive inbound WhatsApp message")
async def receive_inbound_message(
    request: Request,
    body: Annotated[WhatsAppWebhookPayload, Body(openapi_examples=WEBHOOK_EXAMPLES)],
    settings: SettingsDep,
    db: DbSessionDep,
) -> Response:
    """Validate signature → parse → run inbound pipeline → return 200.

    Errors in per-message processing are logged and swallowed — returning 200
    prevents WhatsApp from retrying a message that would fail for the same
    reason on every retry (e.g., a parse or routing bug).

    Starlette caches request.body() so the HMAC check reads the same bytes
    that FastAPI already consumed to parse `body`.
    """
    raw_body = await request.body()
    _verify_signature(raw_body, request, settings)

    # by_alias=True is required so WhatsAppMessage.from_number serialises
    # back to the key "from" that parse_inbound_payload expects.
    messages = parse_inbound_payload(body.model_dump(by_alias=True))
    for msg in messages:
        req_id = ""
        try:
            result = await process_inbound_message(db, message=msg)
            req_id = result.req_id
        except Exception:
            logger.exception(
                "[%s] Failed to process inbound message | id=%s | phone=%s",
                req_id or "--------",
                msg.message_id,
                msg.phone_number,
            )

    return Response(status_code=200)


@router.post("/status", summary="Receive WhatsApp delivery status update")
async def receive_status_update(request: Request, settings: SettingsDep) -> Response:
    """Validate signature, parse delivery status events, log, return 200."""
    raw_body = await request.body()
    _verify_signature(raw_body, request, settings)

    try:
        payload = await request.json()
    except Exception:
        logger.warning("Malformed JSON in status webhook payload")
        return Response(status_code=200)

    statuses = parse_delivery_status(payload)
    for s in statuses:
        logger.info(
            "Delivery status | id=%s | status=%s | recipient=%s",
            s.message_id,
            s.status,
            s.recipient_phone_number,
        )

    return Response(status_code=200)


def _verify_signature(raw_body: bytes, request: Request, settings: SettingsDep) -> None:
    """Raise 401 if signature validation is configured and fails.

    Skipped when whatsapp_webhook_secret is not set so the webhook can be
    tested locally without signing every request.
    """
    if not settings.whatsapp_webhook_secret:
        return
    signature = request.headers.get("X-Hub-Signature-256", "")
    if not validate_webhook_signature(raw_body, signature, settings.whatsapp_webhook_secret):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")
