import paho.mqtt.client as mqtt
import json
import time
import random
import ssl

BROKER = "2d0d6f6575dc4006bebe6f5c459bad88.s1.eu.hivemq.cloud"
PORT = 8883
USERNAME = "occuser"
PASSWORD = "Occpassword123"

TOPIC = "vehicle/raw"

client = mqtt.Client()
client.username_pw_set(USERNAME, PASSWORD)
client.tls_set(cert_reqs=ssl.CERT_NONE)
client.tls_insecure_set(True)

client.connect(BROKER, PORT, 60)

print("[ATTACK SIMULATOR] Connected to HiveMQ Cloud")

while True:

    normal_data = {
        "vehicle_id": "ESP32_NORMAL",
        "timestamp": time.time(),
        "speed": random.randint(20, 60),
        "battery": random.randint(60, 100),
        "temperature": random.randint(25, 40),
        "location": {
            "lat": 52.1,
            "lon": 11.6
        },
        "latency_ms": round(random.uniform(0.2, 0.6), 2),
        "jitter_ms": round(random.uniform(0.0, 1.0), 2),
        "packet_loss": 0,
        "throughput_msg_per_sec": 0.51
    }

    attack_data = {
        "vehicle_id": "ESP32_ATTACK",
        "timestamp": time.time(),
        "speed": 250,
        "battery": 90,
        "temperature": 90,
        "location": {
            "lat": 52.1,
            "lon": 11.6
        },
        "latency_ms": 5000.0,
        "jitter_ms": 500.0,
        "packet_loss": 75,
        "throughput_msg_per_sec": 0.01
    }

    client.publish(TOPIC, json.dumps(normal_data))
    print("[NORMAL DATA SENT]")

    time.sleep(2)

    client.publish(TOPIC, json.dumps(attack_data))
    print("[ATTACK DATA SENT]")

    time.sleep(2)