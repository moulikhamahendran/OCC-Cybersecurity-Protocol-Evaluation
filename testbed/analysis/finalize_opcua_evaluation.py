import csv
import statistics
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


ROOT = Path("testbed/results/opcua")
FIG = ROOT / "figures"
FIG.mkdir(parents=True, exist_ok=True)

NETWORK_MANIFEST = ROOT / "opcua_final_network_manifest.csv"
AVAIL_MANIFEST = ROOT / "opcua_final_availability_manifest.csv"
SECURITY_FILE = ROOT / "opcua_attack_security_results.csv"
STRESS_FILE = ROOT / "opcua_availability_stress_metrics.csv"

DELIVERY_OUT = ROOT / "opcua_delivery_resilience.csv"
SECURITY_OUT = ROOT / "opcua_security_control_summary.csv"
STRESS_OUT = ROOT / "opcua_stress_generator_summary.csv"

levels = ["C0", "C1", "C2"]


def read_csv(path):
    with path.open() as fh:
        return list(csv.DictReader(fh))


network = read_csv(NETWORK_MANIFEST)
availability = read_csv(AVAIL_MANIFEST)
security = read_csv(SECURITY_FILE)
stress = read_csv(STRESS_FILE)


# ==========================================================
# 1. APPLICATION DELIVERY / RESILIENCE
# ==========================================================

conditions = {
    "Baseline": "NET-ideal",
    "Connection": "STRESS-connection",
    "Read": "STRESS-read",
    "Subscription": "STRESS-subscription",
}

delivery_rows = []

for level in levels:
    for label, profile in conditions.items():

        source = (
            network
            if profile == "NET-ideal"
            else availability
        )

        profile_key = (
            "net_profile"
            if profile == "NET-ideal"
            else "net_profile"
        )

        selected = [
            r for r in source
            if r["security_level"] == level
            and r[profile_key] == profile
        ]

        received = [
            float(r["received_messages"])
            for r in selected
        ]

        throughput = [
            float(
                r["throughput_messages_per_second"]
            )
            for r in selected
        ]

        delivery_rows.append({
            "security_level": level,
            "condition": label,
            "runs": len(selected),
            "received_mean":
                statistics.mean(received),
            "received_std":
                statistics.stdev(received),
            "throughput_mean_msg_s":
                statistics.mean(throughput),
            "application_delivery_percent_of_10hz":
                statistics.mean(throughput) / 10.0 * 100.0,
        })

with DELIVERY_OUT.open("w", newline="") as fh:
    writer = csv.DictWriter(
        fh,
        fieldnames=delivery_rows[0].keys(),
    )
    writer.writeheader()
    writer.writerows(delivery_rows)


# delivery figure
x = np.arange(len(conditions))
width = 0.24

plt.figure(figsize=(10, 6))

for index, level in enumerate(levels):

    level_rows = [
        r for r in delivery_rows
        if r["security_level"] == level
    ]

    means = [
        r["received_mean"]
        for r in level_rows
    ]

    stds = [
        r["received_std"]
        for r in level_rows
    ]

    plt.bar(
        x + (index - 1) * width,
        means,
        width,
        yerr=stds,
        capsize=4,
        label=level,
    )

plt.axhline(
    600,
    linestyle="--",
    linewidth=1,
    label="Nominal 10 Hz × 60 s",
)

plt.xticks(
    x,
    list(conditions.keys()),
)

plt.xlabel("Operating condition")
plt.ylabel("Received application updates / 60 s")
plt.title("OPC UA Application Delivery Resilience")
plt.legend()
plt.grid(axis="y", alpha=0.3)
plt.tight_layout()

delivery_figure = (
    FIG / "opcua_delivery_resilience.png"
)

plt.savefig(
    delivery_figure,
    dpi=300,
)

plt.close()


# ==========================================================
# 2. SECURITY CONTROL SUMMARY
# ==========================================================

security_groups = {}

for r in security:
    key = (
        r["security_level"],
        r["attack_type"],
    )

    security_groups.setdefault(
        key,
        [],
    ).append(r)

security_rows = []

for key, rows in sorted(
    security_groups.items()
):
    level, attack = key

    passed = sum(
        r["control_passed"].lower() == "true"
        for r in rows
    )

    observed = sorted(
        set(
            r["observed_outcome"]
            for r in rows
        )
    )

    expected = sorted(
        set(
            r["expected_outcome"]
            for r in rows
        )
    )

    security_rows.append({
        "security_level": level,
        "attack_type": attack,
        "runs": len(rows),
        "controls_passed": passed,
        "pass_rate_percent":
            passed / len(rows) * 100.0,
        "expected_outcome":
            " / ".join(expected),
        "observed_outcome":
            " / ".join(observed),
    })

with SECURITY_OUT.open("w", newline="") as fh:
    writer = csv.DictWriter(
        fh,
        fieldnames=security_rows[0].keys(),
    )
    writer.writeheader()
    writer.writerows(security_rows)


# security outcome figure as table
fig, ax = plt.subplots(figsize=(11, 5))
ax.axis("off")

table_data = []

for r in security_rows:
    table_data.append([
        r["security_level"],
        r["attack_type"],
        r["expected_outcome"],
        r["observed_outcome"],
        f'{r["controls_passed"]}/{r["runs"]}',
    ])

table = ax.table(
    cellText=table_data,
    colLabels=[
        "Level",
        "Security test",
        "Expected",
        "Observed",
        "Passed",
    ],
    loc="center",
)

table.auto_set_font_size(False)
table.set_fontsize(9)
table.scale(1, 1.4)

plt.title(
    "OPC UA Security-Control Evaluation",
    pad=18,
)

plt.tight_layout()

security_figure = (
    FIG / "opcua_security_control_summary.png"
)

plt.savefig(
    security_figure,
    dpi=300,
    bbox_inches="tight",
)

plt.close()


# ==========================================================
# 3. STRESS GENERATOR SUMMARY
# ==========================================================

stress_groups = {}

for r in stress:
    key = (
        r["security_level"],
        r["stress_type"],
    )

    stress_groups.setdefault(
        key,
        [],
    ).append(r)

stress_rows = []

for key, rows in sorted(
    stress_groups.items()
):
    level, stress_type = key

    rates = [
        float(r["operations_per_second"])
        for r in rows
    ]

    failed = [
        float(r["failed_ops"])
        for r in rows
    ]

    successful = [
        float(r["successful_ops"])
        for r in rows
    ]

    stress_rows.append({
        "security_level": level,
        "stress_type": stress_type,
        "runs": len(rows),
        "operations_per_second_mean":
            statistics.mean(rates),
        "operations_per_second_std":
            statistics.stdev(rates),
        "successful_ops_mean":
            statistics.mean(successful),
        "failed_ops_total":
            sum(failed),
    })

with STRESS_OUT.open("w", newline="") as fh:
    writer = csv.DictWriter(
        fh,
        fieldnames=stress_rows[0].keys(),
    )
    writer.writeheader()
    writer.writerows(stress_rows)


# stress generator figure as table
fig, ax = plt.subplots(figsize=(10, 5))
ax.axis("off")

table_data = []

for r in stress_rows:
    table_data.append([
        r["security_level"],
        r["stress_type"],
        f'{r["operations_per_second_mean"]:.1f}',
        f'{r["successful_ops_mean"]:.0f}',
        f'{r["failed_ops_total"]:.0f}',
    ])

table = ax.table(
    cellText=table_data,
    colLabels=[
        "Level",
        "Stress type",
        "Mean operations/s",
        "Mean successful ops",
        "Failed ops",
    ],
    loc="center",
)

table.auto_set_font_size(False)
table.set_fontsize(9)
table.scale(1, 1.4)

plt.title(
    "OPC UA Controlled Stress Generator Summary",
    pad=18,
)

plt.tight_layout()

stress_figure = (
    FIG / "opcua_stress_generator_summary.png"
)

plt.savefig(
    stress_figure,
    dpi=300,
    bbox_inches="tight",
)

plt.close()


print("===== OPC UA FINAL EVALUATION ARTIFACTS =====")
print("Created:", DELIVERY_OUT)
print("Created:", delivery_figure)
print()
print("Created:", SECURITY_OUT)
print("Created:", security_figure)
print()
print("Created:", STRESS_OUT)
print("Created:", stress_figure)
print()
print("OPC UA extended evaluation complete.")
