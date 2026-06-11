import json
import paho.mqtt.client as mqtt

BROKER = "localhost"
TOPIC = "vehicle/validated"

def on_connect(client, userdata, flags, rc):
    print("[DASHBOARD] Connected")
    client.subscribe(TOPIC)

def on_message(client, userdata, msg):
    data = json.loads(msg.payload.decode())
    print("\n===== OCC DASHBOARD =====")
    print("Vehicle:", data.get("vehicle_id"))
    print("Status:", data.get("security_status"))
    print("Latency:", data.get("latency_ms"), "ms")
    print("Jitter:", data.get("jitter_ms"), "ms")
    print("Packet loss:", data.get("packet_loss"))
    print("Throughput:", data.get("throughput_msg_per_sec"), "msg/s")
    print("=========================")

client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message
client.connect(BROKER, 1883, 60)
client.loop_forever()
