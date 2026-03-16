from __future__ import annotations
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.base import User, Child, Prescription
from app.utils.auth import get_current_user

router = APIRouter(prefix="/children", tags=["Children"])

class CreateChildRequest(BaseModel):
    name: str
    dob: str
    gender: str = "other"
    screen_time_limit_hours: float = 2.0
    outdoor_goal_hours: float = 2.0

class UpdateChildRequest(BaseModel):
    name: Optional[str] = None
    screen_time_limit_hours: Optional[float] = None
    outdoor_goal_hours: Optional[float] = None

class AddPrescriptionRequest(BaseModel):
    date: str
    right_sph: float = 0
    right_cyl: float = 0
    right_axis: int = 0
    left_sph: float = 0
    left_cyl: float = 0
    left_axis: int = 0
    notes: str = ""

@router.get("/")
async def list_children(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Child).where(Child.user_id == user.id).order_by(Child.created_at))
    children = result.scalars().all()
    return [{"id": str(c.id), "name": c.name, "dob": c.dob, "gender": c.gender,
             "screen_time_limit_hours": c.screen_time_limit_hours, "outdoor_goal_hours": c.outdoor_goal_hours} for c in children]

@router.post("/")
async def create_child(req: CreateChildRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    child = Child(user_id=user.id, name=req.name, dob=req.dob, gender=req.gender,
                  screen_time_limit_hours=req.screen_time_limit_hours, outdoor_goal_hours=req.outdoor_goal_hours)
    db.add(child)
    await db.commit()
    await db.refresh(child)
    return {"id": str(child.id), "name": child.name}

@router.patch("/{child_id}")
async def update_child(child_id: str, req: UpdateChildRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Child).where(Child.id == child_id, Child.user_id == user.id))
    child = result.scalar_one_or_none()
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")
    if req.name is not None: child.name = req.name
    if req.screen_time_limit_hours is not None: child.screen_time_limit_hours = req.screen_time_limit_hours
    if req.outdoor_goal_hours is not None: child.outdoor_goal_hours = req.outdoor_goal_hours
    await db.commit()
    return {"message": "Updated"}

@router.delete("/{child_id}")
async def delete_child(child_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Child).where(Child.id == child_id, Child.user_id == user.id))
    child = result.scalar_one_or_none()
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")
    await db.delete(child)
    await db.commit()
    return {"message": "Deleted"}

@router.get("/{child_id}/prescriptions")
async def list_prescriptions(child_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Prescription).where(Prescription.child_id == child_id).order_by(Prescription.date.desc()))
    rxs = result.scalars().all()
    return [{"id": str(r.id), "date": r.date, "right_sph": r.right_sph, "right_cyl": r.right_cyl,
             "right_axis": r.right_axis, "left_sph": r.left_sph, "left_cyl": r.left_cyl,
             "left_axis": r.left_axis, "notes": r.notes} for r in rxs]

@router.post("/{child_id}/prescriptions")
async def add_prescription(child_id: str, req: AddPrescriptionRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    rx = Prescription(child_id=child_id, date=req.date, right_sph=req.right_sph, right_cyl=req.right_cyl,
                      right_axis=req.right_axis, left_sph=req.left_sph, left_cyl=req.left_cyl,
                      left_axis=req.left_axis, notes=req.notes)
    db.add(rx)
    await db.commit()
    await db.refresh(rx)
    return {"id": str(rx.id)}

@router.delete("/{child_id}/prescriptions/{rx_id}")
async def delete_prescription(child_id: str, rx_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Prescription).where(Prescription.id == rx_id, Prescription.child_id == child_id))
    rx = result.scalar_one_or_none()
    if not rx:
        raise HTTPException(status_code=404, detail="Prescription not found")
    await db.delete(rx)
    await db.commit()
    return {"message": "Prescription deleted"}
