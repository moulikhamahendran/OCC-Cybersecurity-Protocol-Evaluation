import csv
import statistics
from pathlib import Path
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results" / "hardware" / "opcua"
OUT = RESULTS / "plots"
OUT.mkdir(parents=True, exist_ok=True)

profiles = {
    "C0\nNoSecurity": RESULTS / "c0" / "summary.csv",
    "C1\nSign": RESULTS / "c1" / "summary.csv",
    "C2\nSignAndEncrypt": RESULTS / "c2" / "summary.csv",
}

metrics = {
    "mean_rtt_ms": ("Mean RTT", "RTT (ms)", "opcua_mean_rtt.png"),
    "mean_jitter_ms": ("Mean Jitter", "Jitter (ms)", "opcua_mean_jitter.png"),
    "throughput_hz": ("Throughput", "Throughput (Hz)", "opcua_throughput.png"),
    "loss_percent": ("Transaction Loss", "Loss (%)", "opcua_loss.png"),
}

data = {}

for profile, path in profiles.items():
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))

    # Use only the three experimental repeats, not the pre-calculated average row.
    repeats = [r for r in rows if r["repeat"] in {"1", "2", "3"}]

    data[profile] = {}
    for metric in metrics:
        values = [float(r[metric]) for r in repeats]
        data[profile][metric] = {
            "values": values,
            "mean": statistics.mean(values),
            "sd": statistics.stdev(values),
        }

for metric, (title, ylabel, filename) in metrics.items():
    labels = list(profiles.keys())
    means = [data[p][metric]["mean"] for p in labels]
    sds = [data[p][metric]["sd"] for p in labels]

    fig, ax = plt.subplots(figsize=(8, 5))

    bars = ax.bar(labels, means, yerr=sds, capsize=6)

    ax.set_title(f"OPC UA Hardware: {title}")
    ax.set_ylabel(ylabel)
    ax.set_xlabel("Security Profile")
    ax.grid(axis="y", alpha=0.25)

    for bar, mean in zip(bars, means):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height(),
            f"{mean:.3f}",
            ha="center",
            va="bottom",
            fontsize=9
        )

    fig.tight_layout()
    fig.savefig(OUT / filename, dpi=300, bbox_inches="tight")
    plt.close(fig)

# Combined repeat-level RTT plot
fig, ax = plt.subplots(figsize=(9, 5))

repeat_labels = ["Repeat 1", "Repeat 2", "Repeat 3"]

for profile in profiles:
    ax.plot(
        repeat_labels,
        data[profile]["mean_rtt_ms"]["values"],
        marker="o",
        label=profile.replace("\n", " – ")
    )

ax.set_title("OPC UA Hardware RTT Across Repeats")
ax.set_ylabel("Mean RTT (ms)")
ax.set_xlabel("Experimental Repeat")
ax.grid(alpha=0.25)
ax.legend()
fig.tight_layout()
fig.savefig(OUT / "opcua_rtt_repeats.png", dpi=300, bbox_inches="tight")
plt.close(fig)

print("Generated OPC UA plots:")
for p in sorted(OUT.glob("*.png")):
    print(" -", p)
