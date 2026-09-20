#!/usr/bin/env python3

import csv

def lf_dict_writer(*args, **kwargs):
    """Create reproducible CSV files using Git-friendly LF line endings."""
    kwargs.setdefault("lineterminator", "\n")
    return csv.DictWriter(*args, **kwargs)

import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNS_DIR = ROOT / "testbed/results/runs"
RESOURCE_DIR = ROOT / "testbed/results/resources"
OUTPUT_DIR = ROOT / "testbed/results/audit"
OUTPUT_FILE = OUTPUT_DIR / "mqtt_common_core_authoritative.csv"

LEVELS = ("C0", "C1", "C2")
PROFILES = ("net-ideal", "net-delay", "net-jitter", "net-loss")
REPEATS = (1, 2, 3)

RUN_PATTERN = re.compile(
    r"^mqtt_(c[012])_"
    r"(net-(?:ideal|delay|jitter|loss))_"
    r"repeat_([123])_"
    r"(\d{8}T\d{6}Z)_"
    r"([A-Za-z0-9]+)$",
    re.IGNORECASE,
)


def read_csv(path):
    if not path.is_file() or path.stat().st_size == 0:
        return []

    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def numeric_span(rows, fields):
    for field in fields:
        values = []

        for row in rows:
            raw = str(row.get(field, "")).strip()

            if not raw:
                continue

            try:
                values.append(float(raw))
            except ValueError:
                continue

        if len(values) < 2:
            continue

        span = max(values) - min(values)

        if field.endswith("_ns"):
            span /= 1_000_000_000

        return field, span

    return None, None


def run_ids_match(rows, expected):
    values = {
        str(row.get("run_id", "")).strip()
        for row in rows
        if str(row.get("run_id", "")).strip()
    }

    return not values or values == {expected}


def find_resource_files(run_id, run_dir):
    candidates = list(
        RESOURCE_DIR.glob(f"resource_{run_id}.csv")
    )

    candidates.extend(
        path
        for path in run_dir.glob("*.csv")
        if "resource" in path.name.lower()
    )

    unique = []

    for path in candidates:
        if path not in unique:
            unique.append(path)

    return unique


def validate_candidate(run_dir, run_id):
    reasons = []

    publisher_path = run_dir / "publisher.csv"
    receipts_path = run_dir / "gateway_receipts.csv"

    publisher_rows = read_csv(publisher_path)
    receipt_rows = read_csv(receipts_path)

    if not publisher_rows:
        reasons.append("missing_or_empty_publisher")

    if not receipt_rows:
        reasons.append("missing_or_empty_receipts")

    if publisher_rows and not run_ids_match(publisher_rows, run_id):
        reasons.append("publisher_run_id_mismatch")

    if receipt_rows and not run_ids_match(receipt_rows, run_id):
        reasons.append("receipt_run_id_mismatch")

    receipt_field, receipt_span = numeric_span(
        receipt_rows,
        ("received_ns", "timestamp", "timestamp_utc"),
    )

    if receipt_span is None:
        reasons.append("receipt_span_unavailable")
    elif not 55.0 <= receipt_span <= 75.0:
        reasons.append(f"invalid_receipt_span_{receipt_span:.3f}s")

    resource_files = find_resource_files(run_id, run_dir)
    selected_resource = None
    resource_rows = []
    resource_span = None

    for resource_path in resource_files:
        candidate_rows = read_csv(resource_path)

        if not candidate_rows:
            continue

        if not run_ids_match(candidate_rows, run_id):
            continue

        _, candidate_span = numeric_span(
            candidate_rows,
            ("elapsed_s", "timestamp", "timestamp_utc"),
        )

        if candidate_span is None:
            continue

        if 45.0 <= candidate_span <= 75.0:
            selected_resource = resource_path
            resource_rows = candidate_rows
            resource_span = candidate_span
            break

    if selected_resource is None:
        reasons.append("no_valid_same_run_resource_csv")

    valid = not reasons

    return {
        "valid": valid,
        "reasons": reasons,
        "publisher_path": publisher_path,
        "publisher_rows": len(publisher_rows),
        "receipts_path": receipts_path,
        "receipt_rows": len(receipt_rows),
        "receipt_time_field": receipt_field or "",
        "receipt_span_s": receipt_span,
        "resource_path": selected_resource,
        "resource_rows": len(resource_rows),
        "resource_span_s": resource_span,
    }


candidates = defaultdict(list)

for run_dir in sorted(RUNS_DIR.iterdir()):
    if not run_dir.is_dir():
        continue

    match = RUN_PATTERN.fullmatch(run_dir.name)

    if not match:
        continue

    level = match.group(1).upper()
    profile = match.group(2).lower()
    repeat = int(match.group(3))
    timestamp_text = match.group(4)

    timestamp = datetime.strptime(
        timestamp_text,
        "%Y%m%dT%H%M%SZ",
    )

    validation = validate_candidate(run_dir, run_dir.name)

    candidates[(level, profile, repeat)].append(
        {
            "run_id": run_dir.name,
            "run_dir": run_dir,
            "timestamp": timestamp,
            **validation,
        }
    )


selected = []
missing = []

print("=== MQTT COMMON-CORE AUTHORITATIVE AUDIT ===")

for level in LEVELS:
    for profile in PROFILES:
        for repeat in REPEATS:
            cell = (level, profile, repeat)
            cell_candidates = candidates.get(cell, [])

            valid_candidates = [
                candidate
                for candidate in cell_candidates
                if candidate["valid"]
            ]

            valid_candidates.sort(
                key=lambda item: item["timestamp"],
                reverse=True,
            )

            if not valid_candidates:
                missing.append(cell)

                print(
                    f"{level} | {profile} | repeat={repeat} | "
                    "NO_VALID_PAIRED_RUN"
                )

                for candidate in sorted(
                    cell_candidates,
                    key=lambda item: item["timestamp"],
                    reverse=True,
                ):
                    print(
                        f"  {candidate['run_id']} | "
                        f"{','.join(candidate['reasons'])}"
                    )

                continue

            authoritative = valid_candidates[0]
            selected.append((cell, authoritative))

            print(
                f"{level} | {profile} | repeat={repeat} | "
                f"SELECTED | {authoritative['run_id']} | "
                f"receipt_rows={authoritative['receipt_rows']} | "
                f"receipt_span="
                f"{authoritative['receipt_span_s']:.1f}s | "
                f"resource_rows={authoritative['resource_rows']} | "
                f"resource_span="
                f"{authoritative['resource_span_s']:.1f}s"
            )


OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

fieldnames = [
    "security_level",
    "network_profile",
    "repeat",
    "run_id",
    "run_directory",
    "publisher_csv",
    "publisher_rows",
    "gateway_receipts_csv",
    "receipt_rows",
    "receipt_time_field",
    "receipt_span_s",
    "resource_csv",
    "resource_rows",
    "resource_span_s",
]

with OUTPUT_FILE.open(
    "w",
    newline="",
    encoding="utf-8",
) as handle:
    writer = lf_dict_writer(handle, fieldnames=fieldnames)
    writer.writeheader()

    for (level, profile, repeat), candidate in selected:
        writer.writerow(
            {
                "security_level": level,
                "network_profile": profile,
                "repeat": repeat,
                "run_id": candidate["run_id"],
                "run_directory": candidate["run_dir"].relative_to(ROOT).as_posix(),
                "publisher_csv": candidate["publisher_path"].relative_to(ROOT).as_posix(),
                "publisher_rows": candidate["publisher_rows"],
                "gateway_receipts_csv": candidate["receipts_path"].relative_to(ROOT).as_posix(),
                "receipt_rows": candidate["receipt_rows"],
                "receipt_time_field": candidate[
                    "receipt_time_field"
                ],
                "receipt_span_s": (
                    f"{candidate['receipt_span_s']:.6f}"
                ),
                "resource_csv": candidate["resource_path"].relative_to(ROOT).as_posix(),
                "resource_rows": candidate["resource_rows"],
                "resource_span_s": (
                    f"{candidate['resource_span_s']:.6f}"
                ),
            }
        )


print("\n=== TOTALS ===")
print("Expected common-core cells: 36")
print(f"Authoritative valid cells: {len(selected)}")
print(f"Missing/invalid cells: {len(missing)}")
print(f"Manifest: {OUTPUT_FILE}")

if missing:
    print("\n=== MISSING/INVALID CELLS ===")

    for level, profile, repeat in missing:
        print(f"{level} | {profile} | repeat={repeat}")

    print("\nAUDIT VERDICT: FAIL")
    raise SystemExit(1)

print("\nAUDIT VERDICT: PASS — 36/36")
