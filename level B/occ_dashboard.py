import json
import time
import ssl
import threading
from collections import deque

import pandas as pd
import paho.mqtt.client as mqtt
import streamlit as st

BROKER = "2d0d6f6575dc4006bebe6f5c459bad88.s1.eu.hivemq.cloud"
PORT = 8883
USERNAME = "occuser"
PASSWORD = "Occpassword123"

TOPIC = "vehicle/validated"

data_buffer = deque(maxlen=100)

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("[DASHBOARD] Connected to HiveMQ Cloud")
        client.subscribe(TOPIC)
        print("[DASHBOARD] Subscribed to vehicle/validated")
    else:
        print("[DASHBOARD] Connection failed:", rc)

def on_message(client, userdata, msg):
    try:
        data = json.loads(msg.payload.decode())

        row = {
            "time": time.strftime("%H:%M:%S"),
            "vehicle_id": data.get("vehicle_id", "UNKNOWN"),
            "latency_ms": data.get("latency_ms", 0),
            "jitter_ms": data.get("jitter_ms", 0),
            "packet_loss": data.get("packet_loss", 0),
            "throughput": data.get("throughput_msg_per_sec", 0),
            "status": data.get("security_status", "UNKNOWN"),
            "attack_type": data.get("attack_type", "NONE")
        }

        data_buffer.append(row)

    except Exception as e:
        print("[DASHBOARD ERROR]", e)

def start_mqtt():
    client = mqtt.Client()
    client.username_pw_set(USERNAME, PASSWORD)
    client.tls_set(cert_reqs=ssl.CERT_NONE)
    client.tls_insecure_set(True)

    client.on_connect = on_connect
    client.on_message = on_message

    client.connect(BROKER, PORT, 60)
    client.loop_forever()

threading.Thread(target=start_mqtt, daemon=True).start()

st.set_page_config(
    page_title="OCC Cybersecurity Dashboard",
    layout="wide"
)

st.title("OCC Cybersecurity Real-Time Dashboard")
st.caption("ESP32_REAL → HiveMQ Cloud → Raspberry Pi Middleware → Validated OCC Dashboard")

placeholder = st.empty()

while True:
    with placeholder.container():
        df = pd.DataFrame(list(data_buffer))

        if df.empty:
            st.warning("Waiting for validated telemetry from middleware...")
        else:
            latest = df.iloc[-1]

            c1, c2, c3, c4 = st.columns(4)

            c1.metric("Vehicle ID", latest["vehicle_id"])
            c2.metric("Security Status", latest["status"])
            c3.metric("Latency", f"{latest['latency_ms']} ms")
            c4.metric("Attack Type", latest["attack_type"])

            st.subheader("Security Status Count")
            status_df = df["status"].value_counts()
            st.bar_chart(status_df)

            st.subheader("Latency and Jitter Trend")
            st.line_chart(
                df.set_index("time")[["latency_ms", "jitter_ms"]]
            )

            st.subheader("Throughput Trend")
            st.line_chart(
                df.set_index("time")[["throughput"]]
            )

            st.subheader("Packet Loss Trend")
            st.line_chart(
                df.set_index("time")[["packet_loss"]]
            )

            st.subheader("Live Validated Telemetry")
            st.dataframe(df.tail(30), use_container_width=True)

    time.sleep(1)