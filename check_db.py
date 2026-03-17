#!/usr/bin/env python3
"""Quick check: verify daily_logs data in DB for a child"""
import asyncio
import sys
sys.path.insert(0, '.')

from app.config import get_settings
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, text

CHILD_ID = "2544bef2-d291-4f4c-a3db-3cfa6dedbe17"

async def check():
    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as db:
        # Check ALL daily logs with detail
        result = await db.execute(text(
            f"SELECT date, screen_minutes, outdoor_minutes, eye_breaks_done, exercises_done, app_usage "
            f"FROM daily_logs WHERE child_id = '{CHILD_ID}' ORDER BY date DESC LIMIT 7"
        ))
        rows = result.fetchall()
        
        if not rows:
            print("❌ No daily_logs found for this child!")
        else:
            print(f"✅ Found {len(rows)} daily log entries:\n")
            print(f"{'Date':<14} {'Screen':<10} {'Outdoor':<10} {'Breaks':<10} {'Exercises':<12} {'Apps'}")
            print("-" * 80)
            for r in rows:
                apps = r[5] if r[5] else []
                exercises = r[4] if r[4] else []
                app_str = ', '.join(f"{a['name']}({a['minutes']}m)" for a in apps) if apps else '-'
                print(f"{r[0]:<14} {r[1] or 0:<10} {r[2] or 0:<10} {r[3] or 0:<10} {len(exercises):<12} {app_str}")
            
            # Show exercise details for today
            today_row = rows[0] if rows else None
            if today_row and today_row[4]:
                print(f"\n  Today's exercises:")
                for e in today_row[4]:
                    print(f"    ✓ {e.get('title', e.get('id', '?'))} at {e.get('completed_at', '?')}")

        # Check scans
        result2 = await db.execute(text(
            f"SELECT created_at, severity, headline FROM scans WHERE child_id = '{CHILD_ID}' ORDER BY created_at DESC LIMIT 5"
        ))
        scans = result2.fetchall()
        print(f"\n✅ Found {len(scans)} scans:")
        for s in scans:
            print(f"  {s[0]} | {s[1]} | {s[2][:50] if s[2] else '-'}")

        # Check risk results
        result3 = await db.execute(text(
            f"SELECT created_at, score, level FROM risk_results WHERE child_id = '{CHILD_ID}' ORDER BY created_at DESC LIMIT 3"
        ))
        risks = result3.fetchall()
        print(f"\n✅ Found {len(risks)} risk results:")
        for r in risks:
            print(f"  {r[0]} | Score: {r[1]} | Level: {r[2]}")

        # Check vision results
        result4 = await db.execute(text(
            f"SELECT created_at, overall_pass FROM vision_results WHERE child_id = '{CHILD_ID}' ORDER BY created_at DESC LIMIT 3"
        ))
        visions = result4.fetchall()
        print(f"\n✅ Found {len(visions)} vision results:")
        for v in visions:
            print(f"  {v[0]} | {v[1]}")

        # Check prescriptions
        result5 = await db.execute(text(
            f"SELECT date, right_sph, right_cyl, right_axis, left_sph, left_cyl, left_axis, notes "
            f"FROM prescriptions WHERE child_id = '{CHILD_ID}' ORDER BY date DESC LIMIT 5"
        ))
        rxs = result5.fetchall()
        print(f"\n✅ Found {len(rxs)} prescriptions:")
        if rxs:
            print(f"{'Date':<14} {'R SPH':<8} {'R CYL':<8} {'R Axis':<8} {'L SPH':<8} {'L CYL':<8} {'L Axis':<8} Notes")
            print("-" * 80)
            for r in rxs:
                print(f"{r[0]:<14} {r[1] or 0:<8} {r[2] or 0:<8} {r[3] or 0:<8} {r[4] or 0:<8} {r[5] or 0:<8} {r[6] or 0:<8} {r[7] or '-'}")

        # Check exercises done
        result6 = await db.execute(text(
            f"SELECT date, exercises_done, eye_breaks_done "
            f"FROM daily_logs WHERE child_id = '{CHILD_ID}' AND exercises_done IS NOT NULL ORDER BY date DESC LIMIT 5"
        ))
        ex_rows = result6.fetchall()
        print(f"\n✅ Exercises logged:")
        if not ex_rows:
            print("  No exercises completed yet")
        for r in ex_rows:
            exercises = r[1] if r[1] else []
            print(f"  {r[0]} | Eye breaks: {r[2]} | Exercises: {len(exercises)}")
            for e in exercises:
                print(f"    - {e.get('title', e.get('id', '?'))} at {e.get('completed_at', '?')}")

    await engine.dispose()

asyncio.run(check())
