import csv
import json
import os
import re
import ssl
import time
from datetime import datetime, timezone
from pathlib import Path

import paho.mqtt.client as mqtt
from jsonschema import FormatChecker, ValidationError, validate

from kpi_recorder import RUN_ID, write_kpi
from threat_detector import ThreatDetector


TESTBED_DIR = Path(__file__).resolve().parents[1]
SCHEMA_PATH = TESTBED_DIR / "schemas" / "vehicle_reading.schema.json"
RESULTS_DIR = TESTBED_DIR / "results"
EVENTS_PATH = RESULTS_DIR / "events.csv"
DEFAULT_CA_CERT = TESTBED_DIR / "config" / "certs" / "ca.crt"

BROKER_HOST = os.getenv("MQTT_HOST", "127.0.0.1")
BROKER_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USERNAME = os.getenv("MQTT_USERNAME")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD")
MQTT_USE_TLS = os.getenv("MQTT_TLS", "false").lower() == "true"
MQTT_CA_CERT = os.getenv("MQTT_CA_CERT", str(DEFAULT_CA_CERT))
SECURITY_LEVEL = os.getenv("MQTT_SECURITY_LEVEL", "C0")

OUTPUT_BROKER_HOST = os.getenv("MQTT_OUTPUT_HOST")
OUTPUT_BROKER_PORT = int(os.getenv("MQTT_OUTPUT_PORT", "1883"))
OUTPUT_MQTT_USERNAME = os.getenv("MQTT_OUTPUT_USERNAME")
OUTPUT_MQTT_PASSWORD = os.getenv("MQTT_OUTPUT_PASSWORD")
OUTPUT_MQTT_USE_TLS = (
    os.getenv("MQTT_OUTPUT_TLS", "false").lower() == "true"
)
OUTPUT_MQTT_CA_CERT = os.getenv(
    "MQTT_OUTPUT_CA_CERT",
    str(DEFAULT_CA_CERT),
)

FORWARD_CLIENT = None

RAW_TOPIC = "uagv/v2/OvGU-Testbed/+/state"
LATENCY_WARNING_MS = 250.0

THREAT_DETECTOR = ThreatDetector()

RECEIPT_FIELDS = [
    "timestamp",
    "run_id",
    "security_level",
    "topic",
    "serial_number",
    "header_id",
    "t_send_ns",
    "received_ns",
    "payload_bytes",
    "mqtt_duplicate",
    "json_valid",
]

with SCHEMA_PATH.open(encoding="utf-8") as schema_file:
    VEHICLE_SCHEMA = json.load(schema_file)


def write_receipt(
    userdata,
    message,
    received_ns,
    payload,
    json_valid,
):
    fields = payload if isinstance(payload, dict) else {}

    userdata["receipt_writer"].writerow(
        {
            "timestamp": datetime.fromtimestamp(
                received_ns / 1_000_000_000,
                timezone.utc,
            ).isoformat(),
            "run_id": RUN_ID,
            "security_level": SECURITY_LEVEL,
            "topic": message.topic,
            "serial_number": fields.get("serialNumber", ""),
            "header_id": fields.get("headerId", ""),
            "t_send_ns": fields.get("t_send_ns", ""),
            "received_ns": received_ns,
            "payload_bytes": len(message.payload),
            "mqtt_duplicate": int(message.dup),
            "json_valid": int(json_valid),
        }
    )
    userdata["receipt_file"].flush()


def write_event(
    topic: str,
    attack_type: str,
    action: str,
    reason: str,
    payload,
) -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).isoformat()

    # Keep the existing global event log for compatibility.
    global_fields = [
        "timestamp",
        "topic",
        "attack_type",
        "action",
        "reason",
        "payload",
    ]

    global_row = {
        "timestamp": timestamp,
        "topic": topic,
        "attack_type": attack_type,
        "action": action,
        "reason": reason,
        "payload": json.dumps(payload, separators=(",", ":")),
    }

    global_needs_header = (
        not EVENTS_PATH.exists()
        or EVENTS_PATH.stat().st_size == 0
    )

    with EVENTS_PATH.open(
        "a",
        newline="",
        encoding="utf-8",
    ) as event_file:
        writer = csv.DictWriter(
            event_file,
            fieldnames=global_fields,
        )

        if global_needs_header:
            writer.writeheader()

        writer.writerow(global_row)

    # Also write a run-specific event ledger.
    run_dir = RESULTS_DIR / "runs" / RUN_ID
    run_dir.mkdir(parents=True, exist_ok=True)

    run_events_path = run_dir / "events.csv"

    run_fields = [
        "timestamp",
        "run_id",
        "protocol",
        "security_level",
        "net_profile",
        "repeat_index",
        "topic",
        "attack_type",
        "action",
        "reason",
        "payload",
    ]

    run_needs_header = (
        not run_events_path.exists()
        or run_events_path.stat().st_size == 0
    )

    run_row = {
        "timestamp": timestamp,
        "run_id": RUN_ID,
        "protocol": os.getenv("PROTOCOL", "MQTT"),
        "security_level": SECURITY_LEVEL,
        "net_profile": os.getenv("NET_PROFILE", "NET-ideal"),
        "repeat_index": os.getenv("REPEAT_INDEX", "1"),
        "topic": topic,
        "attack_type": attack_type,
        "action": action,
        "reason": reason,
        "payload": json.dumps(payload, separators=(",", ":")),
    }

    with run_events_path.open(
        "a",
        newline="",
        encoding="utf-8",
    ) as run_event_file:
        writer = csv.DictWriter(
            run_event_file,
            fieldnames=run_fields,
        )

        if run_needs_header:
            writer.writeheader()

        writer.writerow(run_row)


def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        print(
            f"Gateway connected to {BROKER_HOST}:{BROKER_PORT} "
            f"using security level {SECURITY_LEVEL}"
        )
        client.subscribe(RAW_TOPIC, qos=1)
        print(f"Subscription requested for {RAW_TOPIC}")
    else:
        raise RuntimeError(f"Connection failed: {reason_code}")


def on_message(client, userdata, message):
    received_ns = time.time_ns()
    topic = message.topic

    try:
        payload = json.loads(message.payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        write_receipt(
            userdata, message, received_ns, None, False
        )

        print(f"BLOCK | Invalid JSON | {error}")
        write_event(
            topic=topic,
            attack_type="malformed_payload",
            action="BLOCK",
            reason=f"Invalid JSON: {error}",
            payload=message.payload.decode("utf-8", errors="replace"),
        )
        return

    write_receipt(
        userdata, message, received_ns, payload, True
    )

    try:
        validate(
            instance=payload,
            schema=VEHICLE_SCHEMA,
            format_checker=FormatChecker(),
        )
    except ValidationError as error:
        print(f"BLOCK | Schema violation: {error.message}")
        write_event(
            topic=topic,
            attack_type="schema_violation",
            action="BLOCK",
            reason=error.message,
            payload=payload,
        )
        return

    latency_ms = (received_ns - payload["t_send_ns"]) / 1_000_000
    threats = THREAT_DETECTOR.detect(payload)

    if threats:
        for threat in threats:
            print(
                f"{threat['action']} | {threat['type']} "
                f"| vehicle={payload['serialNumber']} "
                f"| headerId={payload['headerId']} "
                f"| {threat['reason']}"
            )

            write_event(
                topic=topic,
                attack_type=threat["type"],
                action=threat["action"],
                reason=threat["reason"],
                payload=payload,
            )

        write_kpi(
            payload=payload,
            latency_ms=latency_ms,
            verdict="BLOCK",
            security_level=SECURITY_LEVEL,
            condition=threats[0]["type"],
        )
        return

    verdict = "PASS"

    if latency_ms > LATENCY_WARNING_MS:
        verdict = "FLAG"
        write_event(
            topic=topic,
            attack_type="high_latency",
            action="FLAG",
            reason=(
                f"Latency {latency_ms:.3f} ms exceeds "
                f"{LATENCY_WARNING_MS:.3f} ms"
            ),
            payload=payload,
        )

    verified_topic = (
        f"uagv/v2/OvGU-Testbed/"
        f"{payload['serialNumber']}/verified"
    )

    publication = FORWARD_CLIENT.publish(
        verified_topic,
        json.dumps(payload, separators=(",", ":")),
        qos=1,
    )

    if publication.rc != mqtt.MQTT_ERR_SUCCESS:
        raise RuntimeError(
            f"Could not queue forwarding: {publication.rc}"
        )

    write_kpi(
        payload=payload,
        latency_ms=latency_ms,
        verdict=verdict,
        security_level=SECURITY_LEVEL,
    )

    print(
        f"{verdict} | security={SECURITY_LEVEL} "
        f"| vehicle={payload['serialNumber']} "
        f"| headerId={payload['headerId']} "
        f"| latency={latency_ms:.3f} ms "
        f"| forwarding_queued={verified_topic}"
    )


def main():
    global FORWARD_CLIENT
    if not re.fullmatch(r"[A-Za-z0-9_-]+", RUN_ID):
        raise ValueError("Invalid RUN_ID")

    run_dir = RESULTS_DIR / "runs" / RUN_ID
    run_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = run_dir / "gateway_receipts.csv"

    with receipt_path.open(
        "x", newline="", encoding="utf-8"
    ) as receipt_file:
        receipt_writer = csv.DictWriter(
            receipt_file,
            fieldnames=RECEIPT_FIELDS,
        )
        receipt_writer.writeheader()
        receipt_file.flush()

        client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"occ-gateway-{SECURITY_LEVEL.lower()}",
            userdata={
                "receipt_writer": receipt_writer,
                "receipt_file": receipt_file,
            },
        )

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

        FORWARD_CLIENT = client

        if OUTPUT_BROKER_HOST:
            FORWARD_CLIENT = mqtt.Client(
                callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
                client_id=f"occ-gateway-output-{SECURITY_LEVEL.lower()}",
            )

            if OUTPUT_MQTT_USERNAME:
                FORWARD_CLIENT.username_pw_set(
                    username=OUTPUT_MQTT_USERNAME,
                    password=OUTPUT_MQTT_PASSWORD,
                )

            if OUTPUT_MQTT_USE_TLS:
                FORWARD_CLIENT.tls_set(
                    ca_certs=OUTPUT_MQTT_CA_CERT,
                    tls_version=ssl.PROTOCOL_TLS_CLIENT,
                )

            FORWARD_CLIENT.connect(
                OUTPUT_BROKER_HOST,
                OUTPUT_BROKER_PORT,
                keepalive=60,
            )
            FORWARD_CLIENT.loop_start()

        client.on_connect = on_connect
        client.on_message = on_message

        print("Starting OCC cybersecurity gateway")
        print(f"Run ID: {RUN_ID}")
        print(f"Security level: {SECURITY_LEVEL}")
        print(f"TLS enabled: {MQTT_USE_TLS}")
        if OUTPUT_BROKER_HOST:
            print(
                "Forwarding verified messages to "
                f"{OUTPUT_BROKER_HOST}:{OUTPUT_BROKER_PORT}"
            )
        else:
            print("Forwarding verified messages through the input broker")
        print(f"Receipt ledger: {receipt_path}")
        print("Press Control+C to stop")

        try:
            client.connect(
                BROKER_HOST,
                BROKER_PORT,
                keepalive=60,
            )
            client.loop_forever()

        except KeyboardInterrupt:
            print("\nGateway stopped")

        finally:
            if FORWARD_CLIENT is not None and FORWARD_CLIENT is not client:
                FORWARD_CLIENT.loop_stop()
                FORWARD_CLIENT.disconnect()
            client.disconnect()


if __name__ == "__main__":
    main()