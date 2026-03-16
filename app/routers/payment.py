import hmac, hashlib, json
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.base import User, Payment
from app.utils.auth import get_current_user
from app.config import get_settings
import razorpay

router = APIRouter(prefix="/payment", tags=["Payment"])
settings = get_settings()

def get_razorpay_client():
    return razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))

class CreateOrderRequest(BaseModel):
    type: str  # 'scan_credit' or 'subscription'

@router.post("/create-order")
async def create_order(req: CreateOrderRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if req.type == "scan_credit":
        amount = settings.EXTRA_SCAN_PRICE * 100  # paise
    elif req.type == "subscription":
        amount = settings.PREMIUM_PRICE * 100
    else:
        raise HTTPException(status_code=400, detail="Invalid payment type")

    client = get_razorpay_client()
    order = client.order.create({
        "amount": amount, "currency": "INR",
        "notes": {"user_id": str(user.id), "type": req.type},
    })

    payment = Payment(
        user_id=user.id, razorpay_order_id=order["id"],
        amount=amount, type=req.type, status="created",
    )
    db.add(payment)
    await db.commit()

    return {"order_id": order["id"], "amount": amount, "currency": "INR", "key_id": settings.RAZORPAY_KEY_ID}

class VerifyPaymentRequest(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str

@router.post("/verify")
async def verify_payment(req: VerifyPaymentRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    # Verify signature
    msg = f"{req.razorpay_order_id}|{req.razorpay_payment_id}"
    expected = hmac.new(settings.RAZORPAY_KEY_SECRET.encode(), msg.encode(), hashlib.sha256).hexdigest()
    if expected != req.razorpay_signature:
        raise HTTPException(status_code=400, detail="Invalid signature")

    from sqlalchemy import select
    result = await db.execute(select(Payment).where(Payment.razorpay_order_id == req.razorpay_order_id))
    payment = result.scalar_one_or_none()
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")

    payment.razorpay_payment_id = req.razorpay_payment_id
    payment.razorpay_signature = req.razorpay_signature
    payment.status = "paid"

    # Apply credits
    if payment.type == "scan_credit":
        user.scan_credits += 1
    elif payment.type == "subscription":
        user.is_subscribed = True
        user.subscription_expiry = datetime.utcnow() + timedelta(days=30)

    await db.commit()
    return {"status": "paid", "type": payment.type}

@router.post("/webhook")
async def razorpay_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    body = await request.body()
    signature = request.headers.get("X-Razorpay-Signature", "")
    expected = hmac.new(settings.RAZORPAY_WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
    if expected != signature:
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    data = json.loads(body)
    event = data.get("event", "")

    if event == "payment.captured":
        payment_entity = data["payload"]["payment"]["entity"]
        order_id = payment_entity.get("order_id")
        if order_id:
            from sqlalchemy import select
            result = await db.execute(select(Payment).where(Payment.razorpay_order_id == order_id))
            payment = result.scalar_one_or_none()
            if payment and payment.status != "paid":
                payment.status = "paid"
                payment.razorpay_payment_id = payment_entity.get("id")
                # Apply credits
                user_result = await db.execute(select(User).where(User.id == payment.user_id))
                user = user_result.scalar_one_or_none()
                if user:
                    if payment.type == "scan_credit":
                        user.scan_credits += 1
                    elif payment.type == "subscription":
                        user.is_subscribed = True
                        user.subscription_expiry = datetime.utcnow() + timedelta(days=30)
                await db.commit()

    return {"status": "ok"}
