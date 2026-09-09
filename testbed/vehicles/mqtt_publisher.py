import json
import os
import ssl
import time
from pathlib import Path

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

TOPIC = "uagv/v2/OvGU-Testbed/VM-001/state"
PUBLISH_INTERVAL_SECONDS = 0.1


def main() -> None:
    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id=f"vehicle-VM-001-{time.time_ns()}",
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

    print(
        f"Connecting publisher to {BROKER_HOST}:{BROKER_PORT} "
        f"using security level {SECURITY_LEVEL}"
    )

    client.connect(
        BROKER_HOST,
        BROKER_PORT,
        keepalive=60,
    )
    client.loop_start()

    sequence = 0

    try:
        while True:
            payload = make_reading(sequence)

            publication = client.publish(
                TOPIC,
                json.dumps(payload, separators=(",", ":")),
                qos=1,
            )
            publication.wait_for_publish()

            print(
                f"Published sequence {sequence}: "
                f"{json.dumps(payload)}"
            )

            sequence += 1
            time.sleep(PUBLISH_INTERVAL_SECONDS)

    except KeyboardInterrupt:
        print("\nVehicle publisher stopped")

    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()