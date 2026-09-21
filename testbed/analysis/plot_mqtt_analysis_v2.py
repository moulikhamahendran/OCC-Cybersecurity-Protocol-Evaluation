#!/usr/bin/env python3

import csv
from pathlib import Path
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "testbed/results/mqtt/analysis_v2/mqtt_v2_group_summary.csv"
OUT = ROOT / "testbed/results/mqtt/analysis_v2/plots"
OUT.mkdir(parents=True, exist_ok=True)

with DATA.open(newline="", encoding="utf-8") as f:
    rows = list(csv.DictReader(f))

levels = ["C0", "C1", "C2"]
profiles = ["net-ideal", "net-delay", "net-jitter", "net-loss"]

def get(level, profile, field):
    for r in rows:
        if (
            r["security_level"] == level
            and r["network_profile"].lower() == profile
        ):
            return float(r[field])
    raise KeyError((level, profile, field))

def grouped_plot(field, ylabel, title, filename):
    x = list(range(len(profiles)))
    width = 0.24

    plt.figure(figsize=(10, 5))

    for i, level in enumerate(levels):
        vals = [get(level, p, field) for p in profiles]
        pos = [v + (i - 1) * width for v in x]
        plt.bar(pos, vals, width=width, label=level)

    plt.xticks(x, ["Ideal", "Delay", "Jitter", "Loss"])
    plt.ylabel(ylabel)
    plt.title(title)
    plt.legend()
    plt.tight_layout()
    plt.savefig(OUT / filename, dpi=180)
    plt.close()

grouped_plot(
    "latency_mean_ms",
    "Latency (ms)",
    "MQTT Authoritative Mean Latency",
    "mqtt_v2_latency.png",
)

grouped_plot(
    "jitter_mean_ms",
    "Jitter (ms)",
    "MQTT Authoritative Mean Jitter",
    "mqtt_v2_jitter.png",
)

grouped_plot(
    "source_rate_mean_hz",
    "Realized Source Rate (Hz)",
    "MQTT Realized Offered Workload",
    "mqtt_v2_source_rate.png",
)

plt.figure(figsize=(10, 5))
plt.axhline(0, linewidth=1)
plt.xticks(range(len(profiles)), ["Ideal", "Delay", "Jitter", "Loss"])
plt.ylabel("Application Loss (%)")
plt.title("MQTT Application-Level Loss")
plt.ylim(-0.05, 0.05)
plt.text(
    1.5, 0.012,
    "0% application-level loss in all 12 authoritative groups",
    ha="center",
    fontsize=11,
)
plt.tight_layout()
plt.savefig(OUT / "mqtt_v2_application_loss.png", dpi=180)
plt.close()

print("Saved plots to:", OUT)
for p in sorted(OUT.glob("*.png")):
    print(" ", p)
