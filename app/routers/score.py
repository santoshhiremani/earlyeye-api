from __future__ import annotations
from datetime import date, timedelta
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.base import User, Child, DailyLog, Prescription
from app.utils.auth import get_current_user

router = APIRouter(prefix="/score", tags=["Eye Score"])

def calc_weekly_score(logs: list, screen_limit: float, outdoor_goal: float, rx_rate: str) -> dict:
    if not logs:
        return {"total": 0, "screenPts": 0, "outdoorPts": 0, "breakPts": 0, "rxPts": 0,
                "verdict": "No data", "tip": "Start tracking to see your score", "emoji": "📊"}

    days = len(logs)
    avg_screen = sum(l.screen_minutes for l in logs) / days
    avg_outdoor = sum(l.outdoor_minutes for l in logs) / days
    avg_breaks = sum(l.eye_breaks_done for l in logs) / days

    screen_limit_min = screen_limit * 60
    screen_pct = min(avg_screen / screen_limit_min, 2) if screen_limit_min > 0 else 1
    screen_pts = max(0, round(30 * (1 - screen_pct / 2)))

    outdoor_goal_min = outdoor_goal * 60
    outdoor_pct = min(avg_outdoor / outdoor_goal_min, 1.5) if outdoor_goal_min > 0 else 0
    outdoor_pts = min(30, round(30 * outdoor_pct))

    break_pts = min(20, round(20 * min(avg_breaks / 10, 1)))

    rx_pts = 20 if rx_rate == "stable" else 12 if rx_rate == "moderate" else 5

    total = screen_pts + outdoor_pts + break_pts + rx_pts

    if total >= 80:
        verdict, tip, emoji = "Excellent", "Keep it up!", "🌟"
    elif total >= 60:
        verdict, tip, emoji = "Good", "Small improvements will help", "👍"
    elif total >= 40:
        verdict, tip, emoji = "Needs attention", "Focus on outdoor time and screen limits", "⚠️"
    else:
        verdict, tip, emoji = "At risk", "Urgent: reduce screen time, increase outdoor time", "🚨"

    return {"total": total, "screenPts": screen_pts, "outdoorPts": outdoor_pts,
            "breakPts": break_pts, "rxPts": rx_pts, "verdict": verdict, "tip": tip, "emoji": emoji}

@router.get("/{child_id}")
async def get_eye_score(child_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    # Get child
    child_result = await db.execute(select(Child).where(Child.id == child_id, Child.user_id == user.id))
    child = child_result.scalar_one_or_none()
    if not child:
        return {"error": "Child not found"}

    # Get last 7 days of logs
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    dates = [(monday + timedelta(days=i)).isoformat() for i in range(7)]

    logs_result = await db.execute(select(DailyLog).where(DailyLog.child_id == child_id, DailyLog.date.in_(dates)))
    logs = logs_result.scalars().all()

    # Get prescriptions to determine rate
    rx_result = await db.execute(select(Prescription).where(Prescription.child_id == child_id).order_by(Prescription.date.desc()).limit(3))
    rxs = rx_result.scalars().all()

    rx_rate = "stable"
    if len(rxs) >= 2:
        latest_sph = abs(rxs[0].right_sph) + abs(rxs[0].left_sph)
        prev_sph = abs(rxs[1].right_sph) + abs(rxs[1].left_sph)
        diff = latest_sph - prev_sph
        if diff > 1.0:
            rx_rate = "fast"
        elif diff > 0.5:
            rx_rate = "moderate"

    score = calc_weekly_score(logs, child.screen_time_limit_hours, child.outdoor_goal_hours, rx_rate)
    return {"child_id": child_id, "child_name": child.name, "week_start": dates[0], **score}
