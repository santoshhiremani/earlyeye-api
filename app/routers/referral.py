from __future__ import annotations
import random, string
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.base import User
from app.utils.auth import get_current_user

router = APIRouter(prefix="/referral", tags=["Referral"])

REFERRAL_REWARD_CREDITS = 1

def generate_code() -> str:
    chars = string.ascii_uppercase + string.digits
    return "EARLY" + ''.join(random.choices(chars, k=4))

@router.get("/my-code")
async def get_my_referral_code(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if not user.referral_code:
        for _ in range(10):
            code = generate_code()
            existing = await db.execute(select(User).where(User.referral_code == code))
            if not existing.scalar_one_or_none():
                user.referral_code = code
                await db.commit()
                break
    return {
        "referral_code": user.referral_code,
        "referral_count": user.referral_count or 0,
        "referral_credits_earned": user.referral_credits_earned or 0,
        "share_message": f"I use EarlyEye to screen my child's eyes — it's incredible! Use my code {user.referral_code} to get a free scan. Download: https://earlyeye.in",
    }

class ApplyReferralRequest(BaseModel):
    code: str

@router.post("/apply")
async def apply_referral(req: ApplyReferralRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    code = req.code.strip().upper()
    if user.referral_code == code:
        raise HTTPException(status_code=400, detail="You can't use your own referral code")
    if user.referred_by:
        raise HTTPException(status_code=400, detail="You've already applied a referral code")
    result = await db.execute(select(User).where(User.referral_code == code))
    referrer = result.scalar_one_or_none()
    if not referrer:
        raise HTTPException(status_code=404, detail="Invalid referral code")
    user.referred_by = referrer.id
    user.scan_credits = (user.scan_credits or 0) + REFERRAL_REWARD_CREDITS
    referrer.referral_count = (referrer.referral_count or 0) + 1
    referrer.referral_credits_earned = (referrer.referral_credits_earned or 0) + REFERRAL_REWARD_CREDITS
    referrer.scan_credits = (referrer.scan_credits or 0) + REFERRAL_REWARD_CREDITS
    await db.commit()
    return {"message": f"Referral applied! You got {REFERRAL_REWARD_CREDITS} free scan credit.", "credits_earned": REFERRAL_REWARD_CREDITS}
