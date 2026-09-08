import json
from pathlib import Path

import paho.mqtt.client as mqtt
from jsonschema import ValidationError, validate

TESTBED_DIR = Path(__file__).resolve().parents[1]
SCHEMA_PATH = TESTBED_DIR / "schemas" / "vehicle_reading.schema.json"

BROKER_HOST = "127.0.0.1"
BROKER_PORT = 1883
RAW_TOPIC = "uagv/v2/OvGU-Testbed/+/state"

with SCHEMA_PATH.open(encoding="utf-8") as schema_file:
    VEHICLE_SCHEMA = json.load(schema_file)


def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        print(f"Gateway connected to {BROKER_HOST}:{BROKER_PORT}")
        print(f"Listening on {RAW_TOPIC}")
        client.subscribe(RAW_TOPIC, qos=1)
    else:
        print(f"Gateway connection failed: {reason_code}")


def on_message(client, userdata, message):
    try:
        payload = json.loads(message.payload.decode("utf-8"))
        validate(instance=payload, schema=VEHICLE_SCHEMA)

        print(
            f"PASS | vehicle={payload['vehicle_id']} "
            f"| sequence={payload['sequence']} "
            f"| topic={message.topic}"
        )

    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        print(f"BLOCK | malformed JSON | {error}")

    except ValidationError as error:
        print(f"BLOCK | schema violation | {error.message}")


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