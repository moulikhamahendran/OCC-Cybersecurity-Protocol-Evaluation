import csv
import json
import os
import re
import signal
import ssl
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import paho.mqtt.client as mqtt

from data_generator import make_reading


TESTBED_DIR = Path(__file__).resolve().parents[1]
DEFAULT_CA_CERT = TESTBED_DIR / "config" / "certs" / "ca.crt"

BROKER_HOST = os.getenv("MQTT_HOST", "127.0.0.1")
BROKER_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USERNAME = os.getenv("MQTT_USERNAME")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD")
MQTT_USE_TLS = os.getenv("MQTT_TLS", "false").lower() == "true"
MQTT_CA_CERT = os.getenv("MQTT_CA_CERT", str(DEFAULT_CA_CERT))
SECURITY_LEVEL = os.getenv("MQTT_SECURITY_LEVEL", "C0")

RUN_ID = os.getenv("RUN_ID") or f"manual_{uuid4().hex}"

TOPIC = "uagv/v2/OvGU-Testbed/VM-001/state"
PUBLISH_INTERVAL_SECONDS = 0.1
ACK_TIMEOUT_SECONDS = 2.0

LEDGER_FIELDS = [
    "timestamp",
    "run_id",
    "security_level",
    "serial_number",
    "header_id",
    "t_send_ns",
    "payload_bytes",
    "status",
    "detail",
]


def main() -> None:
    if not re.fullmatch(r"[A-Za-z0-9_-]+", RUN_ID):
        raise ValueError(
            "RUN_ID must contain only letters, numbers, "
            "underscores or hyphens."
        )

    run_dir = TESTBED_DIR / "results" / "runs" / RUN_ID
    run_dir.mkdir(parents=True, exist_ok=True)
    ledger_path = run_dir / "publisher.csv"

    stop_requested = threading.Event()
    connection_finished = threading.Event()
    connection_result = {"error": None}

    def request_stop(signum, frame):
        stop_requested.set()

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)

    def on_connect(client, userdata, flags, reason_code, properties):
        if reason_code != 0:
            connection_result["error"] = str(reason_code)
        connection_finished.set()

    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id=f"vehicle-VM-001-{uuid4().hex}",
    )
    client.on_connect = on_connect
    client.connect_timeout = 3.0

    if MQTT_USERNAME:
        client.username_pw_set(
            username=MQTT_USERNAME,
            password=MQTT_PASSWORD,
        )

    if MQTT_USE_TLS:
        client.tls_set(
            ca_certs=MQTT_CA_CERT,
            tls_version=ssl.PROTOCOL_TLS_CLIENT,
        )

    print(
        f"Connecting publisher to {BROKER_HOST}:{BROKER_PORT} "
        f"using security level {SECURITY_LEVEL}"
    )
    print(f"Run ID: {RUN_ID}")
    print(f"Publisher ledger: {ledger_path}")

    # Exclusive creation prevents overwriting an earlier run.
    with ledger_path.open(
        "x", newline="", encoding="utf-8"
    ) as ledger_file:
        writer = csv.DictWriter(
            ledger_file,
            fieldnames=LEDGER_FIELDS,
        )
        writer.writeheader()
        ledger_file.flush()

        def record(payload, payload_bytes, status, detail=""):
            writer.writerow(
                {
                    "timestamp": datetime.now(
                        timezone.utc
                    ).isoformat(),
                    "run_id": RUN_ID,
                    "security_level": SECURITY_LEVEL,
                    "serial_number": payload["serialNumber"],
                    "header_id": payload["headerId"],
                    "t_send_ns": payload["t_send_ns"],
                    "payload_bytes": payload_bytes,
                    "status": status,
                    "detail": detail,
                }
            )
            ledger_file.flush()

        loop_started = False

        try:
            client.connect(
                BROKER_HOST,
                BROKER_PORT,
                keepalive=60,
            )
            client.loop_start()
            loop_started = True

            connection_deadline = time.monotonic() + 3.0

            while not connection_finished.wait(timeout=0.05):
                if stop_requested.is_set():
                    return
                if time.monotonic() >= connection_deadline:
                    raise RuntimeError(
                        "Broker connection acknowledgement timed out."
                    )

            if connection_result["error"] is not None:
                raise RuntimeError(
                    "Broker rejected connection: "
                    f"{connection_result['error']}"
                )

            sequence = 0

            while not stop_requested.is_set():
                payload = make_reading(sequence)
                encoded = json.dumps(
                    payload,
                    separators=(",", ":"),
                ).encode("utf-8")

                record(payload, len(encoded), "ATTEMPT")

                try:
                    publication = client.publish(
                        TOPIC,
                        encoded,
                        qos=1,
                    )

                    if publication.rc != mqtt.MQTT_ERR_SUCCESS:
                        record(
                            payload,
                            len(encoded),
                            "PUBLISH_ERROR",
                            f"return_code={publication.rc}",
                        )
                        raise RuntimeError(
                            f"Publish failed for sequence {sequence}"
                        )

                    record(payload, len(encoded), "QUEUED")

                    publication.wait_for_publish(
                        timeout=ACK_TIMEOUT_SECONDS
                    )

                    if not publication.is_published():
                        record(
                            payload,
                            len(encoded),
                            "ACK_TIMEOUT",
                            "Delivery unresolved; not proof of loss.",
                        )
                        raise RuntimeError(
                            f"No broker acknowledgement within "
                            f"{ACK_TIMEOUT_SECONDS} seconds for "
                            f"sequence {sequence}"
                        )

                    record(payload, len(encoded), "BROKER_ACK")

                except Exception as error:
                    record(
                        payload,
                        len(encoded),
                        "ERROR",
                        str(error),
                    )
                    raise

                print(f"Broker acknowledged sequence {sequence}")
                sequence += 1

                # Retains the existing acknowledgement-paced workload.
                stop_requested.wait(PUBLISH_INTERVAL_SECONDS)

        finally:
            if loop_started:
                client.disconnect()
                client.loop_stop()

            print("Vehicle publisher stopped")


if __name__ == "__main__":
    main()