from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.base import User, Child, RiskResult
from app.utils.auth import get_current_user

router = APIRouter(prefix="/risk-quiz", tags=["Risk Quiz"])

class RiskQuizRequest(BaseModel):
    child_id: str
    date: str
    answers: dict  # {age, parentalMyopia, dailyScreenHours, readingDistanceCm, dailyOutdoorMinutes, symptoms}

def calculate_risk(answers: dict) -> dict:
    score = 0
    factors = []

    # Parental myopia
    pm = answers.get("parentalMyopia", "none")
    if pm == "both":
        score += 30
        factors.append("Both parents have myopia (+30)")
    elif pm == "one":
        score += 15
        factors.append("One parent has myopia (+15)")

    # Screen time
    screen = answers.get("dailyScreenHours", 0)
    if screen > 4:
        score += 25
        factors.append(f"High screen time: {screen}h/day (+25)")
    elif screen > 2:
        score += 15
        factors.append(f"Moderate screen time: {screen}h/day (+15)")

    # Outdoor time
    outdoor = answers.get("dailyOutdoorMinutes", 0)
    if outdoor < 30:
        score += 20
        factors.append(f"Very low outdoor time: {outdoor}min/day (+20)")
    elif outdoor < 60:
        score += 10
        factors.append(f"Low outdoor time: {outdoor}min/day (+10)")

    # Reading distance
    dist = answers.get("readingDistanceCm", 30)
    if dist < 20:
        score += 15
        factors.append(f"Close reading distance: {dist}cm (+15)")

    # Symptoms
    symptoms = answers.get("symptoms", [])
    symptom_points = len([s for s in symptoms if s != "none"]) * 5
    if symptom_points > 0:
        score += symptom_points
        factors.append(f"Symptoms reported: {', '.join(s for s in symptoms if s != 'none')} (+{symptom_points})")

    score = min(score, 100)
    level = "high" if score >= 60 else "moderate" if score >= 30 else "low"

    recs = {
        "low": "Low risk. Continue regular outdoor time and screen limits. Next screening in 6 months.",
        "moderate": "Moderate risk. Schedule an eye check within 3 months. Increase outdoor time to 2+ hours daily.",
        "high": "High risk. Schedule an ophthalmologist visit within 2 weeks. Reduce screen time and increase outdoor exposure.",
    }

    return {"level": level, "score": score, "factors": factors, "recommendation": recs[level]}

@router.post("/")
async def submit_risk_quiz(req: RiskQuizRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    # Verify child
    result = await db.execute(select(Child).where(Child.id == req.child_id, Child.user_id == user.id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Child not found")

    calc = calculate_risk(req.answers)

    rr = RiskResult(
        child_id=req.child_id, user_id=user.id, date=req.date,
        level=calc["level"], score=calc["score"],
        factors=calc["factors"], recommendation=calc["recommendation"],
        answers=req.answers,
    )
    db.add(rr)
    await db.commit()
    await db.refresh(rr)

    return {"id": str(rr.id), **calc}

@router.get("/{child_id}")
async def get_risk_results(child_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(RiskResult).where(RiskResult.child_id == child_id, RiskResult.user_id == user.id)
        .order_by(RiskResult.created_at.desc()).limit(20)
    )
    results = result.scalars().all()
    return [{
        "id": str(r.id), "date": r.date, "level": r.level, "score": r.score,
        "factors": r.factors, "recommendation": r.recommendation, "answers": r.answers,
    } for r in results]
