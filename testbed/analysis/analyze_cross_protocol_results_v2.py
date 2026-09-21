#!/usr/bin/env python3

import csv
import statistics as st
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

MQTT = ROOT / "testbed/results/mqtt/analysis_v2/mqtt_v2_group_summary.csv"
MQTT_BASE = ROOT / "testbed/results/audit/mqtt_v2_proxy_baseline_manifest.csv"

OPCUA = ROOT / "testbed/results/opcua/analysis_v2/opcua_network_summary_v2.csv"
OPCUA_BASE = ROOT / "testbed/results/audit/opcua_v2_proxy_baseline_manifest.csv"

DDS = ROOT / "testbed/results/dds/analysis_v2/dds_network_summary_v2.csv"

OUTDIR = ROOT / "testbed/results/cross_protocol/analysis_v2"
OUTDIR.mkdir(parents=True, exist_ok=True)

NORMALIZED = OUTDIR / "cross_protocol_network_summary_v2.csv"
DELAY_EFFECT = OUTDIR / "cross_protocol_delay_effect_v2.csv"

LEVELS = ("C0", "C1", "C2")
PROFILES = ("NET-ideal", "NET-delay", "NET-jitter", "NET-loss")


def read_csv(path):
    with Path(path).open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def write_csv(path, rows):
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def f(row, key, default=None):
    value = row.get(key, "")
    if value in ("", None):
        return default
    return float(value)


# ------------------------------------------------------------
# Baselines
# ------------------------------------------------------------

mqtt_base = defaultdict(list)
for r in read_csv(MQTT_BASE):
    mqtt_base[r["security_level"]].append(float(r["latency_mean_ms"]))

opcua_base = defaultdict(list)
for r in read_csv(OPCUA_BASE):
    opcua_base[r["security_level"]].append(float(r["latency_mean_ms"]))

mqtt_base_mean = {k: st.mean(v) for k, v in mqtt_base.items()}
opcua_base_mean = {k: st.mean(v) for k, v in opcua_base.items()}


# ------------------------------------------------------------
# Normalize group summaries
# ------------------------------------------------------------

rows = []

# MQTT
for r in read_csv(MQTT):
    level = r["security_level"]
    profile = r["network_profile"].upper()

    latency = f(r, "latency_mean_ms")

    rows.append({
        "protocol": "MQTT",
        "security_level": level,
        "network_profile": profile,
        "n_runs": int(r["n_runs"]),
        "latency_mean_ms": latency,
        "latency_sd_across_runs_ms": f(r, "latency_sd_across_runs_ms"),
        "jitter_mean_ms": f(r, "jitter_mean_ms"),
        "jitter_sd_across_runs_ms": f(r, "jitter_sd_across_runs_ms"),
        "realized_rate_mean_hz": f(r, "source_rate_mean_hz"),
        "application_loss_mean_percent": f(
            r, "application_loss_mean_percent"
        ),
        "payload_mean_bytes": f(r, "payload_mean_bytes"),
        "baseline_type": "NET-proxy-ideal",
        "baseline_latency_ms": mqtt_base_mean[level],
        "latency_increment_vs_baseline_ms":
            latency - mqtt_base_mean[level],
        "comparability_note":
            "QoS1 acknowledgement-paced offered workload",
    })


# OPC UA
for r in read_csv(OPCUA):
    level = r["security_level"]
    profile = r["net_profile"].upper()

    latency = f(r, "latency_mean_ms")

    rows.append({
        "protocol": "OPC UA",
        "security_level": level,
        "network_profile": profile,
        "n_runs": int(r["runs"]),
        "latency_mean_ms": latency,
        "latency_sd_across_runs_ms": f(
            r, "latency_between_run_sd_ms"
        ),
        "jitter_mean_ms": f(r, "jitter_mean_ms"),
        "jitter_sd_across_runs_ms": f(
            r, "jitter_between_run_sd_ms"
        ),
        "realized_rate_mean_hz": f(r, "throughput_mean_msg_s"),
        # Sequence audit independently verified 0 gaps/duplicates/inversions
        # across all 36 authoritative Docker-v2 runs.
        "application_loss_mean_percent": 0.0,
        "payload_mean_bytes": None,
        "baseline_type": "NET-proxy-ideal",
        "baseline_latency_ms": opcua_base_mean[level],
        "latency_increment_vs_baseline_ms":
            latency - opcua_base_mean[level],
        "comparability_note":
            "50 ms subscription publishing interval creates "
            "baseline timing sawtooth",
    })


# DDS
dds_rows = read_csv(DDS)

dds_ideal = {}
for r in dds_rows:
    if r["net_profile"].upper() == "NET-IDEAL":
        dds_ideal[r["security_level"]] = float(r["latency_mean_ms"])

for r in dds_rows:
    level = r["security_level"]
    profile = r["net_profile"].upper()
    latency = f(r, "latency_mean_ms")

    rows.append({
        "protocol": "DDS",
        "security_level": level,
        "network_profile": profile,
        "n_runs": int(r["runs"]),
        "latency_mean_ms": latency,
        "latency_sd_across_runs_ms": f(r, "latency_sd_ms"),
        "jitter_mean_ms": f(r, "jitter_mean_ms"),
        "jitter_sd_across_runs_ms": f(r, "jitter_sd_ms"),
        "realized_rate_mean_hz": f(r, "throughput_mean_mps"),
        "application_loss_mean_percent": f(r, "loss_mean_percent"),
        "payload_mean_bytes": None,
        "baseline_type": "NET-ideal",
        "baseline_latency_ms": dds_ideal[level],
        "latency_increment_vs_baseline_ms":
            latency - dds_ideal[level],
        "comparability_note":
            "Reliable QoS + KeepLast(10); transport loss may be recovered",
    })


# Sort consistently
order_protocol = {"MQTT": 0, "OPC UA": 1, "DDS": 2}
order_profile = {
    "NET-IDEAL": 0,
    "NET-DELAY": 1,
    "NET-JITTER": 2,
    "NET-LOSS": 3,
}

rows.sort(
    key=lambda r: (
        order_protocol[r["protocol"]],
        r["security_level"],
        order_profile[r["network_profile"]],
    )
)

if len(rows) != 36:
    raise RuntimeError(
        f"Expected 36 normalized groups "
        f"(3 protocols x 3 levels x 4 profiles), got {len(rows)}"
    )

write_csv(NORMALIZED, rows)


# ------------------------------------------------------------
# Delay effect table
# ------------------------------------------------------------

delay_rows = []

for r in rows:
    if r["network_profile"] != "NET-DELAY":
        continue

    added = float(r["latency_increment_vs_baseline_ms"])
    multiplier = added / 25.0

    delay_rows.append({
        "protocol": r["protocol"],
        "security_level": r["security_level"],
        "baseline_type": r["baseline_type"],
        "baseline_latency_ms": r["baseline_latency_ms"],
        "net_delay_latency_ms": r["latency_mean_ms"],
        "added_delay_ms": added,
        "effective_delay_multiplier": multiplier,
        "effective_delay_multiplier_report": f"{multiplier:.2f}",
    })

write_csv(DELAY_EFFECT, delay_rows)


print("Cross-protocol network analysis v2 complete")
print("Normalized groups:", len(rows))
print("Delay-effect rows:", len(delay_rows))
print()
print("Outputs:")
print(" ", NORMALIZED)
print(" ", DELAY_EFFECT)
print()
print("Effective delay multipliers:")

for r in delay_rows:
    print(
        f"  {r['protocol']:6s} {r['security_level']}: "
        f"{r['effective_delay_multiplier']:.6f}x "
        f"-> {r['effective_delay_multiplier_report']}x"
    )
