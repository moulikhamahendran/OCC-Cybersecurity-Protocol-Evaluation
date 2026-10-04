from __future__ import annotations

import json
import os
import ssl
import threading
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

import paho.mqtt.client as mqtt

from testbed.final_runtime.occ.core.config import (
    load_runtime_config,
)

from .live_state import LiveVehicleStore


TESTBED_ROOT = Path(__file__).resolve().parents[1]

REPO_RUNTIME_CONFIG = (
    TESTBED_ROOT
    / "final_runtime"
    / "config"
    / "system.example.json"
)

PI_RUNTIME_CONFIG = Path(
    "/etc/occ-final-runtime/system.json"
)

PROFILES = (
    "C0",
    "C1",
    "C2",
)

TERMINAL_PHASES = {
    "verified",
    "failed",
    "timeout",
}


class MqttControlError(RuntimeError):
    pass


class ControlUnavailableError(MqttControlError):
    pass


class VehicleOfflineError(MqttControlError):
    pass


class InvalidProfileError(ValueError):
    pass


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def env_control_enabled() -> bool:
    value = os.getenv(
        "OCC_DASHBOARD_MQTT_CONTROL_ENABLED",
        "0",
    ).strip().lower()

    return value in {
        "1",
        "true",
        "yes",
        "on",
    }


def default_runtime_config_path() -> Path:
    configured = os.getenv(
        "OCC_DASHBOARD_RUNTIME_CONFIG",
        "",
    ).strip()

    if configured:
        return Path(
            configured
        ).expanduser().resolve()

    if PI_RUNTIME_CONFIG.is_file():
        return PI_RUNTIME_CONFIG

    return REPO_RUNTIME_CONFIG


def vehicle_id_is_valid(
    vehicle_id: str,
) -> bool:
    if (
        not isinstance(vehicle_id, str)
        or not vehicle_id
        or len(vehicle_id) >= 64
    ):
        return False

    return all(
        char.isascii()
        and (
            char.isalnum()
            or char in {
                "-",
                "_",
            }
        )
        for char in vehicle_id
    )


def parse_status_topic(
    topic: str,
) -> tuple[str, str] | None:
    if not isinstance(topic, str):
        return None

    parts = topic.split("/")

    if len(parts) != 5:
        return None

    root, runtime, profile, vehicle_id, kind = (
        parts
    )

    if root != "occ":
        return None

    if runtime != "runtime":
        return None

    if profile not in PROFILES:
        return None

    if kind != "status":
        return None

    if not vehicle_id_is_valid(
        vehicle_id
    ):
        return None

    return profile, vehicle_id


class DashboardMqttControlManager:
    """
    Operational MQTT control plane for the dashboard.

    This manager is intentionally separate from the read-only
    telemetry observer.

    It may:
    - publish operational set_profile commands
    - subscribe to operational vehicle status topics
    - verify profile changes from status and live telemetry

    It must never:
    - publish to fair/v1/#
    - modify FAIR-V1 benchmark definitions
    - treat button clicks as successful without verification
    """

    def __init__(
        self,
        store: LiveVehicleStore,
        *,
        enabled: bool = False,
        timeout_seconds: float = 60.0,
        config_path: Path | None = None,
        runtime_config=None,
        client_factory=mqtt.Client,
    ):
        if timeout_seconds <= 0:
            raise ValueError(
                "timeout_seconds must be positive"
            )

        self.store = store
        self.enabled = bool(enabled)
        self.timeout_seconds = float(
            timeout_seconds
        )

        self.config_path = (
            Path(config_path)
            if config_path is not None
            else default_runtime_config_path()
        )

        self._runtime_config = runtime_config
        self._client_factory = client_factory

        self._lock = threading.RLock()
        self._clients: dict[str, object] = {}
        self._started = False

        self._requests: dict[str, dict] = {}
        self._events: list[dict] = []

        self._profiles = {
            profile: {
                "profile": profile,
                "connected": False,
                "broker_host": None,
                "broker_port": None,
                "status_topic": (
                    f"occ/runtime/"
                    f"{profile}/+/status"
                ),
                "last_event_utc": None,
                "last_error": None,
            }
            for profile in PROFILES
        }

    def _load_config(self):
        if self._runtime_config is not None:
            config = self._runtime_config
        else:
            if not self.config_path.is_file():
                raise FileNotFoundError(
                    self.config_path
                )

            config = load_runtime_config(
                self.config_path
            )

        if config.runtime_mode != "operational":
            raise ValueError(
                "dashboard MQTT control requires "
                "runtime_mode=operational"
            )

        available = set(
            config.mqtt.profiles
        )

        expected = set(PROFILES)

        if available != expected:
            raise ValueError(
                "operational MQTT profiles must be "
                "exactly C0, C1, C2"
            )

        return config

    def _credentials(
        self,
    ) -> tuple[str, str]:
        username = os.getenv(
            "OCC_MQTT_USERNAME",
            "",
        )

        password = os.getenv(
            "OCC_MQTT_PASSWORD",
            "",
        )

        if not username or not password:
            raise ValueError(
                "C1/C2 dashboard MQTT control "
                "requires OCC_MQTT_USERNAME and "
                "OCC_MQTT_PASSWORD"
            )

        return username, password

    def _ca_file(self) -> Path:
        value = os.getenv(
            "OCC_MQTT_CA_FILE",
            "",
        ).strip()

        if not value:
            raise ValueError(
                "C2 dashboard MQTT control "
                "requires OCC_MQTT_CA_FILE"
            )

        path = Path(
            value
        ).expanduser()

        if not path.is_file():
            raise FileNotFoundError(
                path
            )

        return path

    def _build_client(
        self,
        profile: str,
    ):
        client = self._client_factory(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=(
                "occ-dashboard-control-"
                f"{profile.lower()}"
            ),
            userdata={
                "security_profile": profile
            },
            protocol=mqtt.MQTTv311,
        )

        client.on_connect = self.on_connect
        client.on_disconnect = (
            self.on_disconnect
        )
        client.on_message = self.on_message

        if profile in {
            "C1",
            "C2",
        }:
            username, password = (
                self._credentials()
            )

            client.username_pw_set(
                username,
                password,
            )

        if profile == "C2":
            ca_file = self._ca_file()

            client.tls_set(
                ca_certs=str(ca_file),
                cert_reqs=ssl.CERT_REQUIRED,
                tls_version=ssl.PROTOCOL_TLS_CLIENT,
            )

            client.tls_insecure_set(
                False
            )

        return client

    def _set_profile_status(
        self,
        profile: str,
        **changes,
    ) -> None:
        with self._lock:
            state = self._profiles[
                profile
            ]

            state.update(
                changes
            )

            state["last_event_utc"] = (
                utc_now_iso()
            )

    def _record_event(
        self,
        vehicle_id: str,
        event: str,
        *,
        profile: str | None = None,
        detail: str | None = None,
    ) -> None:
        item = {
            "timestamp_utc": utc_now_iso(),
            "vehicle_id": vehicle_id,
            "event": event,
            "profile": profile,
            "detail": detail,
        }

        with self._lock:
            self._events.append(
                item
            )

            if len(self._events) > 200:
                del self._events[:-200]

    def start(self) -> None:
        if not self.enabled:
            return

        with self._lock:
            if self._started:
                return

        config = self._load_config()

        started_clients = []

        try:
            for profile in PROFILES:
                endpoint = (
                    config.mqtt.profiles[
                        profile
                    ]
                )

                self._set_profile_status(
                    profile,
                    broker_host=(
                        endpoint.broker_host
                    ),
                    broker_port=(
                        endpoint.port
                    ),
                    last_error=None,
                )

                client = self._build_client(
                    profile
                )

                self._clients[
                    profile
                ] = client

                client.connect_async(
                    endpoint.broker_host,
                    endpoint.port,
                    keepalive=30,
                )

                client.loop_start()

                started_clients.append(
                    client
                )

            with self._lock:
                self._started = True

        except Exception:
            for client in started_clients:
                try:
                    client.loop_stop()
                except Exception:
                    pass

            self._clients.clear()
            raise

    def stop(self) -> None:
        clients = list(
            self._clients.items()
        )

        for profile, client in clients:
            try:
                client.disconnect()
            except Exception:
                pass

            try:
                client.loop_stop()
            except Exception:
                pass

            self._set_profile_status(
                profile,
                connected=False,
            )

        with self._lock:
            self._clients.clear()
            self._started = False

    def on_connect(
        self,
        client,
        userdata,
        flags,
        reason_code,
        properties,
    ):
        profile = (
            userdata.get(
                "security_profile"
            )
            if isinstance(
                userdata,
                dict,
            )
            else None
        )

        if profile not in PROFILES:
            return

        if reason_code != 0:
            self._set_profile_status(
                profile,
                connected=False,
                last_error=(
                    "MQTT control connection rejected: "
                    f"{reason_code}"
                ),
            )
            return

        topic = (
            self._profiles[
                profile
            ]["status_topic"]
        )

        client.subscribe(
            topic,
            qos=1,
        )

        self._set_profile_status(
            profile,
            connected=True,
            last_error=None,
        )

    def on_disconnect(
        self,
        client,
        userdata,
        disconnect_flags,
        reason_code,
        properties,
    ):
        profile = (
            userdata.get(
                "security_profile"
            )
            if isinstance(
                userdata,
                dict,
            )
            else None
        )

        if profile not in PROFILES:
            return

        self._set_profile_status(
            profile,
            connected=False,
            last_error=(
                None
                if reason_code == 0
                else (
                    "MQTT control disconnected: "
                    f"{reason_code}"
                )
            ),
        )

    def _public_request(
        self,
        request: dict,
    ) -> dict:
        return {
            key: value
            for key, value in request.items()
            if not key.startswith("_")
        }

    def _mark_request(
        self,
        vehicle_id: str,
        *,
        phase: str,
        result: str | None = None,
        error: str | None = None,
        vehicle_result: str | None = None,
    ) -> None:
        with self._lock:
            request = self._requests.get(
                vehicle_id
            )

            if request is None:
                return

            if request["phase"] in TERMINAL_PHASES:
                if not (
                    request["phase"] == "timeout"
                    and phase == "verified"
                ):
                    return

            request["phase"] = phase
            request["updated_utc"] = (
                utc_now_iso()
            )

            if result is not None:
                request["result"] = result

            if phase == "verified":
                request["error"] = None
            elif error is not None:
                request["error"] = error

            if vehicle_result is not None:
                request["vehicle_result"] = (
                    vehicle_result
                )

    def _refresh_request(
        self,
        vehicle_id: str,
    ) -> None:
        with self._lock:
            request = self._requests.get(
                vehicle_id
            )

            if request is None:
                return

            if request["phase"] in {
                "verified",
                "failed",
            }:
                return

            deadline = request[
                "_deadline_monotonic"
            ]

            target_profile = request[
                "target_profile"
            ]

        vehicle = self.store.get(
            vehicle_id
        )

        if (
            vehicle is not None
            and vehicle["online"]
            and vehicle[
                "security_profile"
            ] == target_profile
        ):
            self._mark_request(
                vehicle_id,
                phase="verified",
                result="success",
                error=None,
                vehicle_result="telemetry_verified",
            )

            self._record_event(
                vehicle_id,
                "profile_verified",
                profile=target_profile,
                detail=(
                    "verified from live telemetry"
                ),
            )

            return

        if time.monotonic() > deadline:
            self._mark_request(
                vehicle_id,
                phase="timeout",
                result="failed",
                error=(
                    "vehicle did not verify target "
                    "profile before timeout"
                ),
            )

            self._record_event(
                vehicle_id,
                "profile_switch_timeout",
                profile=target_profile,
            )

    def request_profile(
        self,
        vehicle_id: str,
        target_profile: str,
    ) -> dict:
        if not vehicle_id_is_valid(
            vehicle_id
        ):
            raise KeyError(
                vehicle_id
            )

        target_profile = str(
            target_profile
        ).upper()

        if target_profile not in PROFILES:
            raise InvalidProfileError(
                "security profile must be "
                "C0, C1, or C2"
            )

        if not self.enabled:
            raise ControlUnavailableError(
                "MQTT dashboard control is disabled"
            )

        with self._lock:
            if not self._started:
                raise ControlUnavailableError(
                    "MQTT dashboard control is not started"
                )

        vehicle = self.store.get(
            vehicle_id
        )

        if vehicle is None:
            raise KeyError(
                vehicle_id
            )

        if not vehicle["online"]:
            raise VehicleOfflineError(
                f"{vehicle_id} is offline"
            )

        current_profile = vehicle[
            "security_profile"
        ]

        if current_profile not in PROFILES:
            raise ControlUnavailableError(
                "vehicle current profile is unknown"
            )

        now_utc = utc_now_iso()

        request = {
            "request_id": uuid.uuid4().hex,
            "vehicle_id": vehicle_id,
            "previous_profile": current_profile,
            "target_profile": target_profile,
            "phase": "requested",
            "result": "pending",
            "vehicle_result": None,
            "error": None,
            "requested_utc": now_utc,
            "updated_utc": now_utc,
            "_deadline_monotonic": (
                time.monotonic()
                + self.timeout_seconds
            ),
        }

        with self._lock:
            existing = self._requests.get(
                vehicle_id
            )

            if (
                existing is not None
                and existing["phase"]
                not in TERMINAL_PHASES
            ):
                raise ControlUnavailableError(
                    "a profile switch is already "
                    f"in progress for {vehicle_id}"
                )

            self._requests[
                vehicle_id
            ] = request

        if current_profile == target_profile:
            self._mark_request(
                vehicle_id,
                phase="verified",
                result="success",
                vehicle_result="already_active",
            )

            self._record_event(
                vehicle_id,
                "profile_already_active",
                profile=target_profile,
            )

            return self.control_state(
                vehicle_id
            )

        with self._lock:
            profile_state = dict(
                self._profiles[
                    current_profile
                ]
            )

            client = self._clients.get(
                current_profile
            )

        if (
            client is None
            or not profile_state[
                "connected"
            ]
        ):
            self._mark_request(
                vehicle_id,
                phase="failed",
                result="failed",
                error=(
                    "control client for current "
                    f"profile {current_profile} "
                    "is not connected"
                ),
            )

            raise ControlUnavailableError(
                "control MQTT client for "
                f"{current_profile} is not connected"
            )

        topic = (
            f"occ/runtime/"
            f"{current_profile}/"
            f"{vehicle_id}/control"
        )

        payload = json.dumps(
            {
                "command": "set_profile",
                "profile": target_profile,
            },
            separators=(
                ",",
                ":",
            ),
        )

        info = client.publish(
            topic,
            payload,
            qos=1,
            retain=False,
        )

        rc = getattr(
            info,
            "rc",
            mqtt.MQTT_ERR_SUCCESS,
        )

        if rc != mqtt.MQTT_ERR_SUCCESS:
            self._mark_request(
                vehicle_id,
                phase="failed",
                result="failed",
                error=(
                    "MQTT control publish failed "
                    f"with rc={rc}"
                ),
            )

            raise ControlUnavailableError(
                "MQTT control publish failed"
            )

        with self._lock:
            request = self._requests[
                vehicle_id
            ]

            request["phase"] = (
                "command_sent"
            )

            request["command_topic"] = (
                topic
            )

            request["updated_utc"] = (
                utc_now_iso()
            )

        self._record_event(
            vehicle_id,
            "profile_command_sent",
            profile=target_profile,
            detail=(
                f"{current_profile} -> "
                f"{target_profile}"
            ),
        )

        return self.control_state(
            vehicle_id
        )

    def handle_status_message(
        self,
        profile: str,
        topic: str,
        payload_bytes: bytes,
    ) -> bool:
        if profile not in PROFILES:
            return False

        parsed = parse_status_topic(
            topic
        )

        if parsed is None:
            return False

        topic_profile, vehicle_id = (
            parsed
        )

        if topic_profile != profile:
            return False

        try:
            payload = json.loads(
                payload_bytes.decode(
                    "utf-8"
                )
            )
        except (
            UnicodeDecodeError,
            json.JSONDecodeError,
        ):
            return False

        if not isinstance(
            payload,
            dict,
        ):
            return False

        if payload.get(
            "vehicle_id"
        ) != vehicle_id:
            return False

        active_profile = payload.get(
            "active_profile"
        )

        requested_profile = payload.get(
            "requested_profile"
        )

        vehicle_result = payload.get(
            "result"
        )

        if active_profile not in PROFILES:
            return False

        if (
            requested_profile is not None
            and requested_profile
            not in PROFILES
        ):
            return False

        if not isinstance(
            vehicle_result,
            str,
        ):
            return False

        with self._lock:
            request = self._requests.get(
                vehicle_id
            )

            if request is None:
                return True

            target_profile = request[
                "target_profile"
            ]

        if requested_profile != target_profile:
            return True

        if vehicle_result == "switching":
            self._mark_request(
                vehicle_id,
                phase="switching",
                vehicle_result=vehicle_result,
            )

            self._record_event(
                vehicle_id,
                "profile_switching",
                profile=target_profile,
            )

        elif vehicle_result == "save_failed":
            self._mark_request(
                vehicle_id,
                phase="failed",
                result="failed",
                error=(
                    "vehicle failed to save "
                    "requested profile"
                ),
                vehicle_result=vehicle_result,
            )

            self._record_event(
                vehicle_id,
                "profile_save_failed",
                profile=target_profile,
            )

        elif (
            vehicle_result
            == "already_active"
            and active_profile
            == target_profile
        ):
            self._mark_request(
                vehicle_id,
                phase="verified",
                result="success",
                vehicle_result=vehicle_result,
            )

            self._record_event(
                vehicle_id,
                "profile_verified",
                profile=target_profile,
                detail="already active",
            )

        elif (
            vehicle_result == "online"
            and active_profile
            == target_profile
        ):
            self._mark_request(
                vehicle_id,
                phase="verified",
                result="success",
                vehicle_result=vehicle_result,
            )

            self._record_event(
                vehicle_id,
                "profile_verified",
                profile=target_profile,
                detail=(
                    "verified from vehicle "
                    "online status"
                ),
            )

        else:
            self._mark_request(
                vehicle_id,
                phase="status_received",
                vehicle_result=vehicle_result,
            )

        return True

    def on_message(
        self,
        client,
        userdata,
        message,
    ):
        profile = (
            userdata.get(
                "security_profile"
            )
            if isinstance(
                userdata,
                dict,
            )
            else None
        )

        if profile not in PROFILES:
            return

        self.handle_status_message(
            profile,
            message.topic,
            message.payload,
        )

    def control_state(
        self,
        vehicle_id: str,
    ) -> dict:
        self._refresh_request(
            vehicle_id
        )

        vehicle = self.store.get(
            vehicle_id
        )

        with self._lock:
            request = self._requests.get(
                vehicle_id
            )

            events = [
                dict(item)
                for item in self._events
                if item[
                    "vehicle_id"
                ] == vehicle_id
            ][-12:]

        if (
            vehicle is None
            and request is None
        ):
            raise KeyError(
                vehicle_id
            )

        return {
            "vehicle_id": vehicle_id,
            "online": (
                vehicle["online"]
                if vehicle is not None
                else False
            ),
            "actual_profile": (
                vehicle[
                    "security_profile"
                ]
                if vehicle is not None
                else None
            ),
            "request": (
                self._public_request(
                    request
                )
                if request is not None
                else None
            ),
            "recent_events": events,
        }

    def status(self) -> dict:
        with self._lock:
            profiles = [
                dict(
                    self._profiles[
                        profile
                    ]
                )
                for profile in PROFILES
            ]

            active_requests = sum(
                1
                for request
                in self._requests.values()
                if request["phase"]
                not in TERMINAL_PHASES
            )

            return {
                "enabled": self.enabled,
                "started": self._started,
                "mode": "operational-control",
                "publishes": True,
                "formal_namespace_subscription":
                    False,
                "formal_namespace_publish":
                    False,
                "timeout_seconds":
                    self.timeout_seconds,
                "active_requests":
                    active_requests,
                "profiles": profiles,
            }


def build_dashboard_mqtt_control_manager(
    store: LiveVehicleStore,
) -> DashboardMqttControlManager:
    return DashboardMqttControlManager(
        store,
        enabled=env_control_enabled(),
        config_path=(
            default_runtime_config_path()
        ),
    )
