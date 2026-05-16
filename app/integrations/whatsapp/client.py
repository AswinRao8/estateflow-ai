import httpx

from app.config import Settings
from app.exceptions import WhatsAppAPIError


class WhatsAppClient:
    """Async client for the WhatsApp Cloud API.

    Owns all HTTP communication with the provider. Services and workflows call
    this client — they never touch httpx or provider URLs directly.
    """

    def __init__(self, settings: Settings) -> None:
        self._base_url = (
            f"https://graph.facebook.com/"
            f"{settings.whatsapp_api_version}/"
            f"{settings.whatsapp_phone_number_id}"
        )
        self._headers = {
            "Authorization": f"Bearer {settings.whatsapp_access_token}",
            "Content-Type": "application/json",
        }

    async def send_text(self, to: str, body: str) -> str:
        """Send a plain text message. Returns the provider message ID."""
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"body": body},
        }
        async with httpx.AsyncClient() as http:
            response = await http.post(
                f"{self._base_url}/messages",
                headers=self._headers,
                json=payload,
                timeout=10.0,
            )
        if response.status_code != 200:
            raise WhatsAppAPIError(response.status_code, response.text)
        data = response.json()
        return data["messages"][0]["id"]
