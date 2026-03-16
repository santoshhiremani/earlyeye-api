from __future__ import annotations
import os, json, base64, uuid, hashlib
from datetime import datetime, date, timedelta
from io import BytesIO
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
import httpx
from app.database import get_db
from app.models.base import User, Child, Scan
from app.utils.auth import get_current_user
from app.config import get_settings

router = APIRouter(prefix="/scan", tags=["Scan"])
settings = get_settings()

# ─── Helpers ──────────────────────────────────────────────────────────────────

def get_week_start():
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    return monday.isoformat()

async def call_claude(model: str, image_b64: str, prompt: str, max_tokens: int = 1200) -> str:
    async with httpx.AsyncClient(timeout=90) as client:
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
            error_text = resp.text
            raise HTTPException(status_code=502, detail=f"AI API error {resp.status_code}: {error_text[:200]}")
        data = resp.json()
        return data["content"][0]["text"]

def compress_image(img_bytes: bytes, max_size: int = 800, quality: int = 70) -> bytes:
    """Compress image for AI analysis — reduces token cost"""
    try:
        from PIL import Image as PILImage
        img = PILImage.open(BytesIO(img_bytes))
        # Resize if larger than max_size
        w, h = img.size
        if max(w, h) > max_size:
            ratio = max_size / max(w, h)
            img = img.resize((int(w * ratio), int(h * ratio)), PILImage.LANCZOS)
        # Compress
        buf = BytesIO()
        img.save(buf, format='JPEG', quality=quality, optimize=True)
        return buf.getvalue()
    except ImportError:
        return img_bytes  # PIL not installed, use original

def save_file(directory: str, filename: str, data: bytes | str, mode: str = "wb"):
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, filename)
    with open(path, mode) as f:
        f.write(data if isinstance(data, bytes) else data.encode() if mode == "wb" else data)
    return path

def parse_ai_response(text: str) -> dict:
    """Safely parse AI JSON response"""
    clean = text.replace("```json", "").replace("```", "").strip()
    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        return {"severity": "refer", "headline": "Could not parse AI response", "conditions": [], "findings": []}

# ─── Brückner Analysis Prompt (14 conditions) ────────────────────────────────

BRUCKNER_PROMPT = """Analyze this Brückner red reflex test photo. Examine the color, brightness, symmetry, and shape of the red reflex in both eyes.

Screen for these 14 conditions and respond ONLY with a JSON object:

HIGH RELIABILITY (active screening):
1. Leukocoria — white/grey pupil glow
2. Absent Red Reflex — dark/black pupil, no glow
3. Iris Heterochromia — different iris colors between eyes
4. Ptosis — eyelid drooping over pupil
5. Head Tilt — tilted head position
6. Aniridia — very large pupil, minimal iris

MODERATE RELIABILITY (active screening):
7. Reflex Asymmetry — brightness difference between eyes
8. Coloboma — keyhole/notched pupil shape
9. Corneal Opacity — white/cloudy area on corneal surface
10. Media Opacity — hazy/cloudy reflex texture

INFORMATIONAL (report but don't flag as urgent):
11. Crescent Shadow — dark arc at pupil edge
12. Eyelid Abnormality — swelling, crusting, asymmetry
13. Color Abnormality — dull/greenish/yellow reflex tint
14. Pupil Irregularity — non-circular pupil shape

Respond with this exact JSON structure:
{
  "severity": "normal" | "refer" | "urgent",
  "headline": "Brief one-line summary",
  "findings": ["Finding 1", "Finding 2"],
  "conditions": [
    {"name": "Leukocoria", "present": false, "severity": "normal", "description": "Not detected"},
    ...for all 14 conditions
  ],
  "recommendation": "What the parent should do next",
  "urgency": "Timeline description",
  "followUpTimeline": "When to follow up",
  "confidence": 85,
  "imageQuality": "good" | "acceptable" | "poor",
  "refractiveEstimate": {
    "available": false,
    "right": {"sph": "N/A", "cyl": "N/A", "axis": "N/A"},
    "left": {"sph": "N/A", "cyl": "N/A", "axis": "N/A"},
    "interpretation": "Refractive estimate not available from this image"
  }
}"""

PRECHECK_PROMPT = """Look at this photo. Answer ONLY with a JSON object:
{
  "is_eye_photo": true/false,
  "eyes_open": true/false,
  "both_eyes_visible": true/false,
  "child_face": true/false,
  "dark_room": true/false,
  "flash_visible": true/false,
  "is_valid": true/false,
  "reason": "string explaining why valid or not"
}"""

# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/precheck")
async def precheck(image: UploadFile = File(...), user: User = Depends(get_current_user)):
    """Eye photo validation using Haiku 3 — cost: ₹0.06"""
    img_bytes = await image.read()
    # Compress heavily for precheck (just need to see if it's an eye)
    compressed = compress_image(img_bytes, max_size=400, quality=50)
    b64 = base64.b64encode(compressed).decode()

    result_text = await call_claude(settings.MODEL_PRECHECK, b64, PRECHECK_PROMPT, 200)
    result = parse_ai_response(result_text)
    return {"result": result, "model": settings.MODEL_PRECHECK}

@router.post("/analyze")
async def analyze(
    child_id: str = Form(...),
    image: UploadFile = File(...),
    prompt: str = Form(None),  # Optional custom prompt, defaults to BRUCKNER_PROMPT
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Two-tier Brückner scan: Haiku 4.5 → Sonnet 4.6 if flagged.
    Saves original image, compressed image, and full JSON result to VPS."""

    # ── 1. Check scan limits ──────────────────────────────────────────────
    week_start = get_week_start()
    if user.week_start_date != week_start:
        user.weekly_scans_used = 0
        user.week_start_date = week_start

    limit = settings.PREMIUM_WEEKLY_SCANS if user.is_subscribed else settings.FREE_WEEKLY_SCANS
    if user.weekly_scans_used >= limit and user.scan_credits <= 0:
        raise HTTPException(status_code=402, detail="Scan limit reached. Buy credits or upgrade to premium.")

    # ── 2. Verify child belongs to user ───────────────────────────────────
    child_result = await db.execute(select(Child).where(Child.id == child_id, Child.user_id == user.id))
    child = child_result.scalar_one_or_none()
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")

    # ── 3. Read image ─────────────────────────────────────────────────────
    img_bytes = await image.read()
    img_hash = hashlib.md5(img_bytes).hexdigest()[:8]
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    scan_id_short = uuid.uuid4().hex[:8]

    # ── 4. Save original image to disk ────────────────────────────────────
    scan_dir = os.path.join(settings.STORAGE_PATH, "scans", str(child_id))
    original_filename = f"{timestamp}_{scan_id_short}_original.jpg"
    original_path = save_file(scan_dir, original_filename, img_bytes)

    # ── 5. Compress for AI analysis (saves ~50% tokens) ───────────────────
    compressed = compress_image(img_bytes, max_size=800, quality=70)
    compressed_filename = f"{timestamp}_{scan_id_short}_compressed.jpg"
    compressed_path = save_file(scan_dir, compressed_filename, compressed)
    b64 = base64.b64encode(compressed).decode()

    # ── 6. Tier 1: Haiku 4.5 screening ───────────────────────────────────
    analysis_prompt = prompt or BRUCKNER_PROMPT
    tier1_raw = await call_claude(settings.MODEL_TIER1, b64, analysis_prompt, 1500)
    tier1_result = parse_ai_response(tier1_raw)

    severity = tier1_result.get("severity", "normal")
    cost = 0.64  # Haiku 4.5 cost in INR
    model_used = settings.MODEL_TIER1
    tiered = False
    tier1_severity = None
    final_result = tier1_result

    # ── 7. Tier 2: Sonnet 4.6 if flagged ─────────────────────────────────
    if severity in ("refer", "urgent"):
        tier1_severity = severity
        tier2_raw = await call_claude(settings.MODEL_TIER2, b64, analysis_prompt, 1500)
        final_result = parse_ai_response(tier2_raw)
        cost += 1.84  # Sonnet 4.6 cost in INR
        model_used = settings.MODEL_TIER2
        tiered = True

    # ── 8. Save complete JSON result to disk ──────────────────────────────
    result_envelope = {
        "scan_metadata": {
            "timestamp": datetime.utcnow().isoformat(),
            "child_id": str(child_id),
            "child_name": child.name,
            "user_id": str(user.id),
            "model_tier1": settings.MODEL_TIER1,
            "model_tier2": settings.MODEL_TIER2 if tiered else None,
            "model_used": model_used,
            "tiered": tiered,
            "tier1_severity": tier1_severity,
            "cost_inr": cost,
            "original_image": original_filename,
            "compressed_image": compressed_filename,
            "image_hash": img_hash,
            "original_size_bytes": len(img_bytes),
            "compressed_size_bytes": len(compressed),
        },
        "tier1_raw": tier1_result if tiered else None,
        "final_result": final_result,
    }
    json_filename = f"{timestamp}_{scan_id_short}_result.json"
    json_path = os.path.join(scan_dir, json_filename)
    with open(json_path, "w") as f:
        json.dump(result_envelope, f, indent=2, default=str)

    # ── 9. Save to database ───────────────────────────────────────────────
    scan = Scan(
        child_id=child_id, user_id=user.id,
        severity=final_result.get("severity", "normal"),
        headline=final_result.get("headline", ""),
        conditions=final_result.get("conditions", []),
        findings=final_result.get("findings", []),
        recommendation=final_result.get("recommendation", ""),
        urgency=final_result.get("urgency", ""),
        follow_up_timeline=final_result.get("followUpTimeline", ""),
        confidence=final_result.get("confidence", 0),
        image_quality=final_result.get("imageQuality", ""),
        refractive_estimate=final_result.get("refractiveEstimate"),
        image_path=original_path,
        result_json_path=json_path,
        model_used=model_used, tiered=tiered, tier1_severity=tier1_severity,
        cost_inr=cost,
    )
    db.add(scan)

    # ── 10. Deduct scan credit ────────────────────────────────────────────
    if user.weekly_scans_used < limit:
        user.weekly_scans_used += 1
    else:
        user.scan_credits -= 1

    await db.commit()
    await db.refresh(scan)

    # ── 11. Return result ─────────────────────────────────────────────────
    return {
        "scan_id": str(scan.id),
        "result": final_result,
        "model": model_used,
        "tiered": tiered,
        "tier1_severity": tier1_severity,
        "cost_inr": cost,
        "image_url": f"{settings.DOMAIN}/files/scans/{child_id}/{original_filename}",
        "files": {
            "original": original_filename,
            "compressed": compressed_filename,
            "result_json": json_filename,
        },
    }

@router.get("/history/{child_id}")
async def scan_history(child_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Get scan timeline for a child — last 50 scans"""
    result = await db.execute(
        select(Scan).where(Scan.child_id == child_id, Scan.user_id == user.id).order_by(Scan.date.desc()).limit(50)
    )
    scans = result.scalars().all()
    return [{
        "id": str(s.id), "date": s.date.isoformat(), "severity": s.severity,
        "headline": s.headline, "conditions": s.conditions, "findings": s.findings,
        "recommendation": s.recommendation, "confidence": s.confidence,
        "image_quality": s.image_quality, "model_used": s.model_used, "tiered": s.tiered,
        "cost_inr": s.cost_inr,
        "image_url": f"{settings.DOMAIN}/files/scans/{child_id}/{os.path.basename(s.image_path)}" if s.image_path else None,
    } for s in scans]

@router.get("/stats")
async def scan_stats(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Get scan usage stats for the current user"""
    total = await db.execute(select(func.count(Scan.id)).where(Scan.user_id == user.id))
    cost = await db.execute(select(func.sum(Scan.cost_inr)).where(Scan.user_id == user.id))
    return {
        "total_scans": total.scalar() or 0,
        "total_cost_inr": round(cost.scalar() or 0, 2),
        "weekly_scans_used": user.weekly_scans_used,
        "weekly_limit": settings.PREMIUM_WEEKLY_SCANS if user.is_subscribed else settings.FREE_WEEKLY_SCANS,
        "scan_credits": user.scan_credits,
    }

@router.get("/{scan_id}/image")
async def get_scan_image(scan_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Get the original scan image"""
    result = await db.execute(select(Scan).where(Scan.id == scan_id, Scan.user_id == user.id))
    scan = result.scalar_one_or_none()
    if not scan or not scan.image_path or not os.path.exists(scan.image_path):
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(scan.image_path, media_type="image/jpeg")

@router.get("/{scan_id}/json")
async def get_scan_json(scan_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Get the full JSON result file for a scan"""
    result = await db.execute(select(Scan).where(Scan.id == scan_id, Scan.user_id == user.id))
    scan = result.scalar_one_or_none()
    if not scan or not scan.result_json_path or not os.path.exists(scan.result_json_path):
        raise HTTPException(status_code=404, detail="Result not found")
    with open(scan.result_json_path) as f:
        return json.load(f)