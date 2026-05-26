import streamlit as st
import pandas as pd
import random
import time
from datetime import datetime

st.set_page_config(
    page_title="OCC Cybersecurity Dashboard",
    page_icon="🛡️",
    layout="wide"
)

st.markdown("# 🛡️ OCC Cybersecurity Middleware Dashboard")
st.markdown("### 📡 Raspberry Pi → MQTT → Middleware → OCC Monitoring")

if "df" not in st.session_state:
    st.session_state.df = pd.DataFrame(columns=[
        "time", "vehicle_id", "speed", "battery", "latency_ms",
        "packet_loss", "jitter", "status", "threat"
    ])

placeholder = st.empty()

while True:
    now = datetime.now().strftime("%H:%M:%S")

    threat = random.choice([0, 0, 0, 0, 1])
    status = "attack_suspected" if threat else "running"

    new_data = {
        "time": now,
        "vehicle_id": random.choice(["AGV-01", "AGV-02", "AGV-03"]),
        "speed": random.randint(20, 80) if not threat else random.randint(120, 220),
        "battery": random.randint(40, 100) if not threat else random.randint(0, 15),
        "latency_ms": round(random.uniform(5, 25), 2) if not threat else round(random.uniform(100, 400), 2),
        "packet_loss": round(random.uniform(0, 3), 2) if not threat else round(random.uniform(10, 35), 2),
        "jitter": round(random.uniform(1, 8), 2) if not threat else round(random.uniform(30, 90), 2),
        "status": status,
        "threat": threat
    }

    st.session_state.df = pd.concat(
        [st.session_state.df, pd.DataFrame([new_data])],
        ignore_index=True
    ).tail(40)

    df = st.session_state.df.copy()
    df["sample"] = range(len(df))

    attack_count = int(df["threat"].sum())
    active_vehicles = df["vehicle_id"].nunique()

    with placeholder.container():
        st.info(
            f"🟢 System Live | 🚘 Vehicles: {active_vehicles} | 📶 MQTT | "
            f"🛡️ Middleware Active | ⚠️ Threat Events: {attack_count}"
        )

        col1, col2, col3, col4, col5 = st.columns(5)

        col1.metric("🚘 Active Vehicles", active_vehicles)
        col2.metric("🚗 Avg Speed", f"{df['speed'].mean():.1f} km/h")
        col3.metric("⏱️ Avg Latency", f"{df['latency_ms'].mean():.1f} ms")
        col4.metric("📉 Packet Loss", f"{df['packet_loss'].mean():.1f}%")
        col5.metric("🚨 Threat Events", attack_count)

        st.divider()

        st.subheader("🚘 Vehicle Monitoring")
        vcols = st.columns(3)

        latest_by_vehicle = df.groupby("vehicle_id").tail(1)

        for i, (_, row) in enumerate(latest_by_vehicle.iterrows()):
            icon = "✅" if row["threat"] == 0 else "🚨"
            with vcols[i % 3]:
                st.markdown(f"""
                ### {icon} {row['vehicle_id']}
                **Status:** {row['status']}  
                🚗 **Speed:** {row['speed']} km/h  
                🔋 **Battery:** {row['battery']}%  
                ⏱️ **Latency:** {row['latency_ms']} ms  
                📉 **Packet Loss:** {row['packet_loss']}%  
                🌊 **Jitter:** {row['jitter']} ms  
                🕒 **Last Update:** {row['time']}
                """)

        st.divider()

        c1, c2 = st.columns(2)

        with c1:
            st.subheader("📈 Live Latency Graph")
            st.line_chart(df.set_index("sample")[["latency_ms"]])

        with c2:
            st.subheader("⚡ Live Speed Graph")
            st.line_chart(df.set_index("sample")[["speed"]])

        c3, c4 = st.columns(2)

        with c3:
            st.subheader("🔋 Battery Trend")
            st.area_chart(df.set_index("sample")[["battery"]])

        with c4:
            st.subheader("🚨 Threat Events")
            st.bar_chart(df.set_index("sample")[["threat"]])

        c5, c6 = st.columns(2)

        with c5:
            st.subheader("📉 Packet Loss")
            st.line_chart(df.set_index("sample")[["packet_loss"]])

        with c6:
            st.subheader("🌊 Jitter")
            st.line_chart(df.set_index("sample")[["jitter"]])

        st.divider()

        if attack_count > 0:
            st.error("🚨 Cyber Attack Alert: Abnormal telemetry detected")
        else:
            st.success("✅ System Normal: No active cyber threat detected")

        st.subheader("📋 Recent Telemetry Logs")
        st.dataframe(df.tail(12), use_container_width=True)

    time.sleep(1)
