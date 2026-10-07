from __future__ import annotations

import os
from pathlib import Path
import ssl
import threading
from datetime import UTC, datetime

import paho.mqtt.client as mqtt

from testbed.final_runtime.occ.core.config import (
    load_runtime_config,
)
from testbed.final_runtime.occ.core.runtime_payload import (
    decode_runtime_payload,
)

from .live_state import LiveVehicleStore


TESTBED_ROOT = Path(__file__).resolve().parents[1]

REPO_RUNTIME_CONFIG = (
    TESTBED_ROOT
    / "final_runtime"
    / "config"
    / "system.example.json"
)

SYSTEM_RUNTIME_CONFIG = Path(
    "/etc/occ-final-runtime/system.json"
)

PROFILES = (
    "C0",
    "C1",
    "C2",
)


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def env_enabled() -> bool:
    value = os.getenv(
        "OCC_DASHBOARD_MQTT_ENABLED",
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

    if SYSTEM_RUNTIME_CONFIG.is_file():
        return SYSTEM_RUNTIME_CONFIG

    return REPO_RUNTIME_CONFIG


def parse_operational_topic(
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

    if kind != "telemetry":
        return None

    if (
        not vehicle_id
        or len(vehicle_id) >= 64
    ):
        return None

    if not all(
        char.isascii()
        and (
            char.isalnum()
            or char in {"-", "_"}
        )
        for char in vehicle_id
    ):
        return None

    return profile, vehicle_id


class DashboardMqttAdapter:
    """
    Read-only MQTT observer for the dashboard.

    Important:
    - subscribes only to occ/runtime/<profile>/+/telemetry
    - never publishes
    - never subscribes to fair/v1/#
    - does not participate in FAIR-V1 timing
    """

    def __init__(
        self,
        store: LiveVehicleStore,
        *,
        enabled: bool = False,
        config_path: Path | None = None,
        runtime_config=None,
        client_factory=mqtt.Client,
    ):
        self.store = store
        self.enabled = bool(enabled)

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

        self._profiles = {
            profile: {
                "profile": profile,
                "connected": False,
                "broker_host": None,
                "broker_port": None,
                "topic": (
                    f"occ/runtime/"
                    f"{profile}/+/telemetry"
                ),
                "accepted_messages": 0,
                "rejected_messages": 0,
                "last_message_utc": None,
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
                "dashboard live MQTT requires "
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

    def _credentials(self) -> tuple[str, str]:
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
                "C1/C2 dashboard MQTT requires "
                "OCC_MQTT_USERNAME and "
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
                "C2 dashboard MQTT requires "
                "OCC_MQTT_CA_FILE"
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
                "occ-dashboard-"
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

            state.update(changes)
            state["last_event_utc"] = (
                utc_now_iso()
            )

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
                    "MQTT connection rejected: "
                    f"{reason_code}"
                ),
            )
            return

        topic = self._profiles[
            profile
        ]["topic"]

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
                    "MQTT disconnected: "
                    f"{reason_code}"
                )
            ),
        )

    def _reject(
        self,
        profile: str,
        message: str,
    ) -> None:
        with self._lock:
            state = self._profiles[
                profile
            ]

            state[
                "rejected_messages"
            ] += 1

            state["last_error"] = (
                message
            )

            state["last_event_utc"] = (
                utc_now_iso()
            )

    def _accept(
        self,
        profile: str,
    ) -> None:
        with self._lock:
            state = self._profiles[
                profile
            ]

            state[
                "accepted_messages"
            ] += 1

            now = utc_now_iso()

            state[
                "last_message_utc"
            ] = now

            state[
                "last_event_utc"
            ] = now

            state["last_error"] = None

    def handle_message(
        self,
        profile: str,
        topic: str,
        payload_bytes: bytes,
    ) -> bool:

        if profile not in PROFILES:
            return False

        parsed = parse_operational_topic(
            topic
        )

        if parsed is None:
            self._reject(
                profile,
                "invalid operational telemetry topic",
            )
            return False

        topic_profile, vehicle_id = (
            parsed
        )

        if topic_profile != profile:
            self._reject(
                profile,
                "MQTT client/profile mismatch",
            )
            return False

        payload = decode_runtime_payload(
            payload_bytes
        )

        if payload is None:
            self._reject(
                profile,
                "malformed runtime telemetry payload",
            )
            return False

        if (
            payload["serialNumber"]
            != vehicle_id
        ):
            self._reject(
                profile,
                "topic/payload vehicle identity mismatch",
            )
            return False

        self.store.update_mqtt(
            profile,
            payload,
        )

        self._accept(
            profile
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

        self.handle_message(
            profile,
            message.topic,
            message.payload,
        )

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

            return {
                "enabled": self.enabled,
                "started": self._started,
                "mode": "read-only",
                "publishes": False,
                "formal_namespace_subscription":
                    False,
                "config_path": str(
                    self.config_path
                ),
                "profiles": profiles,
            }


def build_dashboard_mqtt_adapter(
    store: LiveVehicleStore,
) -> DashboardMqttAdapter:
    return DashboardMqttAdapter(
        store,
        enabled=env_enabled(),
        config_path=(
            default_runtime_config_path()
        ),
    )
