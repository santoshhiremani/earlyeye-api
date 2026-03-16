from __future__ import annotations
# app/config.py
from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "postgresql+asyncpg://earlyeye:password@localhost:5432/earlyeye"

    # JWT
    JWT_SECRET: str = "change-me"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 10080  # 7 days

    # Anthropic
    ANTHROPIC_API_KEY: str = ""
    MODEL_PRECHECK: str = "claude-3-haiku-20240307"
    MODEL_TIER1: str = "claude-haiku-4-5-20251001"
    MODEL_TIER2: str = "claude-sonnet-4-6-20250514"

    # Razorpay
    RAZORPAY_KEY_ID: str = ""
    RAZORPAY_KEY_SECRET: str = ""
    RAZORPAY_WEBHOOK_SECRET: str = ""

    # Storage
    STORAGE_PATH: str = "/var/earlyeye"
    DOMAIN: str = "http://localhost:8000"

    # SMS
    MSG91_AUTH_KEY: str = ""
    MSG91_TEMPLATE_ID: str = ""
    MSG91_SENDER_ID: str = "EARLEYE"

    # Scan limits
    FREE_WEEKLY_SCANS: int = 1
    PREMIUM_WEEKLY_SCANS: int = 4
    EXTRA_SCAN_PRICE: int = 49  # INR
    PREMIUM_PRICE: int = 99     # INR/month

    class Config:
        env_file = ".env"
        extra = "ignore"

@lru_cache()
def get_settings():
    return Settings()
