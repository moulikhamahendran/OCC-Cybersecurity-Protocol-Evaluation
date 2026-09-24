import csv
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import serial

PORT = "/dev/cu.usbserial-0001"
BAUD = 115200
DURATION = 60.0

if len(sys.argv) != 3:
    raise SystemExit("Usage: python3 capture_mqtt_run.py C0 1")

profile = sys.argv[1].upper()
repeat = int(sys.argv[2])

stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
run_id = f"esp32_{profile.lower()}_formal_repeat_{repeat}_{stamp}"

outdir = Path("testbed/results/hardware/esp32_mqtt") / profile
outdir.mkdir(parents=True, exist_ok=True)

csv_path = outdir / f"{run_id}.csv"
raw_path = outdir / f"{run_id}.log"

print(f"RUN_ID={run_id}")
print(f"PORT={PORT}")
print(f"DURATION={DURATION}s")
print("Waiting for ESP32 startup/MQTT connection...")

ser = serial.Serial(PORT, BAUD, timeout=1)

# Trigger a clean reset when possible.
ser.dtr = False
ser.rts = True
time.sleep(0.1)
ser.rts = False

connected = False
start = None
records = []

with raw_path.open("w") as raw:
    while True:
        line = ser.readline().decode("utf-8", errors="replace").strip()

        if line:
            print(line)
            raw.write(line + "\n")
            raw.flush()

        if not connected:
            if line == "MQTT connected":
                connected = True
                start = time.monotonic()
                print("=== FORMAL CAPTURE START ===")
            continue

        elapsed = time.monotonic() - start

        if line.startswith("ACK,"):
            parts = line.split(",")
            if len(parts) == 4:
                try:
                    records.append({
                        "run_id": run_id,
                        "profile": profile,
                        "repeat": repeat,
                        "elapsed_s": round(elapsed, 6),
                        "sequence": int(parts[1]),
                        "ack_rtt_ms": float(parts[2]),
                        "payload_bytes": int(parts[3]),
                    })
                except ValueError:
                    pass

        if elapsed >= DURATION:
            break

ser.close()

with csv_path.open("w", newline="") as f:
    writer = csv.DictWriter(
        f,
        fieldnames=[
            "run_id",
            "profile",
            "repeat",
            "elapsed_s",
            "sequence",
            "ack_rtt_ms",
            "payload_bytes",
        ],
    )
    writer.writeheader()
    writer.writerows(records)

print("=== FORMAL CAPTURE COMPLETE ===")
print(f"ACK_COUNT={len(records)}")
print(f"CSV={csv_path}")
print(f"RAW_LOG={raw_path}")
