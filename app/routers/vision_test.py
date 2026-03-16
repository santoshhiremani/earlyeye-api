from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.base import User, Child, VisionResult
from app.utils.auth import get_current_user

router = APIRouter(prefix="/vision-test", tags=["Vision Test"])

class EyeResultInput(BaseModel):
    eye: str  # right, left
    pass_result: str  # pass, fail, inconclusive
    correct_answers: int
    total_questions: int
    lowest_line_passed: int  # Snellen denominator: 20, 30, 40, 60, 200

class VisionTestRequest(BaseModel):
    child_id: str
    date: str
    optotype_mode: str = "lea"
    right_eye: Optional[EyeResultInput] = None
    left_eye: Optional[EyeResultInput] = None
    overall_pass: str = "inconclusive"
    recommendation: str = ""

@router.post("/")
async def submit_vision_test(req: VisionTestRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Child).where(Child.id == req.child_id, Child.user_id == user.id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Child not found")

    vr = VisionResult(
        child_id=req.child_id, user_id=user.id, date=req.date,
        optotype_mode=req.optotype_mode,
        right_eye=req.right_eye.dict() if req.right_eye else None,
        left_eye=req.left_eye.dict() if req.left_eye else None,
        overall_pass=req.overall_pass,
        recommendation=req.recommendation,
    )
    db.add(vr)
    await db.commit()
    await db.refresh(vr)

    return {"id": str(vr.id), "overall_pass": vr.overall_pass}

@router.get("/{child_id}")
async def get_vision_results(child_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(VisionResult).where(VisionResult.child_id == child_id, VisionResult.user_id == user.id)
        .order_by(VisionResult.created_at.desc()).limit(20)
    )
    results = result.scalars().all()
    return [{
        "id": str(r.id), "date": r.date, "optotype_mode": r.optotype_mode,
        "right_eye": r.right_eye, "left_eye": r.left_eye,
        "overall_pass": r.overall_pass, "recommendation": r.recommendation,
    } for r in results]
