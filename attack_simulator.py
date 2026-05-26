import paho.mqtt.client as mqtt
import json
import random
import time

broker = "localhost"
topic = "occ/vehicle"

client = mqtt.Client()
client.connect(broker, 1883, 60)

print("Starting fake cyber attack simulation...\n")

while True:

    fake_data = {
        "vehicle_id": "FAKE-AGV",
        "speed": random.randint(150, 300),
        "battery": random.randint(-20, 5),
        "latency_ms": random.uniform(100, 500),
        "position": {
            "x": random.randint(100, 500),
            "y": random.randint(100, 500)
        },
        "task_status": "HACKED",
        "protocol": "MQTT",
        "attack": "Fake Vehicle Injection"
    }

    payload = json.dumps(fake_data)

    client.publish(topic, payload)

    print("ATTACK PACKET SENT:")
    print(payload)

    time.sleep(3)
