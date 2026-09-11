import csv
import statistics
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt


RESULTS = Path("testbed/results")
FIGURES = RESULTS / "figures"

MANIFEST = RESULTS / "mqtt_final_network_manifest.csv"
ATTACK_SUMMARY = RESULTS / "mqtt_attack_summary.csv"

FINAL_RUNS = RESULTS / "mqtt_final_results.csv"
FINAL_SUMMARY = RESULTS / "mqtt_final_summary.csv"
SECURITY_OVERHEAD = RESULTS / "mqtt_security_overhead.csv"

PROFILES = [
    "NET-ideal",
    "NET-proxy-ideal",
    "NET-delay",
    "NET-jitter",
    "NET-loss",
]

LEVELS = ["C0", "C1", "C2"]


def mean_or_none(values):
    values = [
        value for value in values
        if value is not None
    ]

    if not values:
        return None

    return statistics.mean(values)


def sd_or_zero(values):
    values = [
        value for value in values
        if value is not None
    ]

    if len(values) < 2:
        return 0.0

    return statistics.stdev(values)


with MANIFEST.open(newline="") as f:
    manifest = list(csv.DictReader(f))


# ------------------------------------------------------------
# Calculate true application delivery loss for each accepted run
# using broker ACK -> gateway receipt accounting.
# ------------------------------------------------------------

final_runs = []

for row in manifest:

    run_id = row["run_id"]
    run_dir = RESULTS / "runs" / run_id

    publisher_path = run_dir / "publisher.csv"
    gateway_path = run_dir / "gateway_receipts.csv"

    app_loss = None
    duplicates = None
    acked_count = None
    received_count = None
    missing_count = None

    if publisher_path.exists() and gateway_path.exists():

        with publisher_path.open(newline="") as f:
            pub = list(csv.DictReader(f))

        with gateway_path.open(newline="") as f:
            rec = list(csv.DictReader(f))

        acked = {
            int(r["header_id"])
            for r in pub
            if (
                r.get("status") == "BROKER_ACK"
                and r.get("header_id")
            )
        }

        received = {
            int(r["header_id"])
            for r in rec
            if r.get("header_id")
        }

        missing = acked - received

        duplicates = sum(
            int(r["mqtt_duplicate"])
            for r in rec
            if r.get("mqtt_duplicate")
        )

        acked_count = len(acked)
        received_count = len(received)
        missing_count = len(missing)

        app_loss = (
            len(missing) / len(acked) * 100.0
            if acked
            else 0.0
        )

    final_runs.append({
        **row,
        "broker_acked": (
            acked_count
            if acked_count is not None
            else ""
        ),
        "gateway_received": (
            received_count
            if received_count is not None
            else ""
        ),
        "missing_after_ack": (
            missing_count
            if missing_count is not None
            else ""
        ),
        "application_delivery_loss_percent": (
            round(app_loss, 6)
            if app_loss is not None
            else ""
        ),
        "mqtt_duplicates": (
            duplicates
            if duplicates is not None
            else ""
        ),
    })


with FINAL_RUNS.open(
    "w",
    newline="",
    encoding="utf-8",
) as f:

    writer = csv.DictWriter(
        f,
        fieldnames=final_runs[0].keys(),
    )

    writer.writeheader()
    writer.writerows(final_runs)


# ------------------------------------------------------------
# Aggregate the three repetitions
# ------------------------------------------------------------

grouped = defaultdict(list)

for row in final_runs:
    grouped[
        (
            row["network_profile"],
            row["security_level"],
        )
    ].append(row)


summary_rows = []

for profile in PROFILES:
    for level in LEVELS:

        rows = grouped[(profile, level)]

        def metric(name):
            return [
                float(r[name])
                for r in rows
                if r.get(name) not in ("", None)
            ]

        latency = metric("latency_ms")
        jitter = metric("jitter_ms")
        throughput = metric(
            "throughput_messages_per_second"
        )
        throughput_kbps = metric(
            "throughput_kbps"
        )
        app_loss = metric(
            "application_delivery_loss_percent"
        )

        summary_rows.append({
            "network_profile": profile,
            "security_level": level,

            "latency_mean_ms":
                statistics.mean(latency),
            "latency_sd_ms":
                sd_or_zero(latency),

            "jitter_mean_ms":
                statistics.mean(jitter),
            "jitter_sd_ms":
                sd_or_zero(jitter),

            "throughput_mean_messages_per_second":
                statistics.mean(throughput),
            "throughput_sd_messages_per_second":
                sd_or_zero(throughput),

            "throughput_mean_kbps":
                statistics.mean(throughput_kbps),
            "throughput_sd_kbps":
                sd_or_zero(throughput_kbps),

            "application_delivery_loss_mean_percent":
                mean_or_none(app_loss),

            "runs": len(rows),
        })


with FINAL_SUMMARY.open(
    "w",
    newline="",
    encoding="utf-8",
) as f:

    writer = csv.DictWriter(
        f,
        fieldnames=summary_rows[0].keys(),
    )

    writer.writeheader()
    writer.writerows(summary_rows)


# ------------------------------------------------------------
# Security overhead relative to C0 for every network profile
# ------------------------------------------------------------

lookup = {
    (
        row["network_profile"],
        row["security_level"],
    ): row
    for row in summary_rows
}

overhead_rows = []

for profile in PROFILES:

    c0 = lookup[(profile, "C0")]

    for level in ["C1", "C2"]:

        current = lookup[(profile, level)]

        latency_change = (
            (
                current["latency_mean_ms"]
                - c0["latency_mean_ms"]
            )
            / c0["latency_mean_ms"]
            * 100
        )

        throughput_change = (
            (
                current[
                    "throughput_mean_messages_per_second"
                ]
                - c0[
                    "throughput_mean_messages_per_second"
                ]
            )
            / c0[
                "throughput_mean_messages_per_second"
            ]
            * 100
        )

        overhead_rows.append({
            "network_profile": profile,
            "comparison": f"{level}_vs_C0",
            "latency_change_percent":
                latency_change,
            "throughput_change_percent":
                throughput_change,
        })


with SECURITY_OVERHEAD.open(
    "w",
    newline="",
    encoding="utf-8",
) as f:

    writer = csv.DictWriter(
        f,
        fieldnames=overhead_rows[0].keys(),
    )

    writer.writeheader()
    writer.writerows(overhead_rows)


# ------------------------------------------------------------
# Plot helper
# ------------------------------------------------------------

def make_plot(
    mean_field,
    sd_field,
    ylabel,
    title,
    filename,
):

    x = list(range(len(PROFILES)))
    offsets = [-0.25, 0.0, 0.25]
    width = 0.23

    plt.figure(figsize=(11, 6))

    for level, offset in zip(
        LEVELS,
        offsets,
    ):

        means = []
        errors = []

        for profile in PROFILES:

            row = lookup[(profile, level)]

            means.append(
                float(row[mean_field])
            )

            errors.append(
                float(row[sd_field])
            )

        positions = [
            value + offset
            for value in x
        ]

        plt.bar(
            positions,
            means,
            width=width,
            yerr=errors,
            capsize=4,
            label=level,
        )

    plt.xticks(
        x,
        PROFILES,
        rotation=15,
    )

    plt.ylabel(ylabel)
    plt.title(title)
    plt.legend()
    plt.grid(
        axis="y",
        alpha=0.25,
    )
    plt.tight_layout()

    path = FIGURES / filename

    plt.savefig(
        path,
        dpi=300,
        bbox_inches="tight",
    )

    plt.close()

    print("Created:", path)


FIGURES.mkdir(
    parents=True,
    exist_ok=True,
)


make_plot(
    "latency_mean_ms",
    "latency_sd_ms",
    "Mean latency (ms)",
    "MQTT Latency Across Network Conditions",
    "mqtt_latency_comparison.png",
)


make_plot(
    "jitter_mean_ms",
    "jitter_sd_ms",
    "Mean jitter (ms)",
    "MQTT Jitter Across Network Conditions",
    "mqtt_jitter_comparison.png",
)


make_plot(
    "throughput_mean_messages_per_second",
    "throughput_sd_messages_per_second",
    "Throughput (messages/s)",
    "MQTT Throughput Across Network Conditions",
    "mqtt_throughput_comparison.png",
)


# ------------------------------------------------------------
# Attack detection figure
# ------------------------------------------------------------

if ATTACK_SUMMARY.exists():

    with ATTACK_SUMMARY.open(newline="") as f:
        attacks = list(csv.DictReader(f))

    attack_names = [
        "malformed",
        "schema",
        "replay",
        "stale",
        "spoofing",
        "dos",
    ]

    detection = defaultdict(list)

    for row in attacks:
        detection[
            (
                row["security_level"],
                row["attack"],
            )
        ].append(
            int(row["detected"])
        )

    x = list(
        range(len(attack_names))
    )

    offsets = [-0.25, 0.0, 0.25]
    width = 0.23

    plt.figure(
        figsize=(10, 6)
    )

    for level, offset in zip(
        LEVELS,
        offsets,
    ):

        values = []

        for attack in attack_names:

            results = detection[
                (level, attack)
            ]

            rate = (
                sum(results)
                / len(results)
                * 100
                if results
                else 0
            )

            values.append(rate)

        positions = [
            value + offset
            for value in x
        ]

        plt.bar(
            positions,
            values,
            width=width,
            label=level,
        )

    plt.xticks(
        x,
        attack_names,
        rotation=15,
    )

    plt.ylim(0, 110)
    plt.ylabel("Detection rate (%)")
    plt.title(
        "MQTT Attack Detection Rate"
    )
    plt.legend()
    plt.grid(
        axis="y",
        alpha=0.25,
    )
    plt.tight_layout()

    attack_plot = (
        FIGURES
        / "mqtt_attack_detection.png"
    )

    plt.savefig(
        attack_plot,
        dpi=300,
        bbox_inches="tight",
    )

    plt.close()

    print(
        "Created:",
        attack_plot,
    )


# ------------------------------------------------------------
# Terminal summary
# ------------------------------------------------------------

print()
print("=" * 82)
print("FINAL MQTT RESULTS")
print("=" * 82)

for row in summary_rows:

    loss = row[
        "application_delivery_loss_mean_percent"
    ]

    loss_text = (
        f"{loss:.3f}%"
        if loss is not None
        else "N/A"
    )

    print(
        f"{row['network_profile']:16s} "
        f"{row['security_level']} | "
        f"lat={row['latency_mean_ms']:.3f}"
        f"±{row['latency_sd_ms']:.3f} ms | "
        f"jitter={row['jitter_mean_ms']:.3f}"
        f"±{row['jitter_sd_ms']:.3f} ms | "
        f"throughput="
        f"{row['throughput_mean_messages_per_second']:.3f}"
        f"±{row['throughput_sd_messages_per_second']:.3f} msg/s | "
        f"app_loss={loss_text}"
    )


print()
print("Final network runs:", len(final_runs))
print(
    "Attack runs:",
    len(attacks) if ATTACK_SUMMARY.exists() else "N/A"
)

print()
print("Saved:", FINAL_RUNS)
print("Saved:", FINAL_SUMMARY)
print("Saved:", SECURITY_OVERHEAD)
print("Figures:", FIGURES)
