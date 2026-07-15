import httpx
from fastapi import APIRouter, Request, Response, HTTPException
from app.config import get_settings

router = APIRouter(prefix="/whatsapp", tags=["WhatsApp"])
settings = get_settings()

WHATSAPP_API_URL = "https://graph.facebook.com/v25.0"


async def send_whatsapp_message(to: str, message: str) -> dict:
    """Send a WhatsApp text message via Meta Cloud API."""
    url = f"{WHATSAPP_API_URL}/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": message},
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, headers=headers, json=payload)
        result = resp.json()
        if not resp.is_success:
            print(f"[WhatsApp] Error sending to {to}: {result}")
            raise Exception(result)
        print(f"[WhatsApp] Sent to {to}: {result}")
        return result


@router.get("/webhook")
async def verify_webhook(request: Request):
    mode = request.query_params.get("hub.mode")
    received_token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    if mode == "subscribe" and received_token == settings.WHATSAPP_VERIFY_TOKEN:
        return Response(content=challenge, media_type="text/plain")

    raise HTTPException(status_code=403, detail="Verification failed")


@router.post("/webhook")
async def receive_webhook(request: Request):
    payload = await request.json()
    print("\nWhatsApp webhook received:")
    print(payload)
    return {"success": True}
