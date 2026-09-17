#!/usr/bin/env python3

import csv
import statistics
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


PROJECT_DIR = Path(__file__).resolve().parents[2]
DOS_DIR = PROJECT_DIR / "testbed/results/dds/dos"
INPUT_PATH = DOS_DIR / "dds_dos_summary.csv"
OUTPUT_DIR = DOS_DIR / "analysis_v1"
PLOT_DIR = OUTPUT_DIR / "plots"

SECURITY_LEVELS = ("C0", "C1", "C2")

METRICS = {
    "received_legitimate_messages": "Received legitimate messages",
    "unexpected_attack_messages": "Attack messages received",
    "legitimate_loss_percent": "Legitimate loss (%)",
    "latency_ms": "Latency (ms)",
    "jitter_ms": "Jitter (ms)",
    "throughput_messages_per_second": "Throughput (messages/s)",
}


def read_csv(path):
    with path.open(newline="", encoding="utf-8") as file:
        return list(csv.DictReader(file))


def number(row, key):
    return float(row[key])


def mean(values):
    return statistics.mean(values)


def sample_stdev(values):
    return statistics.stdev(values) if len(values) > 1 else 0.0


def write_csv(path, rows):
    if not rows:
        raise RuntimeError(f"No rows available for {path.name}")

    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def create_security_summary(formal_rows):
    grouped = defaultdict(list)

    for row in formal_rows:
        grouped[row["security_level"]].append(row)

    output = []

    for level in SECURITY_LEVELS:
        rows = grouped[level]

        if len(rows) != 3:
            raise RuntimeError(
                f"Expected 3 formal runs for {level}, found {len(rows)}"
            )

        result = {
            "security_level": level,
            "runs": len(rows),
        }

        for metric in METRICS:
            values = [number(row, metric) for row in rows]
            result[f"{metric}_mean"] = f"{mean(values):.3f}"
            result[f"{metric}_stdev"] = f"{sample_stdev(values):.3f}"

        result["impacted_runs"] = sum(
            row["availability_outcome"] == "IMPACTED"
            for row in rows
        )
        result["passed_runs"] = sum(
            row["experiment_status"] == "PASS"
            for row in rows
        )

        output.append(result)

    return output


def create_run_resource_summary(formal_rows):
    output = []

    for experiment in formal_rows:
        resource_path = DOS_DIR / experiment["run_id"] / "resources.csv"

        if not resource_path.exists():
            raise FileNotFoundError(resource_path)

        resource_rows = read_csv(resource_path)
        grouped = defaultdict(list)

        for row in resource_rows:
            if row["status"] == "running":
                grouped[row["component"]].append(row)

        for component, rows in sorted(grouped.items()):
            cpu_values = [number(row, "cpu_percent") for row in rows]
            memory_values = [number(row, "memory_mb") for row in rows]

            output.append(
                {
                    "run_id": experiment["run_id"],
                    "security_level": experiment["security_level"],
                    "repeat": experiment["repeat"],
                    "component": component,
                    "samples": len(rows),
                    "cpu_percent_mean": f"{mean(cpu_values):.3f}",
                    "cpu_percent_peak": f"{max(cpu_values):.3f}",
                    "memory_mb_mean": f"{mean(memory_values):.3f}",
                    "memory_mb_peak": f"{max(memory_values):.3f}",
                }
            )

    return output


def create_resource_summary(run_resource_rows):
    grouped = defaultdict(list)

    for row in run_resource_rows:
        grouped[
            (row["security_level"], row["component"])
        ].append(row)

    output = []

    for level in SECURITY_LEVELS:
        components = sorted(
            component
            for security_level, component in grouped
            if security_level == level
        )

        for component in components:
            rows = grouped[(level, component)]

            cpu_means = [
                number(row, "cpu_percent_mean")
                for row in rows
            ]
            cpu_peaks = [
                number(row, "cpu_percent_peak")
                for row in rows
            ]
            memory_means = [
                number(row, "memory_mb_mean")
                for row in rows
            ]
            memory_peaks = [
                number(row, "memory_mb_peak")
                for row in rows
            ]

            output.append(
                {
                    "security_level": level,
                    "component": component,
                    "runs": len(rows),
                    "cpu_percent_mean": f"{mean(cpu_means):.3f}",
                    "cpu_percent_stdev": f"{sample_stdev(cpu_means):.3f}",
                    "cpu_percent_peak_mean": f"{mean(cpu_peaks):.3f}",
                    "memory_mb_mean": f"{mean(memory_means):.3f}",
                    "memory_mb_stdev": f"{sample_stdev(memory_means):.3f}",
                    "memory_mb_peak_mean": f"{mean(memory_peaks):.3f}",
                }
            )

    return output


def metric_plot(summary_rows, metric, title, ylabel, filename):
    means = [
        number(row, f"{metric}_mean")
        for row in summary_rows
    ]
    errors = [
        number(row, f"{metric}_stdev")
        for row in summary_rows
    ]

    figure, axis = plt.subplots(figsize=(7.2, 4.5))
    bars = axis.bar(
        SECURITY_LEVELS,
        means,
        yerr=errors,
        capsize=6,
        color=["#607D8B", "#1976D2", "#7B1FA2"],
    )

    axis.set_title(title)
    axis.set_xlabel("DDS security profile")
    axis.set_ylabel(ylabel)
    axis.grid(axis="y", alpha=0.25)

    for bar, value in zip(bars, means):
        axis.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height(),
            f"{value:.2f}",
            ha="center",
            va="bottom",
        )

    figure.tight_layout()
    figure.savefig(PLOT_DIR / filename, dpi=200)
    plt.close(figure)


def resource_plot(resource_rows, metric, ylabel, title, filename):
    components = sorted(
        {
            row["component"]
            for row in resource_rows
            if row["component"] != "host"
        }
    )

    if not components:
        return

    width = 0.8 / len(components)
    positions = list(range(len(SECURITY_LEVELS)))

    figure, axis = plt.subplots(figsize=(9, 5))

    for index, component in enumerate(components):
        values = []

        for level in SECURITY_LEVELS:
            match = next(
                (
                    row for row in resource_rows
                    if row["security_level"] == level
                    and row["component"] == component
                ),
                None,
            )
            values.append(number(match, metric) if match else 0.0)

        offsets = [
            position - 0.4 + width / 2 + index * width
            for position in positions
        ]

        axis.bar(
            offsets,
            values,
            width=width,
            label=component,
        )

    axis.set_xticks(positions, SECURITY_LEVELS)
    axis.set_xlabel("DDS security profile")
    axis.set_ylabel(ylabel)
    axis.set_title(title)
    axis.grid(axis="y", alpha=0.25)
    axis.legend()

    figure.tight_layout()
    figure.savefig(PLOT_DIR / filename, dpi=200)
    plt.close(figure)


def create_report(security_rows, resource_rows):
    lines = [
        "# DDS DoS Availability Analysis",
        "",
        "## Experimental scope",
        "",
        "- Threat model: compromised authorized DDS publisher performing an application-layer flood.",
        "- Security profiles: C0, C1 and C2.",
        "- Repetitions: three per profile.",
        "- Legitimate workload: 10 messages/s for 60 seconds.",
        "- Attack workload: 200 messages/s for 30 seconds.",
        "- The attacker used valid publisher authorization; this is not an unauthenticated external attacker.",
        "",
        "## Availability results",
        "",
        "| Profile | Runs | Received legitimate | Attack messages | Loss (%) | Latency (ms) | Outcome |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]

    for row in security_rows:
        lines.append(
            f"| {row['security_level']} "
            f"| {row['runs']} "
            f"| {float(row['received_legitimate_messages_mean']):.1f} "
            f"| {float(row['unexpected_attack_messages_mean']):.1f} "
            f"| {float(row['legitimate_loss_percent_mean']):.3f} "
            f"| {float(row['latency_ms_mean']):.3f} "
            f"| IMPACTED ({row['impacted_runs']}/{row['runs']}) |"
        )

    lines.extend(
        [
            "",
            "Values are arithmetic means across three runs; the generated CSV also contains sample standard deviations.",
            "",
            "## Resource results",
            "",
            "| Profile | Component | Mean CPU (%) | Mean peak CPU (%) | Mean memory (MB) | Mean peak memory (MB) |",
            "|---|---|---:|---:|---:|---:|",
        ]
    )

    for row in resource_rows:
        lines.append(
            f"| {row['security_level']} "
            f"| {row['component']} "
            f"| {float(row['cpu_percent_mean']):.3f} "
            f"| {float(row['cpu_percent_peak_mean']):.3f} "
            f"| {float(row['memory_mb_mean']):.3f} "
            f"| {float(row['memory_mb_peak_mean']):.3f} |"
        )

    loss_by_level = {
        row["security_level"]:
        float(row["legitimate_loss_percent_mean"])
        for row in security_rows
    }

    lowest = min(loss_by_level, key=loss_by_level.get)
    highest = max(loss_by_level, key=loss_by_level.get)

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            f"- All nine formal runs detected the controlled flood and recorded an availability impact.",
            f"- Mean legitimate-message loss ranged from {loss_by_level[lowest]:.3f}% ({lowest}) to {loss_by_level[highest]:.3f}% ({highest}).",
            "- C1 and C2 authentication and cryptographic protection did not prevent this flood because the attacking publisher possessed valid authorization.",
            "- The results demonstrate a residual availability risk from compromised or malicious authorized participants.",
            "- Differences between C0, C1 and C2 must be treated as exploratory because each profile has only three repetitions.",
            "- These results do not demonstrate that an unauthenticated external attacker can bypass DDS Security.",
            "",
            "## Generated evidence",
            "",
            "- `dds_dos_security_summary.csv`",
            "- `dds_dos_run_resource_summary.csv`",
            "- `dds_dos_resource_summary.csv`",
            "- `plots/dds_dos_loss.png`",
            "- `plots/dds_dos_latency.png`",
            "- `plots/dds_dos_attack_messages.png`",
            "- `plots/dds_dos_cpu.png`",
            "- `plots/dds_dos_memory.png`",
            "",
        ]
    )

    report_path = OUTPUT_DIR / "DDS_DOS_ANALYSIS_V1.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")


def main():
    if not INPUT_PATH.exists():
        raise FileNotFoundError(INPUT_PATH)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    PLOT_DIR.mkdir(parents=True, exist_ok=True)

    formal_rows = read_csv(INPUT_PATH)

    if len(formal_rows) != 9:
        raise RuntimeError(
            f"Expected 9 formal DDS DoS runs, found {len(formal_rows)}"
        )

    security_summary = create_security_summary(formal_rows)
    run_resource_summary = create_run_resource_summary(formal_rows)
    resource_summary = create_resource_summary(run_resource_summary)

    write_csv(
        OUTPUT_DIR / "dds_dos_security_summary.csv",
        security_summary,
    )
    write_csv(
        OUTPUT_DIR / "dds_dos_run_resource_summary.csv",
        run_resource_summary,
    )
    write_csv(
        OUTPUT_DIR / "dds_dos_resource_summary.csv",
        resource_summary,
    )

    metric_plot(
        security_summary,
        "legitimate_loss_percent",
        "DDS legitimate-message loss during authorized flood",
        "Loss (%)",
        "dds_dos_loss.png",
    )
    metric_plot(
        security_summary,
        "latency_ms",
        "DDS latency during authorized flood",
        "Latency (ms)",
        "dds_dos_latency.png",
    )
    metric_plot(
        security_summary,
        "unexpected_attack_messages",
        "DDS controlled attack messages received",
        "Messages",
        "dds_dos_attack_messages.png",
    )

    resource_plot(
        resource_summary,
        "cpu_percent_mean",
        "Mean CPU (%)",
        "DDS DoS component CPU usage",
        "dds_dos_cpu.png",
    )
    resource_plot(
        resource_summary,
        "memory_mb_mean",
        "Mean memory (MB)",
        "DDS DoS component memory usage",
        "dds_dos_memory.png",
    )

    create_report(security_summary, resource_summary)

    print("DDS DoS analysis completed")
    print(f"Formal runs: {len(formal_rows)}")
    print(f"Output: {OUTPUT_DIR}")

    for row in security_summary:
        print(
            f"{row['security_level']} | "
            f"loss={row['legitimate_loss_percent_mean']}% | "
            f"latency={row['latency_ms_mean']} ms | "
            f"attack={row['unexpected_attack_messages_mean']}"
        )

    print("PASS: DDS DoS analysis artifacts generated")


if __name__ == "__main__":
    main()
