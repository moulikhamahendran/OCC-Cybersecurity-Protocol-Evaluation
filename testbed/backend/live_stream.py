from __future__ import annotations

import asyncio

from fastapi import WebSocket, WebSocketDisconnect

from .live_state import LiveVehicleStore


DEFAULT_PUSH_INTERVAL_SECONDS = 0.25


async def stream_vehicle_snapshots(
    websocket: WebSocket,
    store: LiveVehicleStore,
    *,
    interval_seconds: float = (
        DEFAULT_PUSH_INTERVAL_SECONDS
    ),
) -> None:
    """
    Stream dashboard snapshots only.

    This function:
    - reads LiveVehicleStore
    - performs no MQTT operations
    - performs no benchmark operations
    - does not publish vehicle commands
    """

    if interval_seconds < 0:
        raise ValueError(
            "interval_seconds must be >= 0"
        )

    await websocket.accept()

    try:
        while True:
            snapshot = store.snapshot()

            await websocket.send_json(
                snapshot
            )

            await asyncio.sleep(
                interval_seconds
            )

    except WebSocketDisconnect:
        return
