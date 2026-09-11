import csv
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt

INPUT = Path("testbed/results/opcua/opcua_final_network_summary.csv")
OUT = Path("testbed/results/opcua/figures")
OUT.mkdir(parents=True, exist_ok=True)

with INPUT.open() as f:
    rows = list(csv.DictReader(f))

profiles = [
    "NET-ideal",
    "NET-proxy-ideal",
    "NET-delay",
    "NET-jitter",
    "NET-loss",
]

levels = ["C0", "C1", "C2"]

labels = [
    "Ideal",
    "Proxy ideal",
    "Delay",
    "Jitter",
    "Loss",
]

lookup = {
    (r["net_profile"], r["security_level"]): r
    for r in rows
}

x = np.arange(len(profiles))
width = 0.24

metrics = [
    (
        "latency_mean_ms",
        "latency_std_ms",
        "Application-level latency (ms)",
        "OPC UA Latency under Network Conditions",
        "opcua_latency_comparison.png",
    ),
    (
        "jitter_mean_ms",
        "jitter_std_ms",
        "Jitter (ms)",
        "OPC UA Jitter under Network Conditions",
        "opcua_jitter_comparison.png",
    ),
    (
        "throughput_mean_msg_s",
        "throughput_std_msg_s",
        "Throughput (messages/s)",
        "OPC UA Throughput under Network Conditions",
        "opcua_throughput_comparison.png",
    ),
]

for mean_key, std_key, ylabel, title, filename in metrics:

    plt.figure(figsize=(10, 6))

    for index, level in enumerate(levels):

        means = [
            float(lookup[(p, level)][mean_key])
            for p in profiles
        ]

        stds = [
            float(lookup[(p, level)][std_key])
            for p in profiles
        ]

        plt.bar(
            x + (index - 1) * width,
            means,
            width,
            yerr=stds,
            capsize=4,
            label=level,
        )

    plt.xticks(x, labels)
    plt.ylabel(ylabel)
    plt.xlabel("Network profile")
    plt.title(title)
    plt.legend(title="Security level")
    plt.grid(axis="y", alpha=0.3)
    plt.tight_layout()

    path = OUT / filename
    plt.savefig(path, dpi=300)
    plt.close()

    print("Created:", path)

print()
print("OPC UA figures complete.")
