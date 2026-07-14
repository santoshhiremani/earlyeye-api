from fastapi import APIRouter, Request, Response, HTTPException
from app.config import get_settings

router = APIRouter(prefix="/whatsapp", tags=["WhatsApp"])
settings = get_settings()


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
