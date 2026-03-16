import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.config import get_settings
from app.database import engine, Base
from app.routers import auth, children, scan, payment, logs, admin
from app.routers import risk_quiz, vision_test, notifications, score, report

settings = get_settings()

app = FastAPI(
    title="EarlyEye API",
    description="Pediatric eye screening backend — AI-powered Brückner test",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static file serving for scan images
storage_path = settings.STORAGE_PATH
os.makedirs(os.path.join(storage_path, "scans"), exist_ok=True)
os.makedirs(os.path.join(storage_path, "reports"), exist_ok=True)
app.mount("/files", StaticFiles(directory=storage_path), name="files")

# Routers
app.include_router(auth.router)
app.include_router(children.router)
app.include_router(scan.router)
app.include_router(payment.router)
app.include_router(logs.router)
app.include_router(admin.router)
app.include_router(risk_quiz.router)
app.include_router(vision_test.router)
app.include_router(notifications.router)
app.include_router(score.router)
app.include_router(report.router)

@app.on_event("startup")
async def startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

@app.get("/")
async def root():
    return {"app": "EarlyEye API", "version": "1.0.0", "status": "running"}

@app.get("/health")
async def health():
    return {"status": "ok"}
