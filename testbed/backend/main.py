import os
from datetime import UTC, datetime

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .live_state import live_vehicle_store
from .results import (
    load_mqtt_qualification_bundle,
    load_mqtt_qualification_repeats,
    mqtt_qualification_status,
)


APP_VERSION = "0.3.0"

app = FastAPI(
    title="OCC Cybersecurity Testbed API",
    description=(
        "Backend API for telemetry, experiments, "
        "KPIs and security events."
    ),
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


@app.get("/api/v1/vehicles")
def vehicles_endpoint() -> dict:
    return live_vehicle_store.snapshot()


@app.get("/api/v1/vehicles/{vehicle_id}")
def vehicle_endpoint(
    vehicle_id: str,
) -> dict:

    vehicle = live_vehicle_store.get(
        vehicle_id
    )

    if vehicle is None:
        raise HTTPException(
            status_code=404,
            detail="vehicle not found",
        )

    return vehicle


@app.get(
    "/api/v1/benchmark/mqtt/qualification/status"
)
def mqtt_qualification_status_endpoint() -> dict:
    return mqtt_qualification_status()


@app.get(
    "/api/v1/benchmark/mqtt/qualification"
)
def mqtt_qualification_endpoint() -> dict:
    try:
        return load_mqtt_qualification_bundle()
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc


@app.get(
    "/api/v1/benchmark/mqtt/qualification/repeats"
)
def mqtt_qualification_repeats_endpoint() -> dict:
    try:
        return load_mqtt_qualification_repeats()
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc
