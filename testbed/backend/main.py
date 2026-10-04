import os
from pathlib import Path
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI, HTTPException, WebSocket
from pydantic import BaseModel
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from .live_state import live_vehicle_store
from .live_stream import stream_vehicle_snapshots
from .mqtt_live import build_dashboard_mqtt_adapter
from .mqtt_control import (
    ControlUnavailableError,
    InvalidProfileError,
    VehicleOfflineError,
    build_dashboard_mqtt_control_manager,
)
from .results import (
    load_mqtt_qualification_bundle,
    load_mqtt_qualification_repeats,
    mqtt_qualification_status,
)


APP_VERSION = "0.7.0"
mqtt_live_adapter = (
    build_dashboard_mqtt_adapter(
        live_vehicle_store
    )
)

mqtt_control_manager = (
    build_dashboard_mqtt_control_manager(
        live_vehicle_store
    )
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    mqtt_live_adapter.start()
    mqtt_control_manager.start()

    try:
        yield
    finally:
        mqtt_control_manager.stop()
        mqtt_live_adapter.stop()


app = FastAPI(
    title="OCC Cybersecurity Testbed API",
    description=(
        "Backend API for telemetry, experiments, "
        "KPIs and security events."
    ),
    version=APP_VERSION,
    lifespan=lifespan,
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


dashboard_static_raw = os.getenv(
    "OCC_DASHBOARD_STATIC_DIR",
    "",
).strip()

dashboard_static_dir = (
    Path(dashboard_static_raw)
    if dashboard_static_raw
    else None
)

dashboard_index = None

if dashboard_static_dir is not None:
    dashboard_index = (
        dashboard_static_dir
        / "index.html"
    )

    dashboard_assets = (
        dashboard_static_dir
        / "assets"
    )

    if not dashboard_index.is_file():
        raise RuntimeError(
            "Dashboard index.html missing: "
            f"{dashboard_index}"
        )

    if not dashboard_assets.is_dir():
        raise RuntimeError(
            "Dashboard assets directory missing: "
            f"{dashboard_assets}"
        )

    app.mount(
        "/assets",
        StaticFiles(
            directory=str(
                dashboard_assets
            ),
        ),
        name="dashboard-assets",
    )


app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class SecurityProfileRequest(BaseModel):
    profile: str


@app.get("/", include_in_schema=False)
def root():
    if dashboard_index is not None:
        return FileResponse(
            dashboard_index
        )

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



@app.get("/api/v1/mqtt/live/status")
def mqtt_live_status_endpoint() -> dict:
    return mqtt_live_adapter.status()


@app.get("/api/v1/mqtt/control/status")
def mqtt_control_status_endpoint() -> dict:
    return mqtt_control_manager.status()


@app.get(
    "/api/v1/vehicles/{vehicle_id}/control-state"
)
def vehicle_control_state_endpoint(
    vehicle_id: str,
) -> dict:
    try:
        return mqtt_control_manager.control_state(
            vehicle_id
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail="vehicle not found",
        ) from exc


@app.post(
    "/api/v1/vehicles/{vehicle_id}/security-profile"
)
def vehicle_security_profile_endpoint(
    vehicle_id: str,
    request: SecurityProfileRequest,
) -> dict:
    try:
        return mqtt_control_manager.request_profile(
            vehicle_id,
            request.profile,
        )

    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail="vehicle not found",
        ) from exc

    except InvalidProfileError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    except VehicleOfflineError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc

    except ControlUnavailableError as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc



@app.websocket("/api/v1/ws/vehicles")
async def websocket_vehicles(
    websocket: WebSocket,
) -> None:
    await stream_vehicle_snapshots(
        websocket,
        live_vehicle_store,
    )


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
