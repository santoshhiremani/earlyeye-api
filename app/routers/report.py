from __future__ import annotations
import os
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.base import User, Child, Scan
from app.utils.auth import get_current_user
from app.config import get_settings

router = APIRouter(prefix="/report", tags=["Reports"])
settings = get_settings()

def generate_report_html(child, scan, image_url):
    sev_color = {"urgent": "#EF4444", "refer": "#F59E0B", "normal": "#10B981"}.get(scan.severity, "#6B7280")
    sev_label = {"urgent": "URGENT", "refer": "REFER", "normal": "NORMAL"}.get(scan.severity, "UNKNOWN")

    conditions_html = ""
    detected = [c for c in (scan.conditions or []) if c.get("present")]
    clear = [c for c in (scan.conditions or []) if not c.get("present")]

    for c in detected:
        cc = {"severe": "#EF4444", "moderate": "#F59E0B", "mild": "#3B82F6"}.get(c.get("severity", ""), "#6B7280")
        conditions_html += f'<tr><td style="padding:6px 10px;border-bottom:1px solid #E5E7EB;">● {c["name"]}</td><td style="padding:6px 10px;border-bottom:1px solid #E5E7EB;text-align:center;"><span style="background:{cc}20;color:{cc};padding:2px 8px;border-radius:10px;font-size:11px;font-weight:600;">{c.get("severity","").upper()}</span></td><td style="padding:6px 10px;border-bottom:1px solid #E5E7EB;color:#6B7280;font-size:11px;">{c.get("description","Detected")}</td></tr>'

    for c in clear:
        conditions_html += f'<tr><td style="padding:6px 10px;border-bottom:1px solid #E5E7EB;color:#9CA3AF;">○ {c["name"]}</td><td style="padding:6px 10px;border-bottom:1px solid #E5E7EB;text-align:center;"><span style="background:#F3F4F6;color:#9CA3AF;padding:2px 8px;border-radius:10px;font-size:11px;">Clear</span></td><td style="padding:6px 10px;border-bottom:1px solid #E5E7EB;color:#9CA3AF;font-size:11px;">Not detected</td></tr>'

    findings_html = "".join(f"<li>{f}</li>" for f in (scan.findings or []))

    return f'''<!DOCTYPE html><html><head><meta charset="utf-8"><style>
    *{{margin:0;padding:0;box-sizing:border-box}}body{{font-family:Helvetica,Arial,sans-serif;color:#1F2937;line-height:1.5;padding:24px}}
    .hdr{{display:flex;justify-content:space-between;padding-bottom:16px;border-bottom:2px solid #0D7377;margin-bottom:20px}}
    .logo{{font-size:22px;font-weight:800;color:#0D7377}}.logo span{{color:#FF8C42}}
    table{{width:100%;border-collapse:collapse;font-size:12px;margin:12px 0}}
    th{{background:#F3F4F6;padding:8px 10px;text-align:left;font-size:11px;color:#6B7280;border-bottom:2px solid #E5E7EB}}
    .disclaimer{{background:#F3F4F6;border-radius:8px;padding:12px;margin-top:20px;font-size:9px;color:#9CA3AF}}
    </style></head><body>
    <div class="hdr"><div><div class="logo">Early<span>Eye</span></div><div style="font-size:11px;color:#6B7280;">Brückner Red Reflex Test — AI Analysis Report</div></div>
    <div style="text-align:right;font-size:10px;color:#9CA3AF;">Report ID: EE-{str(scan.id)[:8].upper()}<br>{scan.date.strftime("%d %b %Y, %H:%M")}</div></div>
    <div style="padding:14px 18px;border-radius:8px;background:{sev_color}10;border:1px solid {sev_color}30;margin-bottom:20px;">
    <span style="font-size:14px;font-weight:700;color:{sev_color};">{sev_label}</span> — <span style="color:#6B7280;">{scan.headline}</span></div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px 24px;padding:14px;background:#F9FAFB;border-radius:8px;border:1px solid #E5E7EB;margin-bottom:16px;">
    <div><div style="font-size:10px;color:#9CA3AF;">CHILD NAME</div><div style="font-size:13px;font-weight:600;">{child.name}</div></div>
    <div><div style="font-size:10px;color:#9CA3AF;">DATE OF BIRTH</div><div style="font-size:13px;font-weight:600;">{child.dob}</div></div>
    <div><div style="font-size:10px;color:#9CA3AF;">GENDER</div><div style="font-size:13px;font-weight:600;">{child.gender}</div></div>
    <div><div style="font-size:10px;color:#9CA3AF;">CONFIDENCE</div><div style="font-size:13px;font-weight:600;">{scan.confidence}%</div></div></div>
    {f'<div style="text-align:center;margin-bottom:16px;"><img src="{image_url}" style="width:240px;height:240px;object-fit:cover;border-radius:12px;border:2px solid #E5E7EB;"/></div>' if image_url else ''}
    {f'<h3 style="font-size:14px;color:#0D7377;margin:16px 0 8px;">Key Findings</h3><ul style="list-style:none;padding:0;">{findings_html}</ul>' if findings_html else ''}
    <h3 style="font-size:14px;color:#0D7377;margin:16px 0 8px;">Conditions Screened</h3>
    <table><thead><tr><th>Condition</th><th>Severity</th><th>Description</th></tr></thead><tbody>{conditions_html}</tbody></table>
    <div style="background:#FFF7ED;border:1px solid #FFEDD5;border-left:4px solid #FF8C42;border-radius:8px;padding:14px;margin:16px 0;">
    <div style="font-size:12px;font-weight:700;color:#FF8C42;margin-bottom:4px;">Doctor Recommendation</div>
    <div style="font-size:12px;color:#92400E;">{scan.recommendation or 'Share this report with a pediatric ophthalmologist.'}</div></div>
    <div class="disclaimer"><strong>Medical Disclaimer:</strong> EarlyEye is an AI screening tool and does not constitute a medical diagnosis. All findings should be confirmed by a qualified ophthalmologist.</div>
    <div style="margin-top:16px;padding-top:12px;border-top:1px solid #E5E7EB;font-size:9px;color:#9CA3AF;display:flex;justify-content:space-between;">
    <span>EarlyEye v1.0.0</span><span>Made in India</span></div></body></html>'''

@router.get("/scan/{scan_id}")
async def get_scan_report(scan_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Scan).where(Scan.id == scan_id, Scan.user_id == user.id))
    scan = result.scalar_one_or_none()
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")

    child_result = await db.execute(select(Child).where(Child.id == scan.child_id))
    child = child_result.scalar_one_or_none()
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")

    image_url = None
    if scan.image_path:
        filename = os.path.basename(scan.image_path)
        image_url = f"{settings.DOMAIN}/files/scans/{scan.child_id}/{filename}"

    html = generate_report_html(child, scan, image_url)

    # Save HTML report
    report_dir = os.path.join(settings.STORAGE_PATH, "reports")
    os.makedirs(report_dir, exist_ok=True)
    report_path = os.path.join(report_dir, f"report_{scan_id}.html")
    with open(report_path, "w") as f:
        f.write(html)

    return FileResponse(report_path, media_type="text/html", filename=f"EarlyEye_Report_{child.name}_{scan.date.strftime('%Y%m%d')}.html")

@router.get("/scan/{scan_id}/json")
async def get_scan_report_data(scan_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Scan).where(Scan.id == scan_id, Scan.user_id == user.id))
    scan = result.scalar_one_or_none()
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")

    child_result = await db.execute(select(Child).where(Child.id == scan.child_id))
    child = child_result.scalar_one_or_none()

    return {
        "scan_id": str(scan.id), "date": scan.date.isoformat(),
        "child_name": child.name if child else "", "child_dob": child.dob if child else "",
        "severity": scan.severity, "headline": scan.headline,
        "conditions": scan.conditions, "findings": scan.findings,
        "recommendation": scan.recommendation, "confidence": scan.confidence,
        "image_quality": scan.image_quality, "model_used": scan.model_used,
        "cost_inr": scan.cost_inr,
    }
