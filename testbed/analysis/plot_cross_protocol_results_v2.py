#!/usr/bin/env python3

import csv
from pathlib import Path
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]

SUMMARY = ROOT / "testbed/results/cross_protocol/analysis_v2/cross_protocol_network_summary_v2.csv"
DELAY = ROOT / "testbed/results/cross_protocol/analysis_v2/cross_protocol_delay_effect_v2.csv"

OUT = ROOT / "testbed/results/cross_protocol/analysis_v2/plots"
OUT.mkdir(parents=True, exist_ok=True)

with SUMMARY.open(newline="", encoding="utf-8") as f:
    rows = list(csv.DictReader(f))

with DELAY.open(newline="", encoding="utf-8") as f:
    delay_rows = list(csv.DictReader(f))

protocols = ["MQTT", "OPC UA", "DDS"]
levels = ["C0", "C1", "C2"]
profiles = ["NET-IDEAL", "NET-DELAY", "NET-JITTER", "NET-LOSS"]

def get(protocol, level, profile, field):
    for r in rows:
        if (
            r["protocol"] == protocol
            and r["security_level"] == level
            and r["network_profile"] == profile
        ):
            v = r.get(field, "")
            return None if v in ("", None) else float(v)
    raise KeyError((protocol, level, profile, field))

# 1. Delay multiplier
plt.figure(figsize=(10, 5))
x = range(len(protocols))
width = 0.24

for i, level in enumerate(levels):
    vals = []
    for protocol in protocols:
        for r in delay_rows:
            if r["protocol"] == protocol and r["security_level"] == level:
                vals.append(float(r["effective_delay_multiplier"]))
                break

    pos = [v + (i - 1) * width for v in x]
    plt.bar(pos, vals, width=width, label=level)

plt.xticks(list(x), protocols)
plt.ylabel("Effective Delay Multiplier")
plt.title("Cross-Protocol Effective Delay Multiplier")
plt.legend()
plt.tight_layout()
plt.savefig(OUT / "cross_protocol_delay_multiplier_v2.png", dpi=180)
plt.close()

# 2. Delay increment in ms
plt.figure(figsize=(10, 5))

for i, level in enumerate(levels):
    vals = []
    for protocol in protocols:
        for r in delay_rows:
            if r["protocol"] == protocol and r["security_level"] == level:
                vals.append(float(r["added_delay_ms"]))
                break

    pos = [v + (i - 1) * width for v in x]
    plt.bar(pos, vals, width=width, label=level)

plt.xticks(list(x), protocols)
plt.ylabel("Added Delay vs Protocol Baseline (ms)")
plt.title("Cross-Protocol Added Delay Under NET-delay")
plt.legend()
plt.tight_layout()
plt.savefig(OUT / "cross_protocol_added_delay_v2.png", dpi=180)
plt.close()

# 3. Realized rate under all profiles, C0 only for clean comparison
plt.figure(figsize=(10, 5))
x2 = range(len(profiles))

for i, protocol in enumerate(protocols):
    vals = [
        get(protocol, "C0", p, "realized_rate_mean_hz")
        for p in profiles
    ]
    pos = [v + (i - 1) * width for v in x2]
    plt.bar(pos, vals, width=width, label=protocol)

plt.xticks(list(x2), ["Ideal", "Delay", "Jitter", "Loss"])
plt.ylabel("Realized Rate (Hz)")
plt.title("Cross-Protocol Realized Rate — C0")
plt.legend()
plt.tight_layout()
plt.savefig(OUT / "cross_protocol_realized_rate_c0_v2.png", dpi=180)
plt.close()

# 4. Jitter under all profiles, C0 only
plt.figure(figsize=(10, 5))

for i, protocol in enumerate(protocols):
    vals = [
        get(protocol, "C0", p, "jitter_mean_ms")
        for p in profiles
    ]
    pos = [v + (i - 1) * width for v in x2]
    plt.bar(pos, vals, width=width, label=protocol)

plt.xticks(list(x2), ["Ideal", "Delay", "Jitter", "Loss"])
plt.ylabel("Mean Jitter (ms)")
plt.title("Cross-Protocol Mean Jitter — C0")
plt.legend()
plt.tight_layout()
plt.savefig(OUT / "cross_protocol_jitter_c0_v2.png", dpi=180)
plt.close()

# 5. Application loss under NET-loss
plt.figure(figsize=(10, 5))

vals = [
    get(protocol, "C0", "NET-LOSS", "application_loss_mean_percent")
    for protocol in protocols
]

plt.bar(protocols, vals)
plt.ylabel("Application-Level Loss (%)")
plt.title("Cross-Protocol Application-Level Loss — C0 / NET-loss")

if all(abs(v) < 1e-12 for v in vals):
    plt.ylim(-0.05, 0.05)
    plt.text(
        1,
        0.012,
        "0% application-level loss for all three protocols",
        ha="center",
        fontsize=11,
    )

plt.tight_layout()
plt.savefig(OUT / "cross_protocol_application_loss_c0_v2.png", dpi=180)
plt.close()

print("Saved cross-protocol plots:")
for p in sorted(OUT.glob("*.png")):
    print(" ", p)
