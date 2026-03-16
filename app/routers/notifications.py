from __future__ import annotations
import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from app.database import get_db
from app.models.base import User, PushToken
from app.utils.auth import get_current_user

router = APIRouter(prefix="/notifications", tags=["Notifications"])

class RegisterTokenRequest(BaseModel):
    token: str
    platform: str = "android"  # android, ios

@router.post("/register-token")
async def register_push_token(req: RegisterTokenRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    # Remove old tokens for this user
    await db.execute(delete(PushToken).where(PushToken.user_id == user.id))

    pt = PushToken(user_id=user.id, token=req.token, platform=req.platform)
    db.add(pt)
    await db.commit()
    return {"message": "Token registered"}

@router.delete("/unregister")
async def unregister_push_token(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await db.execute(delete(PushToken).where(PushToken.user_id == user.id))
    await db.commit()
    return {"message": "Token removed"}

async def send_push(token: str, title: str, body: str, data: dict = None):
    """Send push notification via Expo Push API"""
    async with httpx.AsyncClient() as client:
        resp = await client.post("https://exp.host/--/api/v2/push/send", json={
            "to": token, "title": title, "body": body, "data": data or {},
            "sound": "default", "channelId": "earlyeye",
        })
        return resp.json()

@router.post("/send-test")
async def send_test_notification(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(PushToken).where(PushToken.user_id == user.id, PushToken.active == True))
    token = result.scalar_one_or_none()
    if not token:
        raise HTTPException(status_code=404, detail="No push token registered")

    resp = await send_push(token.token, "EarlyEye", "Test notification working!")
    return {"message": "Sent", "response": resp}
