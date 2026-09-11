import csv
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt


RESULTS = Path("testbed/results/opcua")
FIGURES = RESULTS / "figures"
FIGURES.mkdir(parents=True, exist_ok=True)

BASELINE_FILE = RESULTS / "opcua_final_network_summary.csv"
STRESS_FILE = RESULTS / "opcua_final_availability_summary.csv"

levels = ["C0", "C1", "C2"]

conditions = [
    "Baseline",
    "Connection",
    "Read",
    "Subscription",
]

stress_map = {
    "Connection": "STRESS-connection",
    "Read": "STRESS-read",
    "Subscription": "STRESS-subscription",
}

with BASELINE_FILE.open() as fh:
    baseline_rows = list(csv.DictReader(fh))

with STRESS_FILE.open() as fh:
    stress_rows = list(csv.DictReader(fh))

baseline = {
    r["security_level"]: r
    for r in baseline_rows
    if r["net_profile"] == "NET-ideal"
}

stress = {
    (
        r["security_level"],
        r["stress_profile"],
    ): r
    for r in stress_rows
}


def build_values(level, mean_key, std_key):
    means = [
        float(baseline[level][mean_key])
    ]

    stds = [
        float(baseline[level][std_key])
    ]

    for condition in conditions[1:]:
        row = stress[
            (
                level,
                stress_map[condition],
            )
        ]

        means.append(
            float(row[mean_key])
        )

        stds.append(
            float(row[std_key])
        )

    return means, stds


metrics = [
    (
        "latency_mean_ms",
        "latency_std_ms",
        "Application-level latency (ms)",
        "OPC UA Availability Stress - Latency",
        "opcua_stress_latency.png",
    ),
    (
        "jitter_mean_ms",
        "jitter_std_ms",
        "Jitter (ms)",
        "OPC UA Availability Stress - Jitter",
        "opcua_stress_jitter.png",
    ),
    (
        "throughput_mean_msg_s",
        "throughput_std_msg_s",
        "Throughput (messages/s)",
        "OPC UA Availability Stress - Throughput",
        "opcua_stress_throughput.png",
    ),
]

x = np.arange(len(conditions))
width = 0.24

for mean_key, std_key, ylabel, title, filename in metrics:

    plt.figure(figsize=(10, 6))

    for index, level in enumerate(levels):

        means, stds = build_values(
            level,
            mean_key,
            std_key,
        )

        plt.bar(
            x + (index - 1) * width,
            means,
            width,
            yerr=stds,
            capsize=4,
            label=level,
        )

    plt.xticks(
        x,
        conditions,
    )

    plt.xlabel(
        "Operating condition"
    )

    plt.ylabel(
        ylabel
    )

    plt.title(
        title
    )

    plt.legend(
        title="Security level"
    )

    plt.grid(
        axis="y",
        alpha=0.3,
    )

    plt.tight_layout()

    output = FIGURES / filename

    plt.savefig(
        output,
        dpi=300,
    )

    plt.close()

    print(
        "Created:",
        output,
    )

print()
print(
    "OPC UA availability figures complete."
)
