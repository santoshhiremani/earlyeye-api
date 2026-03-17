import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Boolean, Integer, Float, Text, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.database import Base

class User(Base):
    __tablename__ = "users"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    phone = Column(String(15), unique=True, nullable=False, index=True)
    name = Column(String(100), default="")
    is_subscribed = Column(Boolean, default=False)
    subscription_expiry = Column(DateTime, nullable=True)
    scan_credits = Column(Integer, default=0)
    weekly_scans_used = Column(Integer, default=0)
    week_start_date = Column(String(10), default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    children = relationship("Child", back_populates="user", cascade="all, delete-orphan")
    payments = relationship("Payment", back_populates="user", cascade="all, delete-orphan")

class Child(Base):
    __tablename__ = "children"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    dob = Column(String(10), nullable=False)
    gender = Column(String(10), default="other")
    screen_time_limit_hours = Column(Float, default=2.0)
    outdoor_goal_hours = Column(Float, default=2.0)
    created_at = Column(DateTime, default=datetime.utcnow)
    user = relationship("User", back_populates="children")
    prescriptions = relationship("Prescription", back_populates="child", cascade="all, delete-orphan")
    scans = relationship("Scan", back_populates="child", cascade="all, delete-orphan")
    daily_logs = relationship("DailyLog", back_populates="child", cascade="all, delete-orphan")
    risk_results = relationship("RiskResult", back_populates="child", cascade="all, delete-orphan")
    vision_results = relationship("VisionResult", back_populates="child", cascade="all, delete-orphan")

class Prescription(Base):
    __tablename__ = "prescriptions"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    child_id = Column(UUID(as_uuid=True), ForeignKey("children.id"), nullable=False, index=True)
    date = Column(String(10), nullable=False)
    right_sph = Column(Float, default=0)
    right_cyl = Column(Float, default=0)
    right_axis = Column(Integer, default=0)
    left_sph = Column(Float, default=0)
    left_cyl = Column(Float, default=0)
    left_axis = Column(Integer, default=0)
    notes = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    child = relationship("Child", back_populates="prescriptions")

class Scan(Base):
    __tablename__ = "scans"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    child_id = Column(UUID(as_uuid=True), ForeignKey("children.id"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    date = Column(DateTime, default=datetime.utcnow)
    severity = Column(String(10), default="normal")
    headline = Column(Text, default="")
    conditions = Column(JSON, default=list)
    findings = Column(JSON, default=list)
    recommendation = Column(Text, default="")
    urgency = Column(Text, default="")
    follow_up_timeline = Column(Text, default="")
    confidence = Column(Float, default=0)
    image_quality = Column(String(20), default="")
    refractive_estimate = Column(JSON, nullable=True)
    image_path = Column(Text, default="")
    result_json_path = Column(Text, default="")
    model_used = Column(String(50), default="")
    tiered = Column(Boolean, default=False)
    tier1_severity = Column(String(10), nullable=True)
    cost_inr = Column(Float, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    child = relationship("Child", back_populates="scans")

class DailyLog(Base):
    __tablename__ = "daily_logs"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    child_id = Column(UUID(as_uuid=True), ForeignKey("children.id"), nullable=False, index=True)
    date = Column(String(10), nullable=False)
    screen_minutes = Column(Integer, default=0)
    outdoor_minutes = Column(Integer, default=0)
    eye_breaks_done = Column(Integer, default=0)
    exercises_done = Column(JSON, default=list)  # [{"id": "20_20_20", "title": "20-20-20 Rule", "completed_at": "..."}]
    app_usage = Column(JSON, default=list)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    child = relationship("Child", back_populates="daily_logs")

class Payment(Base):
    __tablename__ = "payments"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    razorpay_order_id = Column(String(50), nullable=True, index=True)
    razorpay_payment_id = Column(String(50), nullable=True)
    razorpay_signature = Column(String(200), nullable=True)
    amount = Column(Integer, nullable=False)
    currency = Column(String(3), default="INR")
    type = Column(String(20), nullable=False)
    status = Column(String(20), default="created")
    created_at = Column(DateTime, default=datetime.utcnow)
    user = relationship("User", back_populates="payments")

class OTPStore(Base):
    __tablename__ = "otp_store"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    phone = Column(String(15), nullable=False, index=True)
    otp = Column(String(6), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    verified = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class RiskResult(Base):
    __tablename__ = "risk_results"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    child_id = Column(UUID(as_uuid=True), ForeignKey("children.id"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    date = Column(String(10), nullable=False)
    level = Column(String(10), default="low")  # low, moderate, high
    score = Column(Integer, default=0)
    factors = Column(JSON, default=list)
    recommendation = Column(Text, default="")
    answers = Column(JSON, default=dict)  # raw quiz answers
    created_at = Column(DateTime, default=datetime.utcnow)
    child = relationship("Child", back_populates="risk_results")

class VisionResult(Base):
    __tablename__ = "vision_results"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    child_id = Column(UUID(as_uuid=True), ForeignKey("children.id"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    date = Column(String(10), nullable=False)
    optotype_mode = Column(String(20), default="lea")  # lea, tumbling_e
    right_eye = Column(JSON, nullable=True)   # {pass, correctAnswers, totalQuestions, lowestLinePassed}
    left_eye = Column(JSON, nullable=True)
    overall_pass = Column(String(15), default="inconclusive")  # pass, fail, inconclusive
    recommendation = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    child = relationship("Child", back_populates="vision_results")

class PushToken(Base):
    __tablename__ = "push_tokens"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    token = Column(String(200), nullable=False, unique=True)
    platform = Column(String(10), default="android")  # android, ios
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)