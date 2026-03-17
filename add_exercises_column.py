#!/usr/bin/env python3
"""Add exercises_done column to daily_logs table"""
import asyncio
import sys
sys.path.insert(0, '.')

from app.config import get_settings
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text

async def migrate():
    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as db:
        try:
            await db.execute(text("ALTER TABLE daily_logs ADD COLUMN exercises_done JSONB DEFAULT '[]'"))
            await db.commit()
            print("✅ Added exercises_done column to daily_logs")
        except Exception as e:
            if "already exists" in str(e).lower() or "duplicate" in str(e).lower():
                print("✅ exercises_done column already exists")
            else:
                print(f"❌ Error: {e}")

    await engine.dispose()

asyncio.run(migrate())