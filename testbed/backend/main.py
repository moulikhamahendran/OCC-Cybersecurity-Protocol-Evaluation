import os
from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


APP_VERSION = "0.1.0"

app = FastAPI(
    title="OCC Cybersecurity Testbed API",
    description="Backend API for telemetry, experiments, KPIs and security events.",
    version=APP_VERSION,
)

default_origins = [
    "http://localhost:3000",
    "http://localhost:5173",
]

allowed_origins = [
    origin.strip()
    for origin in os.getenv(
        "OCC_CORS_ORIGINS",
        ",".join(default_origins),
    ).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root() -> dict[str, str]:
    return {
        "service": "OCC Cybersecurity Testbed API",
        "version": APP_VERSION,
        "documentation": "/docs",
    }


@app.get("/api/v1/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "occ-backend",
        "version": APP_VERSION,
        "timestamp_utc": datetime.now(UTC).isoformat(),
    }
