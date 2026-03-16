import os, json, base64, uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
import httpx
from app.database import get_db
from app.models.base import User, Child, Scan
from app.utils.auth import get_current_user
from app.config import get_settings

router = APIRouter(prefix="/scan", tags=["Scan"])
settings = get_settings()

def get_week_start():
    from datetime import date
    today = date.today()
    monday = today - __import__('datetime').timedelta(days=today.weekday())
    return monday.isoformat()

async def call_claude(model: str, image_b64: str, prompt: str, max_tokens: int = 1200):
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post("https://api.anthropic.com/v1/messages", headers={
            "Content-Type": "application/json",
            "x-api-key": settings.ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
        }, json={
            "model": model, "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": image_b64}},
                {"type": "text", "text": prompt},
            ]}],
        })
        if resp.status_code != 200:
            raise HTTPException(status_code=502, detail=f"AI API error: {resp.status_code}")
        data = resp.json()
        return data["content"][0]["text"]

@router.post("/precheck")
async def precheck(image: UploadFile = File(...), user: User = Depends(get_current_user)):
    img_bytes = await image.read()
    b64 = base64.b64encode(img_bytes).decode()
    prompt = 'Is this a close-up photo of a child\'s open eyes in a dark room with flash? Answer JSON: {"is_valid": true/false, "reason": "..."}'
    result = await call_claude(settings.MODEL_PRECHECK, b64, prompt, 200)
    return {"result": json.loads(result.replace("```json", "").replace("```", "").strip())}

@router.post("/analyze")
async def analyze(
    child_id: str = Form(...),
    prompt: str = Form(...),
    image: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Check scan limits
    week_start = get_week_start()
    if user.week_start_date != week_start:
        user.weekly_scans_used = 0
        user.week_start_date = week_start

    limit = settings.PREMIUM_WEEKLY_SCANS if user.is_subscribed else settings.FREE_WEEKLY_SCANS
    if user.weekly_scans_used >= limit and user.scan_credits <= 0:
        raise HTTPException(status_code=402, detail="Scan limit reached. Buy credits or upgrade.")

    # Verify child belongs to user
    child_result = await db.execute(select(Child).where(Child.id == child_id, Child.user_id == user.id))
    child = child_result.scalar_one_or_none()
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")

    # Read and encode image
    img_bytes = await image.read()
    b64 = base64.b64encode(img_bytes).decode()

    # Save image to disk
    scan_dir = os.path.join(settings.STORAGE_PATH, "scans", str(child_id))
    os.makedirs(scan_dir, exist_ok=True)
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    img_filename = f"{timestamp}_{uuid.uuid4().hex[:8]}.jpg"
    img_path = os.path.join(scan_dir, img_filename)
    with open(img_path, "wb") as f:
        f.write(img_bytes)

    # Tier 1: Haiku 4.5
    tier1_raw = await call_claude(settings.MODEL_TIER1, b64, prompt, 1200)
    tier1_text = tier1_raw.replace("```json", "").replace("```", "").strip()

    severity = "normal"
    cost = 0.64  # Haiku cost in INR
    model_used = settings.MODEL_TIER1
    tiered = False
    tier1_severity = None
    result_text = tier1_text

    try:
        parsed = json.loads(tier1_text)
        severity = parsed.get("severity", "normal")
    except:
        severity = "refer"

    # Tier 2: Sonnet if flagged
    if severity in ("refer", "urgent"):
        tier1_severity = severity
        tier2_raw = await call_claude(settings.MODEL_TIER2, b64, prompt, 1200)
        result_text = tier2_raw.replace("```json", "").replace("```", "").strip()
        cost += 1.84
        model_used = settings.MODEL_TIER2
        tiered = True

    # Parse final result
    try:
        result = json.loads(result_text)
    except:
        result = {"severity": "refer", "headline": "Could not parse AI response", "conditions": [], "findings": []}

    # Save JSON to disk
    json_filename = f"{timestamp}_{uuid.uuid4().hex[:8]}.json"
    json_path = os.path.join(scan_dir, json_filename)
    with open(json_path, "w") as f:
        json.dump(result, f, indent=2)

    # Save to database
    scan = Scan(
        child_id=child_id, user_id=user.id,
        severity=result.get("severity", "normal"),
        headline=result.get("headline", ""),
        conditions=result.get("conditions", []),
        findings=result.get("findings", []),
        recommendation=result.get("recommendation", ""),
        urgency=result.get("urgency", ""),
        follow_up_timeline=result.get("followUpTimeline", ""),
        confidence=result.get("confidence", 0),
        image_quality=result.get("imageQuality", ""),
        refractive_estimate=result.get("refractiveEstimate"),
        image_path=img_path,
        result_json_path=json_path,
        model_used=model_used, tiered=tiered, tier1_severity=tier1_severity,
        cost_inr=cost,
    )
    db.add(scan)

    # Deduct scan credit
    if user.weekly_scans_used < limit:
        user.weekly_scans_used += 1
    else:
        user.scan_credits -= 1

    await db.commit()
    await db.refresh(scan)

    return {
        "scan_id": str(scan.id),
        "result": result,
        "model": model_used,
        "tiered": tiered,
        "cost_inr": cost,
        "image_url": f"{settings.DOMAIN}/files/scans/{child_id}/{img_filename}",
    }

@router.get("/history/{child_id}")
async def scan_history(child_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Scan).where(Scan.child_id == child_id, Scan.user_id == user.id).order_by(Scan.date.desc()).limit(50)
    )
    scans = result.scalars().all()
    return [{
        "id": str(s.id), "date": s.date.isoformat(), "severity": s.severity,
        "headline": s.headline, "conditions": s.conditions, "confidence": s.confidence,
        "image_quality": s.image_quality, "model_used": s.model_used, "tiered": s.tiered,
        "cost_inr": s.cost_inr,
        "image_url": f"{settings.DOMAIN}/files/scans/{child_id}/{os.path.basename(s.image_path)}" if s.image_path else None,
    } for s in scans]

@router.get("/stats")
async def scan_stats(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    total = await db.execute(select(func.count(Scan.id)).where(Scan.user_id == user.id))
    cost = await db.execute(select(func.sum(Scan.cost_inr)).where(Scan.user_id == user.id))
    return {
        "total_scans": total.scalar() or 0,
        "total_cost_inr": round(cost.scalar() or 0, 2),
        "weekly_scans_used": user.weekly_scans_used,
        "weekly_limit": settings.PREMIUM_WEEKLY_SCANS if user.is_subscribed else settings.FREE_WEEKLY_SCANS,
        "scan_credits": user.scan_credits,
    }
