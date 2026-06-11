import json
import time
from collections import defaultdict, deque
import paho.mqtt.client as mqtt

BROKER = "2d0d6f6575dc4006bebe6f5c459bad88.s1.eu.hivemq.cloud"
PORT = 8883
USERNAME = "occuser"
PASSWORD = "Occpassword123"

RAW_TOPIC = "vehicle/raw"
VALIDATED_TOPIC = "vehicle/validated"

LATENCY_WARNING_MS = 300
LATENCY_ATTACK_MS = 1000

last_sequence = {}
last_latency = {}
message_times = defaultdict(lambda: deque(maxlen=50))

def validate_structure(data):
    required = [
        "vehicle_id",
        "timestamp",
        "sequence",
        "speed",
        "battery",
        "temperature",
        "location"
    ]

    for field in required:
        if field not in data:
            return False

    return True

def inspect_security(data):
    vehicle_id = data["vehicle_id"]
    now = time.time()

    timestamp = float(data["timestamp"])

    if timestamp > 100000000000:
        timestamp = timestamp / 1000

    latency_ms = (now - timestamp) * 1000

    previous_latency = last_latency.get(vehicle_id, latency_ms)
    jitter_ms = abs(latency_ms - previous_latency)
    last_latency[vehicle_id] = latency_ms

    previous_seq = last_sequence.get(vehicle_id)
    current_seq = int(data["sequence"])

    packet_loss = 0

    if previous_seq is not None:
        if current_seq > previous_seq + 1:
            packet_loss = current_seq - previous_seq - 1

    last_sequence[vehicle_id] = current_seq

    message_times[vehicle_id].append(now)
    window = message_times[vehicle_id]

    if len(window) > 1:
        throughput = len(window) / (window[-1] - window[0] + 0.001)
    else:
        throughput = 1

    status = "NORMAL"
    attack_type = "NONE"

    if latency_ms > LATENCY_ATTACK_MS:
        status = "ATTACK"
        attack_type = "HIGH_LATENCY_OR_REPLAY"

    elif latency_ms > LATENCY_WARNING_MS:
        status = "WARNING"
        attack_type = "LATENCY_WARNING"

    elif data["speed"] > 180:
        status = "ATTACK"
        attack_type = "SPEED_SPOOFING"

    elif packet_loss > 5:
        status = "ATTACK"
        attack_type = "PACKET_LOSS_OR_SEQUENCE_JUMP"

    data["latency_ms"] = round(latency_ms, 2)
    data["jitter_ms"] = round(jitter_ms, 2)
    data["packet_loss"] = packet_loss
    data["throughput_msg_per_sec"] = round(throughput, 2)
    data["security_status"] = status
    data["attack_type"] = attack_type
    data["middleware_time"] = now

    return data

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("[MIDDLEWARE] Connected to HiveMQ Cloud")
        client.subscribe(RAW_TOPIC)
        print("[MIDDLEWARE] Listening on vehicle/raw")
    else:
        print("[MIDDLEWARE] Connection failed:", rc)

def on_message(client, userdata, msg):
    try:
        data = json.loads(msg.payload.decode())

        if not validate_structure(data):
            print("[ATTACK] Invalid telemetry structure")
            return

        validated = inspect_security(data)

        client.publish(VALIDATED_TOPIC, json.dumps(validated))

        print(
            f"[{validated['security_status']}] "
            f"{validated['vehicle_id']} | "
            f"latency={validated['latency_ms']} ms | "
            f"jitter={validated['jitter_ms']} ms | "
            f"loss={validated['packet_loss']} | "
            f"throughput={validated['throughput_msg_per_sec']} msg/s | "
            f"attack={validated['attack_type']}"
        )

    except Exception as e:
        print("[ERROR]", e)

client = mqtt.Client()
client.username_pw_set(USERNAME, PASSWORD)
client.tls_set()

client.on_connect = on_connect
client.on_message = on_message

print("[MIDDLEWARE] Starting cloud MQTT firewall...")

client.connect(BROKER, PORT, 60)

client.loop_forever()