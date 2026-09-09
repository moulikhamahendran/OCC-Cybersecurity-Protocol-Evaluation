import csv
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import paho.mqtt.client as mqtt
from jsonschema import FormatChecker, ValidationError, validate

from kpi_recorder import write_kpi
from threat_detector import ThreatDetector


TESTBED_DIR = Path(__file__).resolve().parents[1]
SCHEMA_PATH = TESTBED_DIR / "schemas" / "vehicle_reading.schema.json"
RESULTS_DIR = TESTBED_DIR / "results"
EVENTS_PATH = RESULTS_DIR / "events.csv"

BROKER_HOST = "127.0.0.1"
BROKER_PORT = 1883
RAW_TOPIC = "uagv/v2/OvGU-Testbed/+/state"
LATENCY_WARNING_MS = 250.0

THREAT_DETECTOR = ThreatDetector()

with SCHEMA_PATH.open(encoding="utf-8") as schema_file:
    VEHICLE_SCHEMA = json.load(schema_file)


def write_event(
    topic: str,
    attack_type: str,
    action: str,
    reason: str,
    payload,
) -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    file_exists = EVENTS_PATH.exists()

    with EVENTS_PATH.open("a", newline="", encoding="utf-8") as event_file:
        writer = csv.DictWriter(
            event_file,
            fieldnames=[
                "timestamp",
                "topic",
                "attack_type",
                "action",
                "reason",
                "payload",
            ],
        )

        if not file_exists:
            writer.writeheader()

        writer.writerow(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "topic": topic,
                "attack_type": attack_type,
                "action": action,
                "reason": reason,
                "payload": json.dumps(payload, separators=(",", ":")),
            }
        )


def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        print(f"Gateway connected to {BROKER_HOST}:{BROKER_PORT}")
        client.subscribe(RAW_TOPIC, qos=1)
        print(f"Listening on {RAW_TOPIC}")
    else:
        print(f"Connection failed: {reason_code}")


def on_message(client, userdata, message):
    received_ns = time.time_ns()
    topic = message.topic

    try:
        payload = json.loads(message.payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        print(f"BLOCK | Invalid JSON | {error}")

        write_event(
            topic=topic,
            attack_type="malformed_payload",
            action="BLOCK",
            reason=f"Invalid JSON: {error}",
            payload=message.payload.decode("utf-8", errors="replace"),
        )
        return

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

    client.publish(
        verified_topic,
        json.dumps(payload, separators=(",", ":")),
        qos=1,
    )

    write_kpi(
        payload=payload,
        latency_ms=latency_ms,
        verdict=verdict,
    )

    print(
        f"{verdict} | vehicle={payload['serialNumber']} "
        f"| headerId={payload['headerId']} "
        f"| latency={latency_ms:.3f} ms "
        f"| forwarded={verified_topic}"
    )


def main():
    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id="occ-cybersecurity-gateway",
    )

    client.on_connect = on_connect
    client.on_message = on_message

    print("Starting OCC cybersecurity gateway")
    print("Press Control+C to stop")

    try:
        client.connect(BROKER_HOST, BROKER_PORT, keepalive=60)
        client.loop_forever()

    except KeyboardInterrupt:
        print("\nGateway stopped")

    finally:
        client.disconnect()


if __name__ == "__main__":
    main()