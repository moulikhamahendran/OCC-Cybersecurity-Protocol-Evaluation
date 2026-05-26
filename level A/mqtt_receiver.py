import json
import paho.mqtt.client as mqtt
from datetime import datetime

BROKER = "localhost"
PORT = 1883
TOPIC = "occ/vehicle/agv01"

def on_connect(client, userdata, flags, rc):
    print("Connected to MQTT broker")
    client.subscribe(TOPIC)
    print("Subscribed to:", TOPIC)

def on_message(client, userdata, msg):
    data = json.loads(msg.payload.decode())

    print("\n--- OCC RECEIVED VEHICLE DATA ---")
    print("Time:", datetime.now().strftime("%H:%M:%S"))
    print("Vehicle:", data["vehicle_id"])
    print("Speed:", data["speed"], "km/h")
    print("Battery:", data["battery"], "%")
    print("Latency:", data["latency_ms"], "ms")
    print("Task:", data["task_status"])
    print("Protocol:", data["protocol"])

client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message

client.connect(BROKER, PORT, 60)
client.loop_forever()
