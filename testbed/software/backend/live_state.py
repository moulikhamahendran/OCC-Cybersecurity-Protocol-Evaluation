from __future__ import annotations

from datetime import UTC, datetime
import threading
import time


VALID_MQTT_PROFILES = {
    "C0",
    "C1",
    "C2",
}

REQUIRED_TELEMETRY_FIELDS = {
    "schema_ver",
    "serialNumber",
    "seq",
    "t_source_us",
    "speed",
    "pos_x",
    "pos_y",
    "heading",
    "battery_pct",
    "state",
}


class LiveVehicleStore:
    """
    Thread-safe dashboard state for operational telemetry.

    This is presentation/runtime state only.
    It is not FAIR-V1 benchmark evidence.

    A vehicle is displayed as online while telemetry has been
    observed within offline_after_seconds.
    """

    def __init__(
        self,
        offline_after_seconds: float = 3.0,
    ):
        if offline_after_seconds <= 0:
            raise ValueError(
                "offline_after_seconds must be positive"
            )

        self.offline_after_seconds = (
            float(offline_after_seconds)
        )

        self._lock = threading.RLock()
        self._vehicles: dict[str, dict] = {}

    def clear(self) -> None:
        with self._lock:
            self._vehicles.clear()

    def update_mqtt(
        self,
        security_profile: str,
        payload: dict,
        *,
        observed_utc: datetime | None = None,
        observed_monotonic: float | None = None,
    ) -> dict:

        if security_profile not in VALID_MQTT_PROFILES:
            raise ValueError(
                "MQTT security profile must be "
                "C0, C1, or C2"
            )

        if not isinstance(payload, dict):
            raise TypeError(
                "telemetry payload must be a dict"
            )

        missing = (
            REQUIRED_TELEMETRY_FIELDS
            - set(payload)
        )

        if missing:
            raise ValueError(
                "telemetry payload missing fields: "
                + ", ".join(sorted(missing))
            )

        vehicle_id = payload["serialNumber"]

        if (
            not isinstance(vehicle_id, str)
            or not vehicle_id
        ):
            raise ValueError(
                "serialNumber must be a non-empty string"
            )

        seq = payload["seq"]

        if (
            isinstance(seq, bool)
            or not isinstance(seq, int)
            or seq < 0
        ):
            raise ValueError(
                "seq must be a non-negative integer"
            )

        if observed_utc is None:
            observed_utc = datetime.now(UTC)

        if observed_utc.tzinfo is None:
            raise ValueError(
                "observed_utc must be timezone-aware"
            )

        if observed_monotonic is None:
            observed_monotonic = time.monotonic()

        state = {
            "vehicle_id": vehicle_id,
            "protocol": "mqtt",
            "security_profile": security_profile,
            "seq": seq,
            "last_seen_utc": (
                observed_utc.astimezone(
                    UTC
                ).isoformat()
            ),
            "_last_seen_monotonic": float(
                observed_monotonic
            ),
            "telemetry": {
                "schema_ver": payload[
                    "schema_ver"
                ],
                "t_source_us": payload[
                    "t_source_us"
                ],
                "speed": payload["speed"],
                "pos_x": payload["pos_x"],
                "pos_y": payload["pos_y"],
                "heading": payload["heading"],
                "battery_pct": payload[
                    "battery_pct"
                ],
                "state": payload["state"],
            },
        }

        with self._lock:
            self._vehicles[vehicle_id] = state

        return self.get(
            vehicle_id,
            now_monotonic=observed_monotonic,
        )

    def _public_state(
        self,
        state: dict,
        now_monotonic: float,
    ) -> dict:

        age_seconds = max(
            0.0,
            now_monotonic
            - state["_last_seen_monotonic"],
        )

        online = (
            age_seconds
            <= self.offline_after_seconds
        )

        return {
            "vehicle_id": state["vehicle_id"],
            "protocol": state["protocol"],
            "security_profile": (
                state["security_profile"]
            ),
            "online": online,
            "age_seconds": round(
                age_seconds,
                3,
            ),
            "last_seen_utc": (
                state["last_seen_utc"]
            ),
            "seq": state["seq"],
            "telemetry": dict(
                state["telemetry"]
            ),
        }

    def get(
        self,
        vehicle_id: str,
        *,
        now_monotonic: float | None = None,
    ) -> dict | None:

        if now_monotonic is None:
            now_monotonic = time.monotonic()

        with self._lock:
            state = self._vehicles.get(
                vehicle_id
            )

            if state is None:
                return None

            return self._public_state(
                state,
                float(now_monotonic),
            )

    def snapshot(
        self,
        *,
        now_monotonic: float | None = None,
    ) -> dict:

        if now_monotonic is None:
            now_monotonic = time.monotonic()

        now_monotonic = float(
            now_monotonic
        )

        with self._lock:
            vehicles = [
                self._public_state(
                    self._vehicles[vehicle_id],
                    now_monotonic,
                )
                for vehicle_id
                in sorted(self._vehicles)
            ]

        online_count = sum(
            vehicle["online"]
            for vehicle in vehicles
        )

        return {
            "source": "live-operational",
            "scientific_evidence": False,
            "protocol": "mqtt",
            "online_rule": {
                "offline_after_seconds":
                    self.offline_after_seconds,
            },
            "vehicle_count": len(vehicles),
            "online_count": online_count,
            "vehicles": vehicles,
        }


live_vehicle_store = LiveVehicleStore()
