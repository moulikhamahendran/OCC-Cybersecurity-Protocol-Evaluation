#!/usr/bin/env python3

import csv
import statistics
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt


TESTBED_DIR = Path(__file__).resolve().parents[1]
DDS_RESULTS = TESTBED_DIR / "results" / "dds"
RESOURCE_DIR = TESTBED_DIR / "results" / "resources"
KPI_PATH = DDS_RESULTS / "dds_kpi_stream_v2.csv"
OUTPUT_DIR = DDS_RESULTS / "analysis_v2"

SUMMARY_PATH = OUTPUT_DIR / "dds_network_summary_v2.csv"
RESOURCE_SUMMARY_PATH = (
    OUTPUT_DIR / "dds_run_resource_summary_v2.csv"
)
REPORT_PATH = OUTPUT_DIR / "DDS_NETWORK_ANALYSIS_V2.md"

LEVELS = ("C0", "C1", "C2")
PROFILES = (
    "NET-ideal",
    "NET-delay",
    "NET-jitter",
    "NET-loss",
)

COLORS = {
    "C0": "#4C78A8",
    "C1": "#F58518",
    "C2": "#54A24B",
}


def mean(values):
    return statistics.mean(values)


def sample_sd(values):
    return (
        statistics.stdev(values)
        if len(values) > 1
        else 0.0
    )


def numeric(rows, field):
    return [float(row[field]) for row in rows]


def load_kpi_rows():
    with KPI_PATH.open(
        newline="",
        encoding="utf-8",
    ) as file:
        rows = list(csv.DictReader(file))

    if len(rows) != 36:
        raise RuntimeError(
            f"Expected 36 KPI rows, found {len(rows)}"
        )

    return rows


def load_run_resources(kpi_rows):
    run_summaries = []

    for kpi in kpi_rows:
        run_id = kpi["run_id"]
        resource_path = (
            RESOURCE_DIR / f"resource_{run_id}.csv"
        )

        if not resource_path.exists():
            raise FileNotFoundError(resource_path)

        with resource_path.open(
            newline="",
            encoding="utf-8",
        ) as file:
            rows = list(csv.DictReader(file))

        components = defaultdict(list)

        for row in rows:
            if (
                row["source"] == "container"
                and row["status"] == "running"
                and row["component"]
                in {"dds_publisher", "dds_subscriber"}
            ):
                components[row["component"]].append(row)

        required = {
            "dds_publisher",
            "dds_subscriber",
        }

        if set(components) != required:
            raise RuntimeError(
                f"Incomplete resource data for {run_id}: "
                f"{sorted(components)}"
            )

        result = {
            "run_id": run_id,
            "security_level":
                kpi["security_level"],
            "net_profile":
                kpi["net_profile"],
            "repeat_index":
                int(kpi["repeat_index"]),
        }

        for component in sorted(required):
            prefix = (
                "publisher"
                if component == "dds_publisher"
                else "subscriber"
            )

            cpu = [
                float(row["cpu_percent"])
                for row in components[component]
            ]
            memory = [
                float(row["memory_mb"])
                for row in components[component]
            ]

            result[f"{prefix}_samples"] = len(cpu)
            result[f"{prefix}_cpu_mean_pct"] = mean(cpu)
            result[f"{prefix}_cpu_peak_pct"] = max(cpu)
            result[f"{prefix}_memory_mean_mb"] = mean(
                memory
            )
            result[f"{prefix}_memory_peak_mb"] = max(
                memory
            )

        result["combined_cpu_mean_pct"] = (
            result["publisher_cpu_mean_pct"]
            + result["subscriber_cpu_mean_pct"]
        )
        result["combined_memory_mean_mb"] = (
            result["publisher_memory_mean_mb"]
            + result["subscriber_memory_mean_mb"]
        )

        run_summaries.append(result)

    return run_summaries


def build_group_summary(kpi_rows, resource_rows):
    kpi_groups = defaultdict(list)
    resource_groups = defaultdict(list)

    for row in kpi_rows:
        key = (
            row["security_level"],
            row["net_profile"],
        )
        kpi_groups[key].append(row)

    for row in resource_rows:
        key = (
            row["security_level"],
            row["net_profile"],
        )
        resource_groups[key].append(row)

    summary = []

    for profile in PROFILES:
        for level in LEVELS:
            key = (level, profile)
            kpi = kpi_groups[key]
            resources = resource_groups[key]

            if len(kpi) != 3 or len(resources) != 3:
                raise RuntimeError(
                    f"Incomplete group: {key}"
                )

            row = {
                "security_level": level,
                "net_profile": profile,
                "runs": 3,
                "latency_mean_ms":
                    mean(numeric(kpi, "latency_ms")),
                "latency_sd_ms":
                    sample_sd(
                        numeric(kpi, "latency_ms")
                    ),
                "jitter_mean_ms":
                    mean(numeric(kpi, "jitter_ms")),
                "jitter_sd_ms":
                    sample_sd(
                        numeric(kpi, "jitter_ms")
                    ),
                "max_latency_mean_ms":
                    mean(
                        numeric(kpi, "max_latency_ms")
                    ),
                "throughput_mean_mps":
                    mean(
                        numeric(
                            kpi,
                            (
                                "throughput_messages_"
                                "per_second"
                            ),
                        )
                    ),
                "throughput_sd_mps":
                    sample_sd(
                        numeric(
                            kpi,
                            (
                                "throughput_messages_"
                                "per_second"
                            ),
                        )
                    ),
                "loss_mean_percent":
                    mean(
                        numeric(kpi, "loss_percent")
                    ),
                "lost_messages_total":
                    sum(
                        int(value)
                        for value in [
                            item["lost_messages"]
                            for item in kpi
                        ]
                    ),
                "publisher_cpu_mean_pct":
                    mean([
                        item[
                            "publisher_cpu_mean_pct"
                        ]
                        for item in resources
                    ]),
                "subscriber_cpu_mean_pct":
                    mean([
                        item[
                            "subscriber_cpu_mean_pct"
                        ]
                        for item in resources
                    ]),
                "combined_cpu_mean_pct":
                    mean([
                        item[
                            "combined_cpu_mean_pct"
                        ]
                        for item in resources
                    ]),
                "publisher_memory_mean_mb":
                    mean([
                        item[
                            "publisher_memory_mean_mb"
                        ]
                        for item in resources
                    ]),
                "subscriber_memory_mean_mb":
                    mean([
                        item[
                            "subscriber_memory_mean_mb"
                        ]
                        for item in resources
                    ]),
                "combined_memory_mean_mb":
                    mean([
                        item[
                            "combined_memory_mean_mb"
                        ]
                        for item in resources
                    ]),
            }

            summary.append(row)

    return summary


def write_csv(path, rows):
    with path.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=rows[0].keys(),
        )
        writer.writeheader()
        writer.writerows(rows)


def plot_grouped(
    summary,
    field,
    ylabel,
    title,
    filename,
    error_field=None,
):
    lookup = {
        (
            row["security_level"],
            row["net_profile"],
        ): row
        for row in summary
    }

    positions = list(range(len(PROFILES)))
    width = 0.24
    offsets = {
        "C0": -width,
        "C1": 0,
        "C2": width,
    }

    figure, axis = plt.subplots(
        figsize=(10, 5.6)
    )

    maximum = 0.0

    for level in LEVELS:
        values = [
            float(lookup[(level, profile)][field])
            for profile in PROFILES
        ]
        maximum = max(maximum, *values)

        errors = (
            [
                float(
                    lookup[(level, profile)][
                        error_field
                    ]
                )
                for profile in PROFILES
            ]
            if error_field
            else None
        )

        axis.bar(
            [
                position + offsets[level]
                for position in positions
            ],
            values,
            width=width,
            label=level,
            color=COLORS[level],
            yerr=errors,
            capsize=4 if errors else 0,
        )

    axis.set_xticks(positions)
    axis.set_xticklabels(
        [
            profile.replace("NET-", "")
            for profile in PROFILES
        ]
    )
    axis.set_xlabel("Network condition")
    axis.set_ylabel(ylabel)
    axis.set_title(title)
    axis.legend(
        title="DDS security profile"
    )
    axis.grid(
        axis="y",
        linestyle="--",
        alpha=0.35,
    )

    if maximum == 0:
        axis.set_ylim(0, 1)
        axis.text(
            0.5,
            0.5,
            "0% application-message loss in all runs",
            transform=axis.transAxes,
            ha="center",
            va="center",
        )

    figure.tight_layout()
    figure.savefig(
        OUTPUT_DIR / filename,
        dpi=300,
        bbox_inches="tight",
    )
    plt.close(figure)


def write_report(summary):
    lookup = {
        (
            row["security_level"],
            row["net_profile"],
        ): row
        for row in summary
    }

    lines = [
        "# Corrected DDS Network Campaign",
        "",
        "## Scope",
        "",
        "- 36 validated runs",
        "- C0, C1 and C2 security profiles",
        "- Ideal, delay, jitter and loss conditions",
        "- Three repetitions per combination",
        "- 60 seconds and 600 messages per run",
        "- ID-set loss metric (`id-set-v1`)",
        "",
        "## Measurement notes",
        "",
        (
            "- NetEm was applied to publisher-container "
            "egress and therefore represents one-way "
            "source-to-subscriber impairment."
        ),
        (
            "- DDS used reliable delivery. The 2% NetEm "
            "packet-loss condition produced zero "
            "application-message loss because delivery "
            "was recovered before the measurement window "
            "closed."
        ),
        (
            "- Host resource rows were excluded. CPU and "
            "RAM statistics use only the DDS publisher "
            "and subscriber container rows."
        ),
        (
            "- Resource values were averaged per run "
            "before group aggregation."
        ),
        "",
        "## Group results",
        "",
        (
            "| Security | Network | Latency ms | "
            "Jitter ms | Throughput msg/s | Loss % | "
            "CPU % | RAM MB |"
        ),
        (
            "|---|---:|---:|---:|---:|---:|---:|---:|"
        ),
    ]

    for profile in PROFILES:
        for level in LEVELS:
            row = lookup[(level, profile)]
            lines.append(
                f"| {level} | {profile} | "
                f"{row['latency_mean_ms']:.3f} | "
                f"{row['jitter_mean_ms']:.3f} | "
                f"{row['throughput_mean_mps']:.3f} | "
                f"{row['loss_mean_percent']:.3f} | "
                f"{row['combined_cpu_mean_pct']:.3f} | "
                f"{row['combined_memory_mean_mb']:.3f} |"
            )

    lines.extend([
        "",
        "## Interpretation boundary",
        "",
        (
            "These broad-matrix results use n=3 and are "
            "exploratory comparative evidence. Headline "
            "findings require later confirmatory runs "
            "with approximately n=10."
        ),
        "",
    ])

    REPORT_PATH.write_text(
        "\n".join(lines),
        encoding="utf-8",
    )


def main():
    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    kpi_rows = load_kpi_rows()
    resource_rows = load_run_resources(kpi_rows)
    summary = build_group_summary(
        kpi_rows,
        resource_rows,
    )

    write_csv(RESOURCE_SUMMARY_PATH, resource_rows)
    write_csv(SUMMARY_PATH, summary)
    write_report(summary)

    plot_grouped(
        summary,
        "latency_mean_ms",
        "Mean latency (ms)",
        "DDS latency by security and network profile",
        "dds_latency_v2.png",
        "latency_sd_ms",
    )
    plot_grouped(
        summary,
        "jitter_mean_ms",
        "Mean jitter (ms)",
        "DDS jitter by security and network profile",
        "dds_jitter_v2.png",
        "jitter_sd_ms",
    )
    plot_grouped(
        summary,
        "throughput_mean_mps",
        "Throughput (messages/second)",
        "DDS throughput by security and network profile",
        "dds_throughput_v2.png",
        "throughput_sd_mps",
    )
    plot_grouped(
        summary,
        "loss_mean_percent",
        "Application-message loss (%)",
        "DDS application-message loss",
        "dds_loss_v2.png",
    )
    plot_grouped(
        summary,
        "combined_cpu_mean_pct",
        "Publisher + subscriber CPU (%)",
        "DDS container CPU usage",
        "dds_cpu_v2.png",
    )
    plot_grouped(
        summary,
        "combined_memory_mean_mb",
        "Publisher + subscriber RAM (MB)",
        "DDS container memory usage",
        "dds_memory_v2.png",
    )

    print("PASS: DDS analysis completed")
    print("Summary:", SUMMARY_PATH)
    print("Run resources:", RESOURCE_SUMMARY_PATH)
    print("Report:", REPORT_PATH)
    print("Plots: 6")


if __name__ == "__main__":
    main()
