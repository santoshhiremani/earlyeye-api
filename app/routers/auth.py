from datetime import datetime, timedelta
import random
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from app.database import get_db
from app.models.base import User, OTPStore
from app.utils.auth import create_token, get_current_user
from app.config import get_settings

router = APIRouter(prefix="/auth", tags=["Auth"])
settings = get_settings()

class SendOTPRequest(BaseModel):
    phone: str

class VerifyOTPRequest(BaseModel):
    phone: str
    otp: str

class UpdateProfileRequest(BaseModel):
    name: str | None = None

@router.post("/send-otp")
async def send_otp(req: SendOTPRequest, db: AsyncSession = Depends(get_db)):
    phone = req.phone.strip().replace(" ", "")
    if len(phone) < 10:
        raise HTTPException(status_code=400, detail="Invalid phone number")

    otp = str(random.randint(100000, 999999))
    expires = datetime.utcnow() + timedelta(minutes=5)

    await db.execute(delete(OTPStore).where(OTPStore.phone == phone))
    db.add(OTPStore(phone=phone, otp=otp, expires_at=expires))
    await db.commit()

    # TODO: Send OTP via MSG91/Twilio
    # For now, return OTP in dev mode
    return {"message": "OTP sent", "dev_otp": otp}

@router.post("/verify-otp")
async def verify_otp(req: VerifyOTPRequest, db: AsyncSession = Depends(get_db)):
    phone = req.phone.strip().replace(" ", "")
    result = await db.execute(
        select(OTPStore).where(OTPStore.phone == phone, OTPStore.verified == False)
        .order_by(OTPStore.created_at.desc()).limit(1)
    )
    otp_record = result.scalar_one_or_none()

    if not otp_record or otp_record.otp != req.otp:
        raise HTTPException(status_code=400, detail="Invalid OTP")
    if otp_record.expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="OTP expired")

    otp_record.verified = True

    user_result = await db.execute(select(User).where(User.phone == phone))
    user = user_result.scalar_one_or_none()
    is_new = user is None

    if not user:
        user = User(phone=phone, name="", week_start_date=datetime.utcnow().strftime("%Y-%m-%d"))
        db.add(user)

    await db.commit()
    await db.refresh(user)

    token = create_token(str(user.id))
    return {"token": token, "user_id": str(user.id), "is_new_user": is_new}

@router.get("/me")
async def get_me(user: User = Depends(get_current_user)):
    return {
        "id": str(user.id), "phone": user.phone, "name": user.name,
        "is_subscribed": user.is_subscribed,
        "subscription_expiry": user.subscription_expiry.isoformat() if user.subscription_expiry else None,
        "scan_credits": user.scan_credits, "weekly_scans_used": user.weekly_scans_used,
    }

@router.patch("/profile")
async def update_profile(req: UpdateProfileRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if req.name is not None:
        user.name = req.name
    await db.commit()
    return {"message": "Profile updated"}
