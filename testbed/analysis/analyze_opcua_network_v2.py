#!/usr/bin/env python3

import csv
import statistics
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

MANIFEST = (
    ROOT
    / "testbed/results/audit/"
    / "opcua_docker_v2_authoritative.csv"
)

OUTPUT_DIR = (
    ROOT
    / "testbed/results/opcua/analysis_v2"
)

RUN_SUMMARY = OUTPUT_DIR / "opcua_network_runs_v2.csv"
GROUP_SUMMARY = OUTPUT_DIR / "opcua_network_summary_v2.csv"


def read_csv(path):
    with path.open(
        newline="",
        encoding="utf-8",
        errors="replace",
    ) as f:
        return list(csv.DictReader(f))


def write_csv(path, rows):
    if not rows:
        raise RuntimeError(f"No rows for {path}")

    with path.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=list(rows[0].keys()),
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def parse_timestamp(value):
    return datetime.fromisoformat(
        value.replace("Z", "+00:00")
    )


def mean(values):
    return statistics.mean(values) if values else 0.0


def stdev(values):
    return (
        statistics.stdev(values)
        if len(values) > 1
        else 0.0
    )


def load_resource_metrics(path):
    rows = read_csv(path)

    running = [
        row
        for row in rows
        if row.get("source") == "container"
        and row.get("status") == "running"
    ]

    components = defaultdict(list)

    for row in running:
        component = row.get("component", "")

        try:
            cpu = float(row.get("cpu_percent", ""))
        except (TypeError, ValueError):
            cpu = None

        try:
            memory = float(row.get("memory_mb", ""))
        except (TypeError, ValueError):
            memory = None

        if component:
            components[component].append(
                (cpu, memory)
            )

    result = {}

    for component in (
        "opcua_server",
        "opcua_client",
    ):
        values = components.get(component, [])

        cpus = [
            cpu
            for cpu, _ in values
            if cpu is not None
        ]

        memories = [
            memory
            for _, memory in values
            if memory is not None
        ]

        result[
            f"{component}_cpu_mean_percent"
        ] = mean(cpus)

        result[
            f"{component}_memory_mean_mb"
        ] = mean(memories)

    return result


manifest = read_csv(MANIFEST)

if len(manifest) != 36:
    raise RuntimeError(
        f"Expected 36 authoritative OPC UA runs, "
        f"found {len(manifest)}"
    )

run_rows = []

for item in manifest:
    run_id = item["run_id"]

    sample_path = ROOT / item["samples_csv"]
    resource_path = ROOT / item["resource_csv"]

    samples = read_csv(sample_path)

    if not samples:
        raise RuntimeError(
            f"No samples for {run_id}"
        )

    latencies = [
        float(row["latency_ms"])
        for row in samples
    ]

    jitters = [
        float(row["jitter_ms"])
        for row in samples
    ]

    payload_bytes = [
        int(float(row["payload_bytes"]))
        for row in samples
    ]

    timestamps = [
        parse_timestamp(row["timestamp"])
        for row in samples
    ]

    span_s = (
        max(timestamps) - min(timestamps)
    ).total_seconds()

    if span_s <= 0:
        raise RuntimeError(
            f"Invalid sample span for {run_id}"
        )

    throughput_msg_s = (
        len(samples) / span_s
    )

    payload_throughput_kbps = (
        sum(payload_bytes)
        * 8.0
        / span_s
        / 1000.0
    )

    resource_metrics = load_resource_metrics(
        resource_path
    )

    run_row = {
        "run_id": run_id,
        "security_level":
            item["security_level"],
        "net_profile":
            item["network_profile"],
        "repeat_index":
            item["repeat"],
        "sample_count":
            len(samples),
        "sample_span_s":
            f"{span_s:.6f}",
        "latency_mean_ms":
            f"{mean(latencies):.6f}",
        "latency_stdev_ms":
            f"{stdev(latencies):.6f}",
        "latency_max_ms":
            f"{max(latencies):.6f}",
        "jitter_mean_ms":
            f"{mean(jitters):.6f}",
        "jitter_stdev_ms":
            f"{stdev(jitters):.6f}",
        "throughput_mean_msg_s":
            f"{throughput_msg_s:.6f}",
        "payload_throughput_kbps":
            f"{payload_throughput_kbps:.6f}",
        "opcua_server_cpu_mean_percent":
            f"{resource_metrics['opcua_server_cpu_mean_percent']:.6f}",
        "opcua_server_memory_mean_mb":
            f"{resource_metrics['opcua_server_memory_mean_mb']:.6f}",
        "opcua_client_cpu_mean_percent":
            f"{resource_metrics['opcua_client_cpu_mean_percent']:.6f}",
        "opcua_client_memory_mean_mb":
            f"{resource_metrics['opcua_client_memory_mean_mb']:.6f}",
        "provenance_class":
            "docker_v2_authoritative",
    }

    run_rows.append(run_row)


groups = defaultdict(list)

for row in run_rows:
    groups[
        (
            row["security_level"],
            row["net_profile"],
        )
    ].append(row)


group_rows = []

for (level, profile), rows in sorted(
    groups.items()
):
    if len(rows) != 3:
        raise RuntimeError(
            f"{level}/{profile}: "
            f"expected 3 repeats, found {len(rows)}"
        )

    def values(field):
        return [
            float(row[field])
            for row in rows
        ]

    group_rows.append({
        "protocol": "OPC UA",
        "security_level": level,
        "net_profile": profile,
        "runs": len(rows),

        "latency_mean_ms":
            f"{mean(values('latency_mean_ms')):.6f}",
        "latency_between_run_sd_ms":
            f"{stdev(values('latency_mean_ms')):.6f}",

        "jitter_mean_ms":
            f"{mean(values('jitter_mean_ms')):.6f}",
        "jitter_between_run_sd_ms":
            f"{stdev(values('jitter_mean_ms')):.6f}",

        "throughput_mean_msg_s":
            f"{mean(values('throughput_mean_msg_s')):.6f}",
        "throughput_between_run_sd_msg_s":
            f"{stdev(values('throughput_mean_msg_s')):.6f}",

        "payload_throughput_mean_kbps":
            f"{mean(values('payload_throughput_kbps')):.6f}",

        "server_cpu_mean_percent":
            f"{mean(values('opcua_server_cpu_mean_percent')):.6f}",
        "server_memory_mean_mb":
            f"{mean(values('opcua_server_memory_mean_mb')):.6f}",

        "client_cpu_mean_percent":
            f"{mean(values('opcua_client_cpu_mean_percent')):.6f}",
        "client_memory_mean_mb":
            f"{mean(values('opcua_client_memory_mean_mb')):.6f}",

        "provenance_class":
            "docker_v2_authoritative",
    })


OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

write_csv(RUN_SUMMARY, run_rows)
write_csv(GROUP_SUMMARY, group_rows)

print("=== OPC UA NETWORK ANALYSIS V2 ===")
print("Authoritative runs:", len(run_rows))
print("Grouped cells:", len(group_rows))
print("Run summary:", RUN_SUMMARY)
print("Grouped summary:", GROUP_SUMMARY)

print("\n=== GROUP SUMMARY ===")

for row in group_rows:
    print(
        row["security_level"],
        "|",
        row["net_profile"],
        "| latency=",
        row["latency_mean_ms"],
        "ms | jitter=",
        row["jitter_mean_ms"],
        "ms | throughput=",
        row["throughput_mean_msg_s"],
        "msg/s",
    )

print("\nANALYSIS VERDICT: PASS")
