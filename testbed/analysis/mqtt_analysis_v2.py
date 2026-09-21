#!/usr/bin/env python3

import csv
import math
import statistics as st
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

MANIFEST = ROOT / "testbed/results/audit/mqtt_common_core_authoritative.csv"
BASELINE_MANIFEST = ROOT / "testbed/results/audit/mqtt_v2_proxy_baseline_manifest.csv"

OUTDIR = ROOT / "testbed/results/mqtt/analysis_v2"
OUTDIR.mkdir(parents=True, exist_ok=True)

RUN_SUMMARY = OUTDIR / "mqtt_v2_run_summary.csv"
GROUP_SUMMARY = OUTDIR / "mqtt_v2_group_summary.csv"
DELAY_EFFECT = OUTDIR / "mqtt_v2_delay_effect.csv"


def read_csv(path):
    with Path(path).open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def mean(values):
    return st.mean(values) if values else float("nan")


def sample_sd(values):
    return st.stdev(values) if len(values) > 1 else 0.0


def safe_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def write_csv(path, rows):
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


manifest = read_csv(MANIFEST)

if len(manifest) != 36:
    raise RuntimeError(f"Expected 36 authoritative MQTT runs, got {len(manifest)}")

run_rows = []

for m in manifest:
    receipts = read_csv(ROOT / m["gateway_receipts_csv"])
    publisher = read_csv(ROOT / m["publisher_csv"])

    valid = [
        r for r in receipts
        if str(r.get("json_valid", "")).lower() in ("true", "1")
        and str(r.get("mqtt_duplicate", "")).lower() not in ("true", "1")
    ]

    latencies = []
    payload_bytes = []

    for r in valid:
        ts = safe_float(r.get("t_send_ns"))
        tr = safe_float(r.get("received_ns"))
        pb = safe_float(r.get("payload_bytes"))

        if ts is not None and tr is not None:
            latencies.append((tr - ts) / 1e6)

        if pb is not None:
            payload_bytes.append(pb)

    jitters = [
        abs(latencies[i] - latencies[i - 1])
        for i in range(1, len(latencies))
    ]

    attempts = [
        r for r in publisher
        if str(r.get("status", "")).upper() == "ATTEMPT"
    ]

    if not attempts:
        seen = {}
        for r in publisher:
            hid = r.get("header_id")
            if hid not in seen:
                seen[hid] = r
        attempts = list(seen.values())

    send_times = []
    for r in attempts:
        t = safe_float(r.get("t_send_ns"))
        if t is not None:
            send_times.append(t / 1e9)

    send_times = sorted(set(send_times))

    source_span_s = (
        send_times[-1] - send_times[0]
        if len(send_times) > 1
        else None
    )

    source_rate_hz = (
        (len(send_times) - 1) / source_span_s
        if source_span_s and source_span_s > 0
        else float("nan")
    )

    receipt_span_s = safe_float(m.get("receipt_span_s"))

    receive_rate_hz = (
        (len(valid) - 1) / receipt_span_s
        if receipt_span_s and receipt_span_s > 0 and len(valid) > 1
        else float("nan")
    )

    generated_ids = {
        r.get("header_id")
        for r in attempts
        if r.get("header_id") not in (None, "")
    }

    received_ids = {
        r.get("header_id")
        for r in valid
        if r.get("header_id") not in (None, "")
    }

    lost_ids = generated_ids - received_ids

    application_loss_pct = (
        len(lost_ids) / len(generated_ids) * 100
        if generated_ids else float("nan")
    )

    run_rows.append({
        "security_level": m["security_level"],
        "network_profile": m["network_profile"],
        "repeat": m["repeat"],
        "run_id": m["run_id"],
        "generated_messages": len(generated_ids),
        "received_messages": len(received_ids),
        "application_lost_messages": len(lost_ids),
        "application_loss_percent": application_loss_pct,
        "source_rate_hz": source_rate_hz,
        "receive_rate_hz": receive_rate_hz,
        "latency_mean_ms": mean(latencies),
        "latency_sd_ms": sample_sd(latencies),
        "jitter_mean_ms": mean(jitters),
        "jitter_sd_ms": sample_sd(jitters),
        "payload_mean_bytes": mean(payload_bytes),
        "payload_sd_bytes": sample_sd(payload_bytes),
        "resource_rows": m["resource_rows"],
        "resource_span_s": m["resource_span_s"],
        "netem_run_status": m["netem_run_status"],
        "netem_verified_before": m["netem_verified_before"],
        "netem_verified_after": m["netem_verified_after"],
        "provenance_class": m["provenance_class"],
    })

write_csv(RUN_SUMMARY, run_rows)


groups = defaultdict(list)

for r in run_rows:
    groups[(r["security_level"], r["network_profile"])].append(r)

group_rows = []

for (level, profile), rows in sorted(groups.items()):
    def vals(field):
        return [
            float(r[field])
            for r in rows
            if r[field] not in ("", None)
            and not math.isnan(float(r[field]))
        ]

    group_rows.append({
        "security_level": level,
        "network_profile": profile,
        "n_runs": len(rows),

        "latency_mean_ms": mean(vals("latency_mean_ms")),
        "latency_sd_across_runs_ms": sample_sd(vals("latency_mean_ms")),

        "jitter_mean_ms": mean(vals("jitter_mean_ms")),
        "jitter_sd_across_runs_ms": sample_sd(vals("jitter_mean_ms")),

        "source_rate_mean_hz": mean(vals("source_rate_hz")),
        "source_rate_sd_hz": sample_sd(vals("source_rate_hz")),

        "receive_rate_mean_hz": mean(vals("receive_rate_hz")),
        "receive_rate_sd_hz": sample_sd(vals("receive_rate_hz")),

        "application_loss_mean_percent": mean(vals("application_loss_percent")),
        "application_loss_sd_percent": sample_sd(vals("application_loss_percent")),

        "payload_mean_bytes": mean(vals("payload_mean_bytes")),
        "payload_sd_across_runs_bytes": sample_sd(vals("payload_mean_bytes")),
    })

write_csv(GROUP_SUMMARY, group_rows)


baseline_rows = read_csv(BASELINE_MANIFEST)

baseline_by_level = defaultdict(list)

for r in baseline_rows:
    baseline_by_level[r["security_level"]].append(
        float(r["latency_mean_ms"])
    )

delay_by_level = defaultdict(list)

for r in run_rows:
    if r["network_profile"].lower() == "net-delay":
        delay_by_level[r["security_level"]].append(
            float(r["latency_mean_ms"])
        )

effect_rows = []

for level in ("C0", "C1", "C2"):
    baseline = baseline_by_level[level]
    delay = delay_by_level[level]

    if len(baseline) != 3 or len(delay) != 3:
        raise RuntimeError(
            f"{level}: expected 3 baseline and 3 delay runs, "
            f"got {len(baseline)} and {len(delay)}"
        )

    baseline_mean = mean(baseline)
    baseline_sd = sample_sd(baseline)

    delay_mean = mean(delay)
    delay_sd = sample_sd(delay)

    added_delay = delay_mean - baseline_mean
    multiplier = added_delay / 25.0

    se_difference = math.sqrt(
        (delay_sd ** 2 + baseline_sd ** 2) / 3
    )

    se_multiplier = se_difference / 25.0

    effect_rows.append({
        "security_level": level,
        "baseline_type": "NET-proxy-ideal",
        "baseline_mean_ms": baseline_mean,
        "baseline_sd_ms": baseline_sd,
        "net_delay_mean_ms": delay_mean,
        "net_delay_sd_ms": delay_sd,
        "added_delay_ms": added_delay,
        "effective_delay_multiplier": multiplier,
        "effective_delay_multiplier_report": f"{multiplier:.2f}",
        "descriptive_se_multiplier": se_multiplier,
        "n_baseline": 3,
        "n_delay": 3,
    })

write_csv(DELAY_EFFECT, effect_rows)


print("MQTT analysis_v2 complete")
print("Authoritative runs:", len(run_rows))
print("Groups:", len(group_rows))
print()
print("Outputs:")
print(" ", RUN_SUMMARY)
print(" ", GROUP_SUMMARY)
print(" ", DELAY_EFFECT)
print()
print("Effective delay multipliers:")
for r in effect_rows:
    print(
        f"  {r['security_level']}: "
        f"{r['effective_delay_multiplier']:.6f}x "
        f"-> report {r['effective_delay_multiplier_report']}x"
    )
