from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.base import User, Child, DailyLog
from app.utils.auth import get_current_user

router = APIRouter(prefix="/logs", tags=["Daily Logs"])

class LogScreenTimeRequest(BaseModel):
    child_id: str
    date: str
    minutes: int

class LogOutdoorRequest(BaseModel):
    child_id: str
    date: str
    minutes: int

class LogEyeBreakRequest(BaseModel):
    child_id: str
    date: str

class LogAppUsageRequest(BaseModel):
    child_id: str
    date: str
    app_name: str
    app_emoji: str
    minutes: int

async def get_or_create_log(db: AsyncSession, child_id: str, date: str) -> DailyLog:
    result = await db.execute(select(DailyLog).where(DailyLog.child_id == child_id, DailyLog.date == date))
    log = result.scalar_one_or_none()
    if not log:
        log = DailyLog(child_id=child_id, date=date)
        db.add(log)
    return log

@router.post("/screen-time")
async def log_screen_time(req: LogScreenTimeRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    log = await get_or_create_log(db, req.child_id, req.date)
    log.screen_minutes = req.minutes
    await db.commit()
    return {"screen_minutes": log.screen_minutes}

@router.post("/outdoor")
async def log_outdoor(req: LogOutdoorRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    log = await get_or_create_log(db, req.child_id, req.date)
    log.outdoor_minutes += req.minutes
    await db.commit()
    return {"outdoor_minutes": log.outdoor_minutes}

@router.post("/eye-break")
async def log_eye_break(req: LogEyeBreakRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    log = await get_or_create_log(db, req.child_id, req.date)
    log.eye_breaks_done += 1
    await db.commit()
    return {"eye_breaks_done": log.eye_breaks_done}

@router.post("/app-usage")
async def log_app_usage(req: LogAppUsageRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    log = await get_or_create_log(db, req.child_id, req.date)
    usage = log.app_usage or []
    existing = next((a for a in usage if a["name"] == req.app_name), None)
    if existing:
        existing["minutes"] += req.minutes
    else:
        usage.append({"name": req.app_name, "emoji": req.app_emoji, "minutes": req.minutes})
    log.app_usage = usage
    log.screen_minutes = sum(a["minutes"] for a in usage)
    await db.commit()
    return {"app_usage": log.app_usage, "screen_minutes": log.screen_minutes}

@router.get("/week/{child_id}")
async def get_week_logs(child_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    from datetime import date, timedelta
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    dates = [(monday + timedelta(days=i)).isoformat() for i in range(7)]

    result = await db.execute(select(DailyLog).where(DailyLog.child_id == child_id, DailyLog.date.in_(dates)))
    logs = {l.date: l for l in result.scalars().all()}

    return [{"date": d, "screen_minutes": logs[d].screen_minutes if d in logs else 0,
             "outdoor_minutes": logs[d].outdoor_minutes if d in logs else 0,
             "eye_breaks_done": logs[d].eye_breaks_done if d in logs else 0,
             "app_usage": logs[d].app_usage if d in logs else []} for d in dates]
