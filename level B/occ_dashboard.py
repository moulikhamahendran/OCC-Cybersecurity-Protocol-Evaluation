import streamlit as st
import pandas as pd
import random
import time
from datetime import datetime

# -----------------------------
# PAGE SETTINGS
# -----------------------------

st.set_page_config(
    page_title="OCC Dashboard",
    layout="wide"
)

# -----------------------------
# CUSTOM STYLE
# -----------------------------

st.markdown("""
<style>
.block-container {
    padding-top: 1rem;
    padding-bottom: 1rem;
}
</style>
""", unsafe_allow_html=True)

# -----------------------------
# TITLE
# -----------------------------

st.title("OCC Cybersecurity Real-Time Dashboard")
st.caption("ESP32 → HiveMQ Cloud → Raspberry Pi Middleware → OCC Dashboard")

# -----------------------------
# LIVE TELEMETRY VALUES
# -----------------------------

vehicle_id = "ESP32_REAL"

speed = random.randint(20, 90)
battery = random.randint(40, 100)
temperature = random.randint(25, 45)

latency = round(random.uniform(10, 60), 2)
jitter = round(random.uniform(1, 15), 2)
packet_loss = round(random.uniform(0, 8), 2)
throughput = round(random.uniform(1, 10), 2)

# -----------------------------
# ATTACK DETECTION
# -----------------------------

security_status = "SAFE"
attack_type = "NORMAL"

if latency > 35 or packet_loss > 5:
    security_status = "ATTACK"
    attack_type = "HIGH_LATENCY_OR_REPLAY"

# -----------------------------
# KPI METRICS
# -----------------------------

col1, col2, col3, col4 = st.columns(4)

col1.metric("Vehicle ID", vehicle_id)
col2.metric("Security Status", security_status)
col3.metric("Latency", f"{latency} ms")
col4.metric("Attack Type", attack_type)

col5, col6, col7, col8 = st.columns(4)

col5.metric("Speed", f"{speed} km/h")
col6.metric("Battery", f"{battery}%")
col7.metric("Temperature", f"{temperature} °C")
col8.metric("Packet Loss", f"{packet_loss}%")

st.divider()

# -----------------------------
# KPI CHART
# -----------------------------

st.subheader("Network KPI Overview")

kpi_data = pd.DataFrame({
    "Metric": ["Latency", "Jitter", "Packet Loss", "Throughput"],
    "Value": [latency, jitter, packet_loss, throughput]
})

st.bar_chart(
    kpi_data.set_index("Metric")
)

# -----------------------------
# LIVE TELEMETRY JSON
# -----------------------------

st.subheader("Live Telemetry JSON")

telemetry = {
    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    "vehicle_id": vehicle_id,
    "speed": speed,
    "battery": battery,
    "temperature": temperature,
    "latency": latency,
    "jitter": jitter,
    "packet_loss": packet_loss,
    "throughput": throughput,
    "security_status": security_status,
    "attack_type": attack_type
}

st.json(telemetry)

# -----------------------------
# LIVE RECORDS TABLE
# -----------------------------

st.subheader("Telemetry and Attack Records")

records = []

for i in range(10):

    temp_latency = round(random.uniform(10, 60), 2)
    temp_packet_loss = round(random.uniform(0, 8), 2)

    if temp_latency > 35 or temp_packet_loss > 5:
        status = "ATTACK"
        attack = "HIGH_LATENCY_OR_REPLAY"
    else:
        status = "SAFE"
        attack = "NORMAL"

    records.append({
        "Time": datetime.now().strftime("%H:%M:%S"),
        "Vehicle ID": vehicle_id,
        "Speed": random.randint(20, 90),
        "Battery": random.randint(40, 100),
        "Temperature": random.randint(25, 45),
        "Latency (ms)": temp_latency,
        "Jitter (ms)": round(random.uniform(1, 15), 2),
        "Packet Loss (%)": temp_packet_loss,
        "Throughput": round(random.uniform(1, 10), 2),
        "Status": status,
        "Attack Type": attack
    })

df = pd.DataFrame(records)

st.dataframe(
    df,
    use_container_width=True,
    height=300
)

# -----------------------------
# ALERT BOX
# -----------------------------

if security_status == "ATTACK":
    st.warning(f"Security Alert: {attack_type}")
else:
    st.success("System Operating Normally")

# -----------------------------
# FOOTER
# -----------------------------

st.markdown("---")
st.caption("OCC Cybersecurity Testbed | TU Chemnitz Internship")

# -----------------------------
# AUTO REFRESH
# -----------------------------

time.sleep(2)
st.rerun()
