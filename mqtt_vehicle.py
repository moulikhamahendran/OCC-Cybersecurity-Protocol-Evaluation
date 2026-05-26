import time
import random
import json
import paho.mqtt.client as mqtt

BROKER = "localhost"
PORT = 1883
TOPIC = "occ/vehicle/agv01"

vehicle_id = "AGV-01"

client = mqtt.Client()

print("Connecting to local MQTT broker...")
client.connect(BROKER, PORT, 60)
print("Connected to MQTT broker")

while True:
    data = {
        "vehicle_id": vehicle_id,
        "speed": random.randint(20, 80),
        "battery": random.randint(40, 100),
        "latency_ms": round(random.uniform(5, 20), 2),
        "position": {
            "x": random.randint(1, 20),
            "y": random.randint(1, 20)
        },
        "task_status": random.choice(["IDLE", "MOVING", "LOADING", "UNLOADING"]),
        "protocol": "MQTT"
    }

    payload = json.dumps(data)

    client.publish(TOPIC, payload)

    print("Published:", payload)

    time.sleep(2)
