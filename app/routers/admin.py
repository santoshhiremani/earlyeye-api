from __future__ import annotations
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database import get_db
from app.models.base import User, Child, Scan, Payment, DailyLog
from app.utils.auth import get_current_user

router = APIRouter(prefix="/admin", tags=["Admin"])

@router.get("/stats")
async def admin_stats(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    users = (await db.execute(select(func.count(User.id)))).scalar() or 0
    children_count = (await db.execute(select(func.count(Child.id)))).scalar() or 0
    scans = (await db.execute(select(func.count(Scan.id)))).scalar() or 0
    total_cost = (await db.execute(select(func.sum(Scan.cost_inr)))).scalar() or 0
    revenue = (await db.execute(select(func.sum(Payment.amount)).where(Payment.status == "paid"))).scalar() or 0
    subscribers = (await db.execute(select(func.count(User.id)).where(User.is_subscribed == True))).scalar() or 0

    return {
        "total_users": users,
        "total_children": children_count,
        "total_scans": scans,
        "total_ai_cost_inr": round(total_cost, 2),
        "total_revenue_inr": round((revenue or 0) / 100, 2),
        "active_subscribers": subscribers,
        "gross_margin_pct": round((1 - total_cost / max((revenue or 0) / 100, 1)) * 100, 1) if revenue else 0,
    }

@router.get("/recent-scans")
async def recent_scans(limit: int = 20, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Scan).order_by(Scan.date.desc()).limit(limit))
    scans = result.scalars().all()
    return [{"id": str(s.id), "child_id": str(s.child_id), "date": s.date.isoformat(),
             "severity": s.severity, "model": s.model_used, "tiered": s.tiered,
             "cost": s.cost_inr, "confidence": s.confidence} for s in scans]
