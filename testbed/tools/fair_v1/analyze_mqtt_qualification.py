#!/usr/bin/env python3

"""
FAIR-V1 MQTT qualification KPI analysis.

Scope:
- Exactly the 15 audited MQTT qualification runs.
- C0 R1-R5, C1 R1-R5, C2 R1-R5.
- Does not relabel these sequential MQTT runs as the final
  interleaved MQTT/OPC UA/DDS comparative FAIR-V1 campaign.
- Reads raw evidence only.
- Never modifies raw experimental data.

Analysis conventions explicitly approved for this qualification analysis:
1. Primary latency sample:
   seq >= 20 AND echo_status == "ok".
2. Primary latency:
   app_rtt_us / 1000.
3. Late echoes:
   formal transaction failures; excluded from normal latency/jitter.
4. Timeouts:
   formal transaction failures; excluded from latency/jitter.
5. Jitter:
   mean absolute difference between successive successful RTT samples
   ordered by seq.
6. Standard deviation:
   sample standard deviation, denominator n-1.
7. p95 / p99:
   empirical percentile using linear interpolation with
   index = (n - 1) * q.
8. Unsuccessful transaction percentage:
   (timeout + late_echo) / sent_success * 100.
9. Skipped slots:
   excluded from transaction-failure denominator; reflected separately
   in achieved_rate.
10. send_failed:
    reported separately; not silently combined with transaction failures.
11. OCC receiver loss:
    successful protocol submission whose seq has no matching OCC occ_rx.
12. Aggregate primary latency:
    five repeat-level mean RTT values, never pooled message samples.
13. 95% CI:
    two-sided Student's t, n=5, df=4.
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import math
import statistics as st
import subprocess
from pathlib import Path


ROOT = Path("testbed/results/fair_v1/mqtt")

OUT = ROOT / "qualification_analysis"

PER_REPEAT_CSV = OUT / "mqtt_qualification_per_repeat.csv"
AGGREGATE_CSV = OUT / "mqtt_qualification_profile_aggregate.csv"
COMPARISON_CSV = OUT / "mqtt_qualification_profile_comparison.csv"
MANIFEST_JSON = OUT / "analysis_manifest.json"
SUMMARY_MD = OUT / "MQTT_QUALIFICATION_KPI_SUMMARY.md"

SCHEDULED = 600
WARMUP_LAST_SEQ = 19
T_CRIT_DF4_95 = 2.7764451051977987


RUNS = [
    ("C0", 1, "MQTT-C0-R1-20261003T230835Z-9f7bde8"),
    ("C0", 2, "MQTT-C0-R2-20261003T231637Z-9f7bde8"),
    ("C0", 3, "MQTT-C0-R3-20261003T233029Z-9f7bde8"),
    ("C0", 4, "MQTT-C0-R4-20261003T233354Z-9f7bde8"),
    ("C0", 5, "MQTT-C0-R5-20261003T233718Z-9f7bde8"),

    ("C1", 1, "MQTT-C1-R1-20261003T234524Z-9f7bde8"),
    ("C1", 2, "MQTT-C1-R2-20261003T234959Z-9f7bde8"),
    ("C1", 3, "MQTT-C1-R3-20261003T235342Z-9f7bde8"),
    ("C1", 4, "MQTT-C1-R4-20261003T235716Z-9f7bde8"),
    ("C1", 5, "MQTT-C1-R5-20261004T000059Z-9f7bde8"),

    ("C2", 1, "MQTT-C2-R1-20261004T003120Z-9f7bde8"),
    ("C2", 2, "MQTT-C2-R2-20261004T003620Z-9f7bde8"),
    ("C2", 3, "MQTT-C2-R3-20261004T004133Z-9f7bde8"),
    ("C2", 4, "MQTT-C2-R4-20261004T004547Z-9f7bde8"),
    ("C2", 5, "MQTT-C2-R5-20261004T004928Z-9f7bde8"),
]


def fail(message: str) -> None:
    raise SystemExit(f"STOP: {message}")


def parse_pipe_record(line: str, marker: str) -> dict[str, str]:
    if marker not in line:
        fail(f"marker {marker!r} missing")

    payload = line.split(marker, 1)[1].strip()

    out: dict[str, str] = {}

    for part in payload.split("|"):
        if "=" not in part:
            continue

        key, value = part.split("=", 1)
        out[key] = value

    return out


def as_int(value: str | None) -> int | None:
    if value in (None, "", "null"):
        return None
    return int(value)


def as_float(value: str | None) -> float | None:
    if value in (None, "", "null"):
        return None
    return float(value)


def mean(values: list[float]) -> float:
    if not values:
        fail("mean requested for empty sample")
    return st.mean(values)


def sample_sd(values: list[float]) -> float:
    if not values:
        fail("SD requested for empty sample")

    if len(values) == 1:
        return 0.0

    return st.stdev(values)


def percentile_linear(values: list[float], q: float) -> float:
    if not values:
        fail("percentile requested for empty sample")

    if not (0.0 <= q <= 1.0):
        fail("percentile q outside [0,1]")

    ordered = sorted(values)

    if len(ordered) == 1:
        return ordered[0]

    pos = (len(ordered) - 1) * q
    lo = math.floor(pos)
    hi = math.ceil(pos)

    if lo == hi:
        return ordered[lo]

    weight = pos - lo

    return (
        ordered[lo] * (1.0 - weight)
        + ordered[hi] * weight
    )


def pct(numerator: int, denominator: int) -> float:
    if denominator == 0:
        fail("percentage denominator is zero")

    return (numerator / denominator) * 100.0


def load_raw(run_dir: Path, run_id: str) -> list[dict[str, str]]:
    path = run_dir / "vehicle_raw.log"

    if not path.is_file():
        fail(f"{run_id}: missing vehicle_raw.log")

    rows = []

    for line in path.read_text(
        encoding="utf-8",
        errors="replace",
    ).splitlines():
        if "FAIR_RAW|" not in line:
            continue

        rows.append(
            parse_pipe_record(
                line,
                "FAIR_RAW|",
            )
        )

    if len(rows) != SCHEDULED:
        fail(
            f"{run_id}: expected {SCHEDULED} raw rows, "
            f"found {len(rows)}"
        )

    return rows


def load_summary(run_dir: Path, run_id: str) -> dict[str, str]:
    path = run_dir / "esp32_serial.log"

    if not path.is_file():
        fail(f"{run_id}: missing esp32_serial.log")

    matches = [
        line
        for line in path.read_text(
            encoding="utf-8",
            errors="replace",
        ).splitlines()
        if "FAIR_SUMMARY|" in line
    ]

    if len(matches) != 1:
        fail(
            f"{run_id}: expected one FAIR_SUMMARY, "
            f"found {len(matches)}"
        )

    return parse_pipe_record(
        matches[0],
        "FAIR_SUMMARY|",
    )


def load_metadata(run_dir: Path, run_id: str) -> dict:
    path = run_dir / "run_metadata.json"

    if not path.is_file():
        fail(f"{run_id}: missing run_metadata.json")

    return json.loads(
        path.read_text(encoding="utf-8")
    )


def load_occ_rx_sequences(
    run_dir: Path,
    run_id: str,
) -> set[int]:

    files = list(
        run_dir.glob("*occ_events*.jsonl")
    )

    if len(files) != 1:
        fail(
            f"{run_id}: expected exactly one OCC event file, "
            f"found {len(files)}"
        )

    rx: set[int] = set()

    for line in files[0].read_text(
        encoding="utf-8",
        errors="replace",
    ).splitlines():

        if not line.strip():
            continue

        event = json.loads(line)

        if event.get("run_id") != run_id:
            fail(
                f"{run_id}: foreign run_id in OCC event"
            )

        if event.get("event_type") != "occ_rx":
            continue

        if event.get("protocol") != "mqtt":
            fail(
                f"{run_id}: non-MQTT OCC event"
            )

        seq = event.get("seq")

        if not isinstance(seq, int):
            fail(
                f"{run_id}: invalid OCC seq {seq!r}"
            )

        rx.add(seq)

    return rx


def validate_raw_identity(
    rows: list[dict[str, str]],
    run_id: str,
    profile: str,
    repeat: int,
) -> None:

    seqs = []

    for row in rows:
        if row.get("run_id") != run_id:
            fail(f"{run_id}: raw run_id mismatch")

        if row.get("protocol") != "MQTT":
            fail(f"{run_id}: raw protocol mismatch")

        if row.get("security_profile") != profile:
            fail(f"{run_id}: raw profile mismatch")

        if as_int(row.get("repeat_index")) != repeat:
            fail(f"{run_id}: raw repeat mismatch")

        if row.get("dataset_schema_version") != "1.0":
            fail(f"{run_id}: raw dataset schema mismatch")

        if row.get("payload_schema_version") != "0.1":
            fail(f"{run_id}: raw payload schema mismatch")

        seq = as_int(row.get("seq"))

        if seq is None:
            fail(f"{run_id}: raw seq missing")

        seqs.append(seq)

        expected_warmup = seq <= WARMUP_LAST_SEQ

        actual_warmup = (
            row.get("latency_warmup_excluded") == "true"
        )

        if expected_warmup != actual_warmup:
            fail(
                f"{run_id}: warm-up flag mismatch at seq={seq}"
            )

    if len(set(seqs)) != SCHEDULED:
        fail(f"{run_id}: duplicate seq values")

    if set(seqs) != set(range(SCHEDULED)):
        fail(f"{run_id}: seq coverage is not exactly 0..599")


def run_metrics(
    profile: str,
    repeat: int,
    run_id: str,
) -> dict[str, object]:

    run_dir = ROOT / run_id

    if not run_dir.is_dir():
        fail(f"missing run directory {run_dir}")

    raw = load_raw(run_dir, run_id)
    summary = load_summary(run_dir, run_id)
    metadata = load_metadata(run_dir, run_id)

    validate_raw_identity(
        raw,
        run_id,
        profile,
        repeat,
    )

    if metadata.get("run_id") != run_id:
        fail(f"{run_id}: metadata run_id mismatch")

    if metadata.get("protocol") != "mqtt":
        fail(f"{run_id}: metadata protocol mismatch")

    if metadata.get("security_profile") != profile:
        fail(f"{run_id}: metadata profile mismatch")

    if metadata.get("repeat_index") != repeat:
        fail(f"{run_id}: metadata repeat mismatch")

    if metadata.get("run_validity_status") != "valid":
        fail(
            f"{run_id}: run is not metadata-valid"
        )

    sent_rows = [
        row
        for row in raw
        if row.get("send_status") in (
            "on_time",
            "late",
        )
    ]

    sent = len(sent_rows)

    skipped = sum(
        row.get("send_status") == "skipped"
        for row in raw
    )

    send_failed = sum(
        row.get("send_status") == "send_failed"
        for row in raw
    )

    late_sends = sum(
        row.get("send_status") == "late"
        for row in raw
    )

    echo_ok = sum(
        row.get("echo_status") == "ok"
        for row in raw
    )

    timeout = sum(
        row.get("echo_status") == "timeout"
        for row in raw
    )

    late_echo = sum(
        row.get("echo_status") == "late_echo"
        for row in raw
    )

    not_applicable = sum(
        row.get("echo_status") == "not_applicable"
        for row in raw
    )

    if (
        echo_ok
        + timeout
        + late_echo
        + not_applicable
        != SCHEDULED
    ):
        fail(
            f"{run_id}: echo-status accounting "
            "does not equal 600"
        )

    if sent + skipped + send_failed != SCHEDULED:
        fail(
            f"{run_id}: send-status accounting "
            "does not equal 600"
        )

    summary_checks = {
        "scheduled": SCHEDULED,
        "sent_success": sent,
        "skipped": skipped,
        "send_failed": send_failed,
        "late": late_sends,
        "echo_ok": echo_ok,
        "timeout": timeout,
        "late_echo": late_echo,
    }

    for key, expected in summary_checks.items():
        actual = as_int(summary.get(key))

        if actual != expected:
            fail(
                f"{run_id}: summary {key}={actual}, "
                f"raw-derived={expected}"
            )

    achieved_rate = sent / SCHEDULED

    summary_rate = as_float(
        summary.get("achieved_rate")
    )

    if summary_rate is None:
        fail(f"{run_id}: summary achieved_rate missing")

    if abs(summary_rate - achieved_rate) > 0.000001:
        fail(
            f"{run_id}: achieved-rate mismatch"
        )

    unsuccessful_count = timeout + late_echo

    unsuccessful_pct = pct(
        unsuccessful_count,
        sent,
    )

    successful_latency_rows = [
        row
        for row in raw
        if (
            as_int(row.get("seq")) is not None
            and as_int(row.get("seq")) > WARMUP_LAST_SEQ
            and row.get("echo_status") == "ok"
        )
    ]

    successful_latency_rows.sort(
        key=lambda row: as_int(row["seq"])
    )

    rtt_ms: list[float] = []
    schedule_latency_ms: list[float] = []

    for row in successful_latency_rows:
        rtt = as_int(row.get("app_rtt_us"))
        sched = as_int(
            row.get("schedule_latency_us")
        )

        if rtt is None:
            fail(
                f"{run_id}: successful echo missing RTT "
                f"at seq={row.get('seq')}"
            )

        if sched is None:
            fail(
                f"{run_id}: successful echo missing "
                f"schedule latency at seq={row.get('seq')}"
            )

        rtt_ms.append(rtt / 1000.0)
        schedule_latency_ms.append(
            sched / 1000.0
        )

    if not rtt_ms:
        fail(
            f"{run_id}: no successful post-warm-up "
            "latency samples"
        )

    jitter_samples_ms = [
        abs(rtt_ms[i] - rtt_ms[i - 1])
        for i in range(1, len(rtt_ms))
    ]

    jitter_ms = (
        mean(jitter_samples_ms)
        if jitter_samples_ms
        else 0.0
    )

    occ_rx = load_occ_rx_sequences(
        run_dir,
        run_id,
    )

    sent_seqs = {
        as_int(row.get("seq"))
        for row in sent_rows
    }

    if None in sent_seqs:
        fail(f"{run_id}: sent seq missing")

    sent_seq_ints = {
        int(seq)
        for seq in sent_seqs
        if seq is not None
    }

    occ_receiver_loss_seqs = sorted(
        sent_seq_ints - occ_rx
    )

    occ_receiver_loss = len(
        occ_receiver_loss_seqs
    )

    occ_receiver_loss_pct = pct(
        occ_receiver_loss,
        sent,
    )

    payload_sizes = [
        as_int(row.get("payload_bytes"))
        for row in sent_rows
        if as_int(row.get("payload_bytes"))
        is not None
    ]

    payload_size_mean = (
        mean(
            [
                float(x)
                for x in payload_sizes
                if x is not None
            ]
        )
        if payload_sizes
        else math.nan
    )

    return {
        "profile": profile,
        "repeat": repeat,
        "run_id": run_id,
        "run_validity": "valid",

        "expected_messages": SCHEDULED,
        "sent_messages": sent,
        "successful_echoes": echo_ok,
        "skipped_messages": skipped,
        "send_failures": send_failed,
        "late_sends": late_sends,
        "timeout_count": timeout,
        "late_echo_count": late_echo,

        "achieved_rate": achieved_rate,
        "achieved_rate_percent":
            achieved_rate * 100.0,

        "unsuccessful_transaction_count":
            unsuccessful_count,

        "unsuccessful_transaction_percent":
            unsuccessful_pct,

        "occ_receiver_loss_count":
            occ_receiver_loss,

        "occ_receiver_loss_percent":
            occ_receiver_loss_pct,

        "latency_sample_count":
            len(rtt_ms),

        "rtt_mean_ms":
            mean(rtt_ms),

        "rtt_median_ms":
            st.median(rtt_ms),

        "rtt_p95_ms":
            percentile_linear(rtt_ms, 0.95),

        "rtt_p99_ms":
            percentile_linear(rtt_ms, 0.99),

        "rtt_max_ms":
            max(rtt_ms),

        "rtt_sample_sd_ms":
            sample_sd(rtt_ms),

        "jitter_sample_pairs":
            len(jitter_samples_ms),

        "jitter_mean_abs_successive_rtt_ms":
            jitter_ms,

        "schedule_latency_mean_ms":
            mean(schedule_latency_ms),

        "schedule_latency_median_ms":
            st.median(schedule_latency_ms),

        "schedule_latency_p95_ms":
            percentile_linear(
                schedule_latency_ms,
                0.95,
            ),

        "schedule_latency_p99_ms":
            percentile_linear(
                schedule_latency_ms,
                0.99,
            ),

        "schedule_latency_max_ms":
            max(schedule_latency_ms),

        "payload_bytes_mean":
            payload_size_mean,

        "occ_receiver_missing_seqs":
            ",".join(
                str(x)
                for x in occ_receiver_loss_seqs
            ),
    }


def aggregate_profile(
    profile: str,
    rows: list[dict[str, object]],
) -> dict[str, object]:

    selected = [
        row
        for row in rows
        if row["profile"] == profile
    ]

    if len(selected) != 5:
        fail(
            f"{profile}: expected 5 repeat rows, "
            f"found {len(selected)}"
        )

    repeat_means = [
        float(row["rtt_mean_ms"])
        for row in selected
    ]

    mean_of_means = mean(repeat_means)

    sd_repeat_means = sample_sd(
        repeat_means
    )

    ci_half = (
        T_CRIT_DF4_95
        * sd_repeat_means
        / math.sqrt(5)
    )

    return {
        "profile": profile,
        "repeat_count": 5,

        "rtt_mean_of_repeat_means_ms":
            mean_of_means,

        "rtt_min_repeat_mean_ms":
            min(repeat_means),

        "rtt_median_repeat_mean_ms":
            st.median(repeat_means),

        "rtt_max_repeat_mean_ms":
            max(repeat_means),

        "rtt_repeat_means_sample_sd_ms":
            sd_repeat_means,

        "rtt_95ci_half_width_ms":
            ci_half,

        "rtt_95ci_low_ms":
            mean_of_means - ci_half,

        "rtt_95ci_high_ms":
            mean_of_means + ci_half,

        "jitter_mean_of_repeats_ms":
            mean([
                float(
                    row[
                        "jitter_mean_abs_successive_rtt_ms"
                    ]
                )
                for row in selected
            ]),

        "achieved_rate_mean_percent":
            mean([
                float(
                    row["achieved_rate_percent"]
                )
                for row in selected
            ]),

        "unsuccessful_transaction_mean_percent":
            mean([
                float(
                    row[
                        "unsuccessful_transaction_percent"
                    ]
                )
                for row in selected
            ]),

        "occ_receiver_loss_mean_percent":
            mean([
                float(
                    row[
                        "occ_receiver_loss_percent"
                    ]
                )
                for row in selected
            ]),

        "late_sends_mean_count":
            mean([
                float(row["late_sends"])
                for row in selected
            ]),
    }


def write_csv(
    path: Path,
    rows: list[dict[str, object]],
) -> None:

    if not rows:
        fail(f"refusing to write empty CSV {path}")

    with path.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as handle:

        writer = csv.DictWriter(
            handle,
            fieldnames=list(rows[0].keys()),
            lineterminator="\n",
        )

        writer.writeheader()
        writer.writerows(rows)


def f3(value: object) -> str:
    return f"{float(value):.3f}"


def main() -> None:

    if OUT.exists():
        fail(
            f"output directory already exists: {OUT}"
        )

    per_repeat = []

    print(
        "===== ANALYZING 15 MQTT QUALIFICATION RUNS ====="
    )

    for profile, repeat, run_id in RUNS:

        metrics = run_metrics(
            profile,
            repeat,
            run_id,
        )

        per_repeat.append(metrics)

        print(
            f"{profile} R{repeat}: "
            f"mean={metrics['rtt_mean_ms']:.3f} ms "
            f"p95={metrics['rtt_p95_ms']:.3f} ms "
            f"p99={metrics['rtt_p99_ms']:.3f} ms "
            f"jitter="
            f"{metrics['jitter_mean_abs_successive_rtt_ms']:.3f} ms "
            f"unsuccessful="
            f"{metrics['unsuccessful_transaction_percent']:.3f}% "
            f"occ_loss="
            f"{metrics['occ_receiver_loss_percent']:.3f}%"
        )

    aggregates = [
        aggregate_profile(
            profile,
            per_repeat,
        )
        for profile in ("C0", "C1", "C2")
    ]

    aggregate_map = {
        row["profile"]: row
        for row in aggregates
    }

    c0_mean = float(
        aggregate_map["C0"][
            "rtt_mean_of_repeat_means_ms"
        ]
    )

    comparison = []

    for profile in ("C0", "C1", "C2"):

        row = aggregate_map[profile]

        value = float(
            row[
                "rtt_mean_of_repeat_means_ms"
            ]
        )

        delta = value - c0_mean

        overhead = (
            (delta / c0_mean) * 100.0
            if c0_mean != 0
            else math.nan
        )

        comparison.append({
            "profile": profile,

            "rtt_mean_of_repeat_means_ms":
                value,

            "rtt_delta_ms_vs_c0":
                delta,

            "rtt_change_percent_vs_c0":
                overhead,

            "jitter_mean_of_repeats_ms":
                row[
                    "jitter_mean_of_repeats_ms"
                ],

            "achieved_rate_mean_percent":
                row[
                    "achieved_rate_mean_percent"
                ],

            "unsuccessful_transaction_mean_percent":
                row[
                    "unsuccessful_transaction_mean_percent"
                ],

            "occ_receiver_loss_mean_percent":
                row[
                    "occ_receiver_loss_mean_percent"
                ],
        })

    OUT.mkdir(
        parents=True,
        exist_ok=False,
    )

    write_csv(
        PER_REPEAT_CSV,
        per_repeat,
    )

    write_csv(
        AGGREGATE_CSV,
        aggregates,
    )

    write_csv(
        COMPARISON_CSV,
        comparison,
    )

    try:
        repo_head = subprocess.check_output(
            [
                "git",
                "rev-parse",
                "HEAD",
            ],
            text=True,
        ).strip()
    except Exception:
        repo_head = "UNAVAILABLE"

    manifest = {
        "analysis_scope":
            "MQTT Vehicle-1 qualification only",

        "final_cross_protocol_interleaved_campaign":
            False,

        "generated_utc":
            dt.datetime.now(
                dt.timezone.utc
            ).isoformat(),

        "analysis_repository_head":
            repo_head,

        "source_firmware_commit_prefix":
            "9f7bde8",

        "selected_run_count":
            15,

        "profiles": [
            "C0",
            "C1",
            "C2",
        ],

        "repeats_per_profile":
            5,

        "analysis_conventions": {
            "warmup_excluded_from_latency_and_jitter":
                "seq 0..19",

            "latency_sample":
                "seq>=20 and echo_status=ok",

            "primary_latency":
                "app_rtt_us / 1000",

            "late_echo":
                "transaction failure; excluded from normal latency/jitter",

            "timeout":
                "transaction failure; excluded from normal latency/jitter",

            "jitter":
                "mean absolute difference between successive successful RTT samples ordered by seq",

            "standard_deviation":
                "sample SD, n-1",

            "percentiles":
                "linear interpolation at index (n-1)*q",

            "unsuccessful_transaction_percent":
                "(timeout + late_echo) / sent_success * 100",

            "skipped":
                "excluded from transaction-failure denominator; represented by achieved_rate",

            "send_failed":
                "reported separately; not merged into transaction failures",

            "occ_receiver_loss":
                "successfully submitted seq absent from OCC occ_rx set",

            "aggregate":
                "five repeat-level RTT means, not pooled message samples",

            "confidence_interval":
                "two-sided 95% Student-t CI, n=5, df=4, t=2.7764451051977987",
        },

        "run_ids": [
            run_id
            for _, _, run_id in RUNS
        ],
    }

    MANIFEST_JSON.write_text(
        json.dumps(
            manifest,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    md = [
        "# MQTT Qualification KPI Summary",
        "",
        "Status: DERIVED QUALIFICATION ANALYSIS",
        "",
        "This is the sequential MQTT C0/C1/C2 qualification dataset.",
        "It is not the final interleaved MQTT/OPC UA/DDS comparative FAIR-V1 campaign.",
        "",
        "## Profile-level primary RTT",
        "",
        "| Profile | Mean of repeat means (ms) | 95% CI (ms) | Min repeat mean | Median repeat mean | Max repeat mean | Mean jitter (ms) | Mean achieved rate (%) | Mean unsuccessful tx (%) | Mean OCC loss (%) |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]

    for row in aggregates:
        md.append(
            f"| {row['profile']} | "
            f"{f3(row['rtt_mean_of_repeat_means_ms'])} | "
            f"[{f3(row['rtt_95ci_low_ms'])}, "
            f"{f3(row['rtt_95ci_high_ms'])}] | "
            f"{f3(row['rtt_min_repeat_mean_ms'])} | "
            f"{f3(row['rtt_median_repeat_mean_ms'])} | "
            f"{f3(row['rtt_max_repeat_mean_ms'])} | "
            f"{f3(row['jitter_mean_of_repeats_ms'])} | "
            f"{f3(row['achieved_rate_mean_percent'])} | "
            f"{f3(row['unsuccessful_transaction_mean_percent'])} | "
            f"{f3(row['occ_receiver_loss_mean_percent'])} |"
        )

    md += [
        "",
        "## C0-relative descriptive comparison",
        "",
        "| Profile | Mean RTT (ms) | Delta vs C0 (ms) | Change vs C0 (%) |",
        "|---|---:|---:|---:|",
    ]

    for row in comparison:
        md.append(
            f"| {row['profile']} | "
            f"{f3(row['rtt_mean_of_repeat_means_ms'])} | "
            f"{f3(row['rtt_delta_ms_vs_c0'])} | "
            f"{f3(row['rtt_change_percent_vs_c0'])} |"
        )

    md += [
        "",
        "## Method note",
        "",
        "- seq 0-19 excluded only from latency/jitter.",
        "- only echo_status=ok contributes to normal latency/jitter.",
        "- timeout and late_echo remain transaction failures.",
        "- p95/p99 use linear interpolation.",
        "- SD uses sample n-1.",
        "- jitter is mean absolute successive successful RTT difference.",
        "- unsuccessful transaction % = (timeout + late_echo) / sent_success * 100.",
        "- OCC receiver loss remains separate from vehicle-side transaction failure.",
        "- aggregate RTT uses five repeat-level means; raw messages are not pooled across repeats.",
        "- p99 is based on a finite per-repeat sample and should be interpreted cautiously.",
        "",
    ]

    SUMMARY_MD.write_text(
        "\n".join(md),
        encoding="utf-8",
    )

    print()
    print("===== PROFILE AGGREGATES =====")

    for row in aggregates:
        print(
            f"{row['profile']}: "
            f"RTT mean-of-means="
            f"{row['rtt_mean_of_repeat_means_ms']:.3f} ms "
            f"95%CI=["
            f"{row['rtt_95ci_low_ms']:.3f}, "
            f"{row['rtt_95ci_high_ms']:.3f}] "
            f"jitter="
            f"{row['jitter_mean_of_repeats_ms']:.3f} ms "
            f"unsuccessful="
            f"{row['unsuccessful_transaction_mean_percent']:.3f}% "
            f"OCC-loss="
            f"{row['occ_receiver_loss_mean_percent']:.3f}%"
        )

    print()
    print("===== C0-RELATIVE RTT COMPARISON =====")

    for row in comparison:
        print(
            f"{row['profile']}: "
            f"{row['rtt_mean_of_repeat_means_ms']:.3f} ms "
            f"delta={row['rtt_delta_ms_vs_c0']:.3f} ms "
            f"change={row['rtt_change_percent_vs_c0']:.3f}%"
        )

    print()
    print("Analysis output:")
    print(PER_REPEAT_CSV)
    print(AGGREGATE_CSV)
    print(COMPARISON_CSV)
    print(MANIFEST_JSON)
    print(SUMMARY_MD)

    print()
    print("STEP 3A RESULT: ANALYSIS COMPLETE")


if __name__ == "__main__":
    main()
