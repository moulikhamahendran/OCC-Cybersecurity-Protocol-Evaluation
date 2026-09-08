import json
import sys
import time
from pathlib import Path

import paho.mqtt.client as mqtt

TESTBED_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TESTBED_DIR))

from vehicles.data_generator import make_reading

BROKER_HOST = "127.0.0.1"
BROKER_PORT = 1883
SERIAL_NUMBER = "VM-001"
TOPIC = f"uagv/v2/OvGU-Testbed/{SERIAL_NUMBER}/state"
PUBLISH_RATE_HZ = 10


def main():
    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id=f"vehicle-{SERIAL_NUMBER}",
    )

    client.connect(BROKER_HOST, BROKER_PORT, keepalive=60)
    client.loop_start()

    sequence = 0
    interval = 1 / PUBLISH_RATE_HZ

    print(f"Connected to MQTT broker at {BROKER_HOST}:{BROKER_PORT}")
    print(f"Publishing to {TOPIC} at {PUBLISH_RATE_HZ} messages/second")
    print("Press Control+C to stop")

    try:
        while True:
            reading = make_reading(sequence)
            payload = json.dumps(reading)

            message = client.publish(
                topic=TOPIC,
                payload=payload,
                qos=1,
            )
            message.wait_for_publish()

            print(f"Published sequence {sequence}: {payload}")

            sequence += 1
            time.sleep(interval)

    except KeyboardInterrupt:
        print("\nVehicle publisher stopped")

    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()