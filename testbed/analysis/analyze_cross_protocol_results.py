#!/usr/bin/env python3

import csv
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


PROJECT_DIR = Path(__file__).resolve().parents[2]
RESULTS_DIR = PROJECT_DIR / "testbed/results"
OUTPUT_DIR = RESULTS_DIR / "cross_protocol/analysis_v1"
PLOT_DIR = OUTPUT_DIR / "plots"

PROTOCOLS = ("MQTT", "OPC UA", "DDS")
SECURITY_LEVELS = ("C0", "C1", "C2")
COMMON_PROFILES = (
    "NET-ideal",
    "NET-delay",
    "NET-jitter",
    "NET-loss",
)

MQTT_NETWORK = RESULTS_DIR / "mqtt_final_network_summary.csv"
MQTT_ATTACKS = RESULTS_DIR / "mqtt_attack_summary.csv"
OPCUA_NETWORK = RESULTS_DIR / "opcua/opcua_final_network_summary.csv"
OPCUA_AVAILABILITY = (
    RESULTS_DIR / "opcua/opcua_final_availability_summary.csv"
)
OPCUA_SECURITY = (
    RESULTS_DIR / "opcua/opcua_security_control_summary.csv"
)
DDS_NETWORK = (
    RESULTS_DIR / "dds/analysis_v2/dds_network_summary_v2.csv"
)
DDS_DOS = (
    RESULTS_DIR
    / "dds/dos/analysis_v1/dds_dos_security_summary.csv"
)


def read_csv(path):
    if not path.exists():
        raise FileNotFoundError(path)

    with path.open(newline="", encoding="utf-8") as file:
        return list(csv.DictReader(file))


def write_csv(path, rows):
    if not rows:
        raise RuntimeError(f"No rows available for {path.name}")

    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def value(row, *keys, default=""):
    for key in keys:
        if key in row and row[key] != "":
            return row[key]
    return default


def floating(row, key):
    raw = row.get(key, "")
    return float(raw) if raw not in ("", None) else None


def normalize_network():
    unified = []

    for row in read_csv(MQTT_NETWORK):
        profile = row["network_profile"]

        if profile not in COMMON_PROFILES:
            continue

        unified.append(
            {
                "protocol": "MQTT",
                "security_level": row["security_level"],
                "network_profile": profile,
                "runs": "3",
                "latency_mean_ms": row["latency_mean_ms"],
                "latency_sd_ms": row["latency_sd_ms"],
                "jitter_mean_ms": row["jitter_mean_ms"],
                "jitter_sd_ms": row["jitter_sd_ms"],
                "throughput_mean_messages_per_second":
                    row["throughput_mean_messages_per_second"],
                "throughput_sd_messages_per_second":
                    row["throughput_sd_messages_per_second"],
                "throughput_mean_kbps":
                    row["throughput_mean_kbps"],
                "throughput_sd_kbps":
                    row["throughput_sd_kbps"],
                "max_latency_mean_ms": "",
                "loss_mean_percent": "",
            }
        )

    for row in read_csv(OPCUA_NETWORK):
        profile = row["net_profile"]

        if profile not in COMMON_PROFILES:
            continue

        unified.append(
            {
                "protocol": "OPC UA",
                "security_level": row["security_level"],
                "network_profile": profile,
                "runs": row["runs"],
                "latency_mean_ms": row["latency_mean_ms"],
                "latency_sd_ms": row["latency_std_ms"],
                "jitter_mean_ms": row["jitter_mean_ms"],
                "jitter_sd_ms": row["jitter_std_ms"],
                "throughput_mean_messages_per_second":
                    row["throughput_mean_msg_s"],
                "throughput_sd_messages_per_second":
                    row["throughput_std_msg_s"],
                "throughput_mean_kbps":
                    row["throughput_mean_kbps"],
                "throughput_sd_kbps":
                    row["throughput_std_kbps"],
                "max_latency_mean_ms":
                    row["max_latency_mean_ms"],
                "loss_mean_percent": "",
            }
        )

    for row in read_csv(DDS_NETWORK):
        profile = row["net_profile"]

        if profile not in COMMON_PROFILES:
            continue

        unified.append(
            {
                "protocol": "DDS",
                "security_level": row["security_level"],
                "network_profile": profile,
                "runs": row["runs"],
                "latency_mean_ms": row["latency_mean_ms"],
                "latency_sd_ms": row["latency_sd_ms"],
                "jitter_mean_ms": row["jitter_mean_ms"],
                "jitter_sd_ms": row["jitter_sd_ms"],
                "throughput_mean_messages_per_second":
                    row["throughput_mean_mps"],
                "throughput_sd_messages_per_second":
                    row["throughput_sd_mps"],
                "throughput_mean_kbps": "",
                "throughput_sd_kbps": "",
                "max_latency_mean_ms":
                    row["max_latency_mean_ms"],
                "loss_mean_percent":
                    row["loss_mean_percent"],
            }
        )

    expected = (
        len(PROTOCOLS)
        * len(SECURITY_LEVELS)
        * len(COMMON_PROFILES)
    )

    if len(unified) != expected:
        raise RuntimeError(
            f"Expected {expected} common network rows, "
            f"found {len(unified)}"
        )

    return sorted(
        unified,
        key=lambda row: (
            COMMON_PROFILES.index(row["network_profile"]),
            SECURITY_LEVELS.index(row["security_level"]),
            PROTOCOLS.index(row["protocol"]),
        ),
    )


def mqtt_security_rows():
    grouped = defaultdict(list)

    for row in read_csv(MQTT_ATTACKS):
        grouped[
            (row["security_level"], row["attack"])
        ].append(row)

    output = []

    for (level, attack), rows in sorted(grouped.items()):
        detected = sum(row["detected"] == "1" for row in rows)
        blocked = sum(int(row["block_events"]) for row in rows)
        flagged = sum(int(row["flag_events"]) for row in rows)

        output.append(
            {
                "protocol": "MQTT",
                "security_level": level,
                "control_test": attack,
                "runs": len(rows),
                "controls_passed": detected,
                "pass_rate_percent":
                    f"{detected / len(rows) * 100:.1f}",
                "expected_behavior": "DETECTED",
                "observed_behavior": "DETECTED",
                "block_events": blocked,
                "flag_events": flagged,
                "evidence_type":
                    "application detector and gateway enforcement",
            }
        )

    return output


def opcua_security_rows():
    output = []

    for row in read_csv(OPCUA_SECURITY):
        output.append(
            {
                "protocol": "OPC UA",
                "security_level": row["security_level"],
                "control_test": row["attack_type"],
                "runs": row["runs"],
                "controls_passed": row["controls_passed"],
                "pass_rate_percent": row["pass_rate_percent"],
                "expected_behavior": row["expected_outcome"],
                "observed_behavior": row["observed_outcome"],
                "block_events": "",
                "flag_events": "",
                "evidence_type":
                    "OPC UA authentication and authorization control",
            }
        )

    return output


def dds_security_rows():
    candidates = sorted(
        (
            RESULTS_DIR / "dds/security_controls"
        ).glob("*/summary.csv")
    )

    if not candidates:
        raise RuntimeError(
            "DDS security-control summary was not found"
        )

    source = candidates[-1]
    output = []

    for row in read_csv(source):
        output.append(
            {
                "protocol": "DDS",
                "security_level": "C2",
                "control_test": row["control_id"],
                "runs": "1",
                "controls_passed":
                    "1" if row["verdict"] == "PASS" else "0",
                "pass_rate_percent":
                    "100.0" if row["verdict"] == "PASS" else "0.0",
                "expected_behavior": row["description"],
                "observed_behavior": row["verdict"],
                "block_events": "",
                "flag_events": "",
                "evidence_type": row["evidence"],
            }
        )

    return output


def normalize_security():
    rows = (
        mqtt_security_rows()
        + opcua_security_rows()
        + dds_security_rows()
    )

    return sorted(
        rows,
        key=lambda row: (
            PROTOCOLS.index(row["protocol"]),
            SECURITY_LEVELS.index(row["security_level"]),
            row["control_test"],
        ),
    )


def normalize_availability():
    output = []

    mqtt_dos = [
        row
        for row in read_csv(MQTT_ATTACKS)
        if row["attack"] == "dos"
    ]

    for row in mqtt_dos:
        output.append(
            {
                "protocol": "MQTT",
                "security_level": row["security_level"],
                "scenario": "DoS detector test",
                "runs": "1",
                "latency_mean_ms": "",
                "jitter_mean_ms": "",
                "throughput_mean_messages_per_second": "",
                "loss_mean_percent": "",
                "attack_messages_mean": "",
                "result":
                    "DETECTED" if row["detected"] == "1"
                    else "NOT DETECTED",
                "comparison_scope":
                    "Detection/enforcement test; no comparable "
                    "availability KPI summary",
            }
        )

    for row in read_csv(OPCUA_AVAILABILITY):
        output.append(
            {
                "protocol": "OPC UA",
                "security_level": row["security_level"],
                "scenario": row["stress_profile"],
                "runs": row["runs"],
                "latency_mean_ms": row["latency_mean_ms"],
                "jitter_mean_ms": row["jitter_mean_ms"],
                "throughput_mean_messages_per_second":
                    row["throughput_mean_msg_s"],
                "loss_mean_percent": "",
                "attack_messages_mean": "",
                "result": "MEASURED",
                "comparison_scope":
                    "OPC UA connection, read or subscription stress",
            }
        )

    for row in read_csv(DDS_DOS):
        output.append(
            {
                "protocol": "DDS",
                "security_level": row["security_level"],
                "scenario":
                    "authorized-publisher application-layer flood",
                "runs": row["runs"],
                "latency_mean_ms": row["latency_ms_mean"],
                "jitter_mean_ms": row["jitter_ms_mean"],
                "throughput_mean_messages_per_second":
                    row[
                        "throughput_messages_per_second_mean"
                    ],
                "loss_mean_percent":
                    row["legitimate_loss_percent_mean"],
                "attack_messages_mean":
                    row["unexpected_attack_messages_mean"],
                "result":
                    f"IMPACTED {row['impacted_runs']}/{row['runs']}",
                "comparison_scope":
                    "Compromised authorized DDS publisher; "
                    "not an unauthenticated external attacker",
            }
        )

    return output


def metric_grid(network_rows, metric, ylabel, filename):
    figure, axes = plt.subplots(
        2,
        2,
        figsize=(12, 8),
        sharex=True,
    )
    colors = {
        "MQTT": "#1565C0",
        "OPC UA": "#EF6C00",
        "DDS": "#6A1B9A",
    }

    for axis, profile in zip(axes.flat, COMMON_PROFILES):
        profile_rows = [
            row
            for row in network_rows
            if row["network_profile"] == profile
        ]

        x_positions = list(range(len(SECURITY_LEVELS)))
        width = 0.24

        for protocol_index, protocol in enumerate(PROTOCOLS):
            values = []

            for level in SECURITY_LEVELS:
                match = next(
                    row
                    for row in profile_rows
                    if row["protocol"] == protocol
                    and row["security_level"] == level
                )
                metric_value = floating(match, metric)
                values.append(
                    metric_value
                    if metric_value is not None
                    else 0.0
                )

            offsets = [
                position
                + (protocol_index - 1) * width
                for position in x_positions
            ]

            axis.bar(
                offsets,
                values,
                width=width,
                label=protocol,
                color=colors[protocol],
            )

        axis.set_title(profile)
        axis.set_xticks(x_positions, SECURITY_LEVELS)
        axis.set_ylabel(ylabel)
        axis.grid(axis="y", alpha=0.25)

    handles, labels = axes[0][0].get_legend_handles_labels()
    figure.legend(
        handles,
        labels,
        loc="upper center",
        ncol=3,
    )
    figure.suptitle(
        f"Cross-protocol {ylabel.lower()} comparison",
        y=0.99,
    )
    figure.tight_layout(rect=(0, 0, 1, 0.94))
    figure.savefig(PLOT_DIR / filename, dpi=200)
    plt.close(figure)


def baseline_table(network_rows):
    rows = [
        row
        for row in network_rows
        if row["network_profile"] == "NET-ideal"
    ]

    return sorted(
        rows,
        key=lambda row: (
            PROTOCOLS.index(row["protocol"]),
            SECURITY_LEVELS.index(row["security_level"]),
        ),
    )


def create_report(network_rows, security_rows, availability_rows):
    baseline = baseline_table(network_rows)

    security_totals = {}

    for protocol in PROTOCOLS:
        rows = [
            row
            for row in security_rows
            if row["protocol"] == protocol
        ]
        runs = sum(int(row["runs"]) for row in rows)
        passed = sum(
            int(row["controls_passed"])
            for row in rows
        )
        security_totals[protocol] = (
            len(rows),
            runs,
            passed,
        )

    lines = [
        "# MQTT–OPC UA–DDS Cross-Protocol Analysis",
        "",
        "## Comparison boundary",
        "",
        "- Direct performance comparison uses only NET-ideal, NET-delay, NET-jitter and NET-loss.",
        "- Each network cell represents three repetitions.",
        "- C0, C1 and C2 are functional security tiers; their protocol-specific mechanisms are not identical.",
        "- Absolute latency also includes implementation architecture, serialization and payload effects.",
        "- Attack and availability results are not numerically ranked when their threat models differ.",
        "",
        "## Ideal-network baseline",
        "",
        "| Protocol | Security | Latency (ms) | Jitter (ms) | Throughput (messages/s) |",
        "|---|---|---:|---:|---:|",
    ]

    for row in baseline:
        lines.append(
            f"| {row['protocol']} "
            f"| {row['security_level']} "
            f"| {float(row['latency_mean_ms']):.3f} "
            f"| {float(row['jitter_mean_ms']):.3f} "
            f"| {float(row['throughput_mean_messages_per_second']):.3f} |"
        )

    lines.extend(
        [
            "",
            "## Security-control validation",
            "",
            "| Protocol | Control/scenario summaries | Executions | Passed |",
            "|---|---:|---:|---:|",
        ]
    )

    for protocol in PROTOCOLS:
        summaries, runs, passed = security_totals[protocol]
        lines.append(
            f"| {protocol} | {summaries} | {runs} | {passed} |"
        )

    lines.extend(
        [
            "",
            "All recorded security-control scenarios produced their expected outcomes. This means the configured controls behaved correctly for the tested cases; it does not prove protection against every possible attack.",
            "",
            "## Availability interpretation",
            "",
            "- MQTT DoS evidence validates application-level detection and gateway enforcement.",
            "- OPC UA evidence measures connection, read and subscription stress.",
            "- DDS evidence measures an application-layer flood from a compromised authorized publisher.",
            "- Because these threat models and workloads differ, their raw availability values must not be presented as a protocol ranking.",
            "- DDS C1 and C2 security did not eliminate the authorized-publisher flood because valid credentials and permissions were used.",
            "",
            "## Main limitations",
            "",
            "- Three repetitions per network condition provide exploratory rather than population-level statistical evidence.",
            "- All tests ran on one Docker host, so results include host scheduling and container effects.",
            "- Protocol payload size and software stacks differ.",
            "- Hardware and multi-network validation remain separate future-validity steps.",
            "",
            "## Generated evidence",
            "",
            "- `cross_protocol_network_summary.csv`",
            "- `cross_protocol_security_matrix.csv`",
            "- `cross_protocol_availability_scope.csv`",
            "- `plots/cross_protocol_latency.png`",
            "- `plots/cross_protocol_jitter.png`",
            "- `plots/cross_protocol_throughput.png`",
            "",
        ]
    )

    report = OUTPUT_DIR / "CROSS_PROTOCOL_ANALYSIS_V1.md"
    report.write_text("\n".join(lines), encoding="utf-8")


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    PLOT_DIR.mkdir(parents=True, exist_ok=True)

    network_rows = normalize_network()
    security_rows = normalize_security()
    availability_rows = normalize_availability()

    write_csv(
        OUTPUT_DIR / "cross_protocol_network_summary.csv",
        network_rows,
    )
    write_csv(
        OUTPUT_DIR / "cross_protocol_security_matrix.csv",
        security_rows,
    )
    write_csv(
        OUTPUT_DIR / "cross_protocol_availability_scope.csv",
        availability_rows,
    )

    metric_grid(
        network_rows,
        "latency_mean_ms",
        "Latency (ms)",
        "cross_protocol_latency.png",
    )
    metric_grid(
        network_rows,
        "jitter_mean_ms",
        "Jitter (ms)",
        "cross_protocol_jitter.png",
    )
    metric_grid(
        network_rows,
        "throughput_mean_messages_per_second",
        "Throughput (messages/s)",
        "cross_protocol_throughput.png",
    )

    create_report(
        network_rows,
        security_rows,
        availability_rows,
    )

    print("Cross-protocol analysis completed")
    print(f"Network rows: {len(network_rows)}")
    print(f"Security rows: {len(security_rows)}")
    print(f"Availability rows: {len(availability_rows)}")
    print(f"Output: {OUTPUT_DIR}")
    print("PASS: cross-protocol artifacts generated")


if __name__ == "__main__":
    main()
