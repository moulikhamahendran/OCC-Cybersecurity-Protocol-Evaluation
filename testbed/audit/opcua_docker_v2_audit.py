#!/usr/bin/env python3

import csv
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

RUNS_DIR = ROOT / "testbed/results/docker_v2/opcua/runs"
RESOURCE_DIR = ROOT / "testbed/results/docker_v2/resources"

OUTPUT_DIR = ROOT / "testbed/results/audit"
OUTPUT_FILE = OUTPUT_DIR / "opcua_docker_v2_authoritative.csv"

LEVELS = ("C0", "C1", "C2")
PROFILES = (
    "NET-ideal",
    "NET-delay",
    "NET-jitter",
    "NET-loss",
)
REPEATS = (1, 2, 3)

MIN_SAMPLE_ROWS = 500
MIN_RESOURCE_SPAN_S = 50.0

RUN_RE = re.compile(
    r"^opcua_(c[012])_"
    r"(net-(?:ideal|delay|jitter|loss))_"
    r"repeat_([123])_"
    r"(\d{8}T\d{6}Z)_"
    r"([0-9a-fA-F]+)$"
)


def read_csv(path):
    with path.open(
        newline="",
        encoding="utf-8",
        errors="replace",
    ) as f:
        return list(csv.DictReader(f))


def parse_run_id(run_id):
    m = RUN_RE.match(run_id)
    if not m:
        return None

    return {
        "level": m.group(1).upper(),
        "profile": "NET-" + m.group(2)[4:],
        "repeat": int(m.group(3)),
        "timestamp": m.group(4),
    }


def validate_candidate(run_dir):
    run_id = run_dir.name
    parsed = parse_run_id(run_id)

    if parsed is None:
        return None

    reasons = []

    sample_path = run_dir / "samples.csv"

    if not sample_path.is_file():
        sample_rows = []
        reasons.append("samples_missing")
    else:
        try:
            sample_rows = read_csv(sample_path)
        except Exception as exc:
            sample_rows = []
            reasons.append(
                f"samples_read_error:{type(exc).__name__}"
            )

    sample_count = len(sample_rows)

    if sample_count < MIN_SAMPLE_ROWS:
        reasons.append(
            f"short_or_incomplete_samples:{sample_count}"
        )

    resource_path = (
        RESOURCE_DIR / f"resource_{run_id}.csv"
    )

    resource_rows = []

    if not resource_path.is_file():
        reasons.append("resource_missing")
    else:
        try:
            resource_rows = read_csv(resource_path)
        except Exception as exc:
            reasons.append(
                f"resource_read_error:{type(exc).__name__}"
            )

    if resource_rows:
        resource_run_ids = {
            row.get("run_id", "")
            for row in resource_rows
            if row.get("run_id")
        }

        if resource_run_ids != {run_id}:
            reasons.append(
                "resource_run_id_mismatch:"
                + ",".join(sorted(resource_run_ids))
            )

        running = [
            row
            for row in resource_rows
            if row.get("source") == "container"
            and row.get("status") == "running"
        ]

        components = {
            row.get("component", "")
            for row in running
            if row.get("component")
        }

        required = {
            "opcua_server",
            "opcua_client",
        }

        if not required.issubset(components):
            reasons.append(
                "resource_components_incomplete:"
                + ",".join(sorted(components))
            )

        elapsed = []

        for row in running:
            try:
                elapsed.append(
                    float(row.get("elapsed_s", ""))
                )
            except (TypeError, ValueError):
                pass

        if elapsed:
            resource_span = max(elapsed) - min(elapsed)

            if resource_span < MIN_RESOURCE_SPAN_S:
                reasons.append(
                    f"resource_span_too_short:"
                    f"{resource_span:.1f}s"
                )
        else:
            resource_span = 0.0
            reasons.append("resource_elapsed_missing")

    else:
        components = set()
        resource_span = 0.0

    return {
        "cell": (
            parsed["level"],
            parsed["profile"],
            parsed["repeat"],
        ),
        "level": parsed["level"],
        "profile": parsed["profile"],
        "repeat": parsed["repeat"],
        "timestamp": parsed["timestamp"],
        "run_id": run_id,
        "run_dir": run_dir,
        "sample_path": sample_path,
        "sample_rows": sample_count,
        "resource_path": resource_path,
        "resource_rows": len(resource_rows),
        "resource_span_s": resource_span,
        "components": sorted(components),
        "reasons": reasons,
        "valid": not reasons,
    }


def main():
    expected = [
        (level, profile, repeat)
        for level in LEVELS
        for profile in PROFILES
        for repeat in REPEATS
    ]

    candidates = defaultdict(list)
    unmatched = []

    for run_dir in sorted(RUNS_DIR.iterdir()):
        if not run_dir.is_dir():
            continue

        candidate = validate_candidate(run_dir)

        if candidate is None:
            unmatched.append(run_dir.name)
            continue

        candidates[candidate["cell"]].append(
            candidate
        )

    selected = []
    missing = []
    duplicate_cells = []
    stale_count = 0

    print(
        "=== OPC UA DOCKER-V2 "
        "COMMON-CORE AUTHORITATIVE AUDIT ==="
    )

    for cell in expected:
        cell_candidates = sorted(
            candidates.get(cell, []),
            key=lambda item: (
                item["timestamp"],
                item["run_id"],
            ),
            reverse=True,
        )

        if len(cell_candidates) > 1:
            duplicate_cells.append(cell)

        valid_candidates = [
            item
            for item in cell_candidates
            if item["valid"]
        ]

        if not valid_candidates:
            missing.append(cell)

            print(
                f"{cell[0]} | {cell[1]} | "
                f"repeat={cell[2]} | "
                "NO_VALID_RUN"
            )

            for item in cell_candidates:
                print(
                    f"  {item['run_id']} | "
                    f"{','.join(item['reasons'])}"
                )

            continue

        authoritative = valid_candidates[0]
        selected.append(authoritative)

        stale = [
            item
            for item in cell_candidates
            if item["run_id"]
            != authoritative["run_id"]
        ]

        stale_count += len(stale)

        print(
            f"{cell[0]} | {cell[1]} | "
            f"repeat={cell[2]} | "
            f"SELECTED | "
            f"{authoritative['run_id']} | "
            f"samples={authoritative['sample_rows']} | "
            f"resource_rows="
            f"{authoritative['resource_rows']} | "
            f"resource_span="
            f"{authoritative['resource_span_s']:.1f}s | "
            f"candidates={len(cell_candidates)}"
        )

        for item in stale:
            label = (
                "VALID_STALE"
                if item["valid"]
                else "INVALID_STALE"
            )

            print(
                f"  {label} | "
                f"{item['run_id']} | "
                f"samples={item['sample_rows']} | "
                f"{','.join(item['reasons']) or 'none'}"
            )

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    fieldnames = [
        "security_level",
        "network_profile",
        "repeat",
        "run_id",
        "run_directory",
        "samples_csv",
        "sample_rows",
        "resource_csv",
        "resource_rows",
        "resource_span_s",
        "resource_components",
        "provenance_class",
    ]

    with OUTPUT_FILE.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=fieldnames,
            lineterminator="\n",
        )

        writer.writeheader()

        for item in selected:
            writer.writerow({
                "security_level":
                    item["level"],
                "network_profile":
                    item["profile"],
                "repeat":
                    item["repeat"],
                "run_id":
                    item["run_id"],
                "run_directory":
                    item["run_dir"]
                    .relative_to(ROOT)
                    .as_posix(),
                "samples_csv":
                    item["sample_path"]
                    .relative_to(ROOT)
                    .as_posix(),
                "sample_rows":
                    item["sample_rows"],
                "resource_csv":
                    item["resource_path"]
                    .relative_to(ROOT)
                    .as_posix(),
                "resource_rows":
                    item["resource_rows"],
                "resource_span_s":
                    f"{item['resource_span_s']:.6f}",
                "resource_components":
                    ";".join(item["components"]),
                "provenance_class":
                    "docker_v2_authoritative",
            })

    selected_resource_names = {
        item["resource_path"].name
        for item in selected
    }

    all_resource_names = {
        p.name
        for p in RESOURCE_DIR.glob(
            "resource_opcua_*.csv"
        )
    }

    orphan_resources = sorted(
        all_resource_names
        - selected_resource_names
    )

    print("\n=== TOTALS ===")
    print(
        f"Expected common-core cells: "
        f"{len(expected)}"
    )
    print(
        f"Authoritative valid cells: "
        f"{len(selected)}"
    )
    print(
        f"Missing/invalid cells: "
        f"{len(missing)}"
    )
    print(
        f"Cells with multiple candidates: "
        f"{len(duplicate_cells)}"
    )
    print(
        f"Stale/non-selected run candidates: "
        f"{stale_count}"
    )
    print(
        f"Resource CSVs not selected: "
        f"{len(orphan_resources)}"
    )
    print(f"Manifest: {OUTPUT_FILE}")

    if missing:
        print("\nAUDIT VERDICT: FAIL")
        raise SystemExit(1)

    print("\nAUDIT VERDICT: PASS — 36/36")


if __name__ == "__main__":
    main()
