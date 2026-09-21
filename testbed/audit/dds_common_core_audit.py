#!/usr/bin/env python3
import csv
import re
from collections import defaultdict
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[2]
TESTBED_DIR = PROJECT_DIR / "testbed"
DDS_RESULTS = TESTBED_DIR / "results" / "dds"
RUNS_DIR = DDS_RESULTS / "runs"
RESOURCE_DIR = TESTBED_DIR / "results" / "resources"
KPI_STREAM = DDS_RESULTS / "dds_kpi_stream_v2.csv"
AUDIT_DIR = TESTBED_DIR / "results" / "audit"
OUTPUT = AUDIT_DIR / "dds_common_core_authoritative.csv"

LEVELS = ("C0", "C1", "C2")
PROFILES = ("NET-ideal", "NET-delay", "NET-jitter", "NET-loss")
REPEATS = (1, 2, 3)

RUN_PATTERN = re.compile(
    r"^dds_(c[012])_"
    r"(net-[a-z0-9-]+)_"
    r"repeat_([0-9]+)_"
    r"(\d{8}T\d{6}Z)_"
    r"([0-9a-fA-F]+)$"
)

MIN_RESOURCE_SPAN_S = 50.0

def lf_dict_writer(*args, **kwargs):
    kwargs.setdefault("lineterminator", "\n")
    return csv.DictWriter(*args, **kwargs)

def read_csv(path):
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))

def parse_run_id(run_id):
    m = RUN_PATTERN.match(run_id)
    if not m:
        return None
    level = m.group(1).upper()
    profile = normalize_profile(m.group(2))
    repeat = int(m.group(3))
    timestamp = m.group(4)
    return {
        "level": level,
        "profile": profile,
        "repeat": repeat,
        "timestamp": timestamp,
    }

def normalize_profile(value):
    if not value:
        return ""
    value = value.strip()
    if value.lower().startswith("net-"):
        suffix = value[4:].lower()
        return "NET-" + suffix
    return value

def find_per_run_kpi_rows(run_dir, run_id):
    """
    Prefer real per-run CSV evidence. Search recursively inside the run
    directory and return rows whose run_id matches exactly.

    Files that are clearly resource files are ignored here because resource
    evidence is validated separately.
    """
    matches = []
    for path in sorted(run_dir.rglob("*.csv")):
        if path.name.startswith("resource_"):
            continue
        try:
            rows = read_csv(path)
        except Exception:
            continue
        for row in rows:
            if row.get("run_id") == run_id:
                matches.append((path, row))
    return matches

def index_aggregate_stream():
    if not KPI_STREAM.exists():
        return {}
    rows = read_csv(KPI_STREAM)
    by_run = defaultdict(list)
    for row in rows:
        run_id = row.get("run_id", "").strip()
        if run_id:
            by_run[run_id].append(row)
    return by_run

def validate_kpi_row(row, run_id, parsed):
    problems = []

    if row.get("run_id") != run_id:
        problems.append("kpi_run_id_mismatch")

    level = (row.get("security_level") or "").upper()
    if level and level != parsed["level"]:
        problems.append("kpi_security_level_mismatch")

    profile = normalize_profile(row.get("net_profile") or row.get("network_profile"))
    if profile and profile != parsed["profile"]:
        problems.append("kpi_net_profile_mismatch")

    repeat_text = row.get("repeat_index")
    if repeat_text not in (None, ""):
        try:
            if int(repeat_text) != parsed["repeat"]:
                problems.append("kpi_repeat_index_mismatch")
        except ValueError:
            problems.append("kpi_repeat_index_invalid")

    duration = row.get("duration_seconds") or row.get("measurement_duration_seconds")
    if duration not in (None, ""):
        try:
            if float(duration) < 55.0:
                problems.append("kpi_duration_too_short")
        except ValueError:
            problems.append("kpi_duration_invalid")

    expected = row.get("expected_messages")
    received = row.get("received_messages")
    if expected not in (None, ""):
        try:
            if int(float(expected)) < 1:
                problems.append("kpi_expected_messages_invalid")
        except ValueError:
            problems.append("kpi_expected_messages_invalid")
    if received not in (None, ""):
        try:
            if int(float(received)) < 0:
                problems.append("kpi_received_messages_invalid")
        except ValueError:
            problems.append("kpi_received_messages_invalid")

    return problems

def validate_resource(run_id, parsed):
    path = RESOURCE_DIR / f"resource_{run_id}.csv"
    result = {
        "path": path,
        "exists": path.exists(),
        "rows": 0,
        "span_s": 0.0,
        "components": [],
        "problems": [],
    }
    if not path.exists():
        result["problems"].append("resource_missing")
        return result

    try:
        rows = read_csv(path)
    except Exception as exc:
        result["problems"].append(f"resource_read_error:{type(exc).__name__}")
        return result

    result["rows"] = len(rows)
    if not rows:
        result["problems"].append("resource_empty")
        return result

    run_ids = {r.get("run_id", "") for r in rows if r.get("run_id", "")}
    if run_ids != {run_id}:
        result["problems"].append(
            "resource_run_id_mismatch:" + ",".join(sorted(run_ids))
        )

    levels = {
        (r.get("security_profile") or "").upper()
        for r in rows
        if r.get("security_profile")
    }
    if levels and levels != {parsed["level"]}:
        result["problems"].append(
            "resource_security_level_mismatch:" + ",".join(sorted(levels))
        )

    scenarios = {
        normalize_profile(r.get("scenario"))
        for r in rows
        if r.get("scenario")
    }
    if scenarios and scenarios != {parsed["profile"]}:
        result["problems"].append(
            "resource_profile_mismatch:" + ",".join(sorted(scenarios))
        )

    running = [
        r for r in rows
        if r.get("source") == "container" and r.get("status") == "running"
    ]
    components = sorted({
        r.get("component", "")
        for r in running
        if r.get("component")
    })
    result["components"] = components

    required = {"dds_publisher", "dds_subscriber"}
    if not required.issubset(set(components)):
        result["problems"].append(
            "resource_components_incomplete:" + ",".join(components)
        )

    elapsed = []
    for r in running:
        try:
            elapsed.append(float(r.get("elapsed_s", "")))
        except (TypeError, ValueError):
            pass
    if elapsed:
        result["span_s"] = max(elapsed) - min(elapsed)
        if result["span_s"] < MIN_RESOURCE_SPAN_S:
            result["problems"].append(
                f"resource_span_too_short:{result['span_s']:.1f}s"
            )
    else:
        result["problems"].append("resource_elapsed_missing")

    return result

def candidate_for_directory(run_dir, aggregate_index):
    run_id = run_dir.name
    parsed = parse_run_id(run_id)
    if parsed is None:
        return None

    cell = (parsed["level"], parsed["profile"], parsed["repeat"])
    per_run = find_per_run_kpi_rows(run_dir, run_id)

    # Per-run KPI evidence is preferred. Aggregate stream is only a
    # cross-check/fallback, never the sole source of candidate discovery.
    evidence_source = ""
    kpi_path = ""
    kpi_row = None
    problems = []

    if len(per_run) == 1:
        kpi_path, kpi_row = per_run[0]
        evidence_source = "per_run_csv"
    elif len(per_run) > 1:
        # Multiple files can legitimately repeat the same summary row, but we
        # flag it rather than silently choosing.
        kpi_path, kpi_row = per_run[-1]
        evidence_source = "per_run_csv_multiple"
        problems.append(f"multiple_per_run_kpi_rows:{len(per_run)}")
    else:
        aggregate_rows = aggregate_index.get(run_id, [])
        if len(aggregate_rows) == 1:
            kpi_row = aggregate_rows[0]
            kpi_path = KPI_STREAM
            evidence_source = "aggregate_stream_fallback"
        elif len(aggregate_rows) > 1:
            kpi_row = aggregate_rows[-1]
            kpi_path = KPI_STREAM
            evidence_source = "aggregate_stream_duplicate"
            problems.append(f"aggregate_duplicate_rows:{len(aggregate_rows)}")
        else:
            problems.append("kpi_evidence_missing")

    if kpi_row is not None:
        problems.extend(validate_kpi_row(kpi_row, run_id, parsed))

    resource = validate_resource(run_id, parsed)
    problems.extend(resource["problems"])

    return {
        "cell": cell,
        "run_id": run_id,
        "timestamp": parsed["timestamp"],
        "run_dir": run_dir,
        "kpi_path": Path(kpi_path) if kpi_path else None,
        "evidence_source": evidence_source,
        "resource": resource,
        "problems": problems,
        "valid": not problems,
        "kpi_row": kpi_row or {},
    }

def main():
    if not RUNS_DIR.exists():
        raise SystemExit(f"DDS run directory not found: {RUNS_DIR}")

    print("=== DDS EVIDENCE LAYOUT ===")
    print("Runs directory:", RUNS_DIR)
    print("KPI stream:", KPI_STREAM, "|", "FOUND" if KPI_STREAM.exists() else "MISSING")
    print("Resource directory:", RESOURCE_DIR)
    print()

    aggregate_index = index_aggregate_stream()

    candidates = defaultdict(list)
    excluded_non_core = []
    unmatched_dds_dirs = []

    for run_dir in sorted(RUNS_DIR.iterdir()):
        if not run_dir.is_dir() or not run_dir.name.startswith("dds_"):
            continue
        candidate = candidate_for_directory(run_dir, aggregate_index)
        if candidate is None:
            unmatched_dds_dirs.append(run_dir.name)
            continue

        level, profile, repeat = candidate["cell"]
        if (
            level in LEVELS
            and profile in PROFILES
            and repeat in REPEATS
        ):
            candidates[candidate["cell"]].append(candidate)
        else:
            excluded_non_core.append(candidate)

    expected = [
        (level, profile, repeat)
        for level in LEVELS
        for profile in PROFILES
        for repeat in REPEATS
    ]

    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    output_rows = []

    valid_cells = 0
    missing_cells = []
    invalid_cells = []
    duplicate_cells = []
    stale_candidates_total = 0

    print("=== DDS COMMON-CORE AUTHORITATIVE AUDIT ===")

    for cell in expected:
        level, profile, repeat = cell
        cell_candidates = sorted(
            candidates.get(cell, []),
            key=lambda c: (c["timestamp"], c["run_id"]),
        )
        valid_candidates = [c for c in cell_candidates if c["valid"]]

        if len(cell_candidates) > 1:
            duplicate_cells.append(cell)

        selected = valid_candidates[-1] if valid_candidates else None
        stale = [
            c for c in cell_candidates
            if selected is None or c["run_id"] != selected["run_id"]
        ]
        stale_candidates_total += len(stale)

        if selected:
            valid_cells += 1
            status = "SELECTED"
            resource = selected["resource"]
            kpi_row = selected["kpi_row"]

            print(
                f"{level} | {profile} | repeat={repeat} | "
                f"{status} | {selected['run_id']} | "
                f"candidates={len(cell_candidates)} | "
                f"valid={len(valid_candidates)} | "
                f"evidence={selected['evidence_source']} | "
                f"resource_rows={resource['rows']} | "
                f"resource_span={resource['span_s']:.1f}s"
            )

            output_rows.append({
                "protocol": "DDS",
                "security_level": level,
                "net_profile": profile,
                "repeat_index": repeat,
                "selection_status": status,
                "run_id": selected["run_id"],
                "run_timestamp": selected["timestamp"],
                "candidate_count": len(cell_candidates),
                "valid_candidate_count": len(valid_candidates),
                "stale_candidate_count": len(stale),
                "stale_run_ids": ";".join(c["run_id"] for c in stale),
                "kpi_evidence_source": selected["evidence_source"],
                "kpi_evidence_path": str(selected["kpi_path"]),
                "resource_path": str(resource["path"]),
                "resource_rows": resource["rows"],
                "resource_span_s": f"{resource['span_s']:.3f}",
                "resource_components": ";".join(resource["components"]),
                "duration_seconds": kpi_row.get("duration_seconds", ""),
                "expected_messages": kpi_row.get("expected_messages", ""),
                "received_messages": kpi_row.get("received_messages", ""),
                "latency_ms": kpi_row.get("latency_ms", ""),
                "jitter_ms": kpi_row.get("jitter_ms", ""),
                "throughput_messages_per_second":
                    kpi_row.get("throughput_messages_per_second", ""),
                "throughput_kbps": kpi_row.get("throughput_kbps", ""),
                "loss_percent": kpi_row.get("loss_percent", ""),
                "audit_problems": "",
            })
        else:
            status = "MISSING" if not cell_candidates else "INVALID"
            if status == "MISSING":
                missing_cells.append(cell)
            else:
                invalid_cells.append(cell)

            problem_text = " | ".join(
                f"{c['run_id']}=>{','.join(c['problems'])}"
                for c in cell_candidates
            ) or "no_candidate_run_directory"

            print(
                f"{level} | {profile} | repeat={repeat} | "
                f"{status} | candidates={len(cell_candidates)} | "
                f"problems={problem_text}"
            )

            output_rows.append({
                "protocol": "DDS",
                "security_level": level,
                "net_profile": profile,
                "repeat_index": repeat,
                "selection_status": status,
                "run_id": "",
                "run_timestamp": "",
                "candidate_count": len(cell_candidates),
                "valid_candidate_count": 0,
                "stale_candidate_count": len(cell_candidates),
                "stale_run_ids": ";".join(c["run_id"] for c in cell_candidates),
                "kpi_evidence_source": "",
                "kpi_evidence_path": "",
                "resource_path": "",
                "resource_rows": "",
                "resource_span_s": "",
                "resource_components": "",
                "duration_seconds": "",
                "expected_messages": "",
                "received_messages": "",
                "latency_ms": "",
                "jitter_ms": "",
                "throughput_messages_per_second": "",
                "throughput_kbps": "",
                "loss_percent": "",
                "audit_problems": problem_text,
            })

    fieldnames = list(output_rows[0].keys())
    with OUTPUT.open("w", newline="", encoding="utf-8") as f:
        writer = lf_dict_writer(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(output_rows)

    print("\n=== DUPLICATE / STALE CANDIDATES ===")
    if duplicate_cells:
        for cell in duplicate_cells:
            items = sorted(
                candidates[cell],
                key=lambda c: (c["timestamp"], c["run_id"]),
            )
            print(
                f"{cell[0]} | {cell[1]} | repeat={cell[2]} | "
                f"candidate_count={len(items)}"
            )
            for c in items:
                marker = "VALID" if c["valid"] else "INVALID"
                print(
                    f"  {marker:7s} | {c['run_id']} | "
                    f"evidence={c['evidence_source']} | "
                    f"problems={','.join(c['problems']) or 'none'}"
                )
    else:
        print("None")

    print("\n=== EXCLUDED NON-CORE DDS RUNS ===")
    if excluded_non_core:
        for c in sorted(excluded_non_core, key=lambda x: x["run_id"]):
            print(c["run_id"])
    else:
        print("None")

    print("\n=== UNMATCHED DDS DIRECTORIES ===")
    if unmatched_dds_dirs:
        for name in unmatched_dds_dirs:
            print(name)
    else:
        print("None")

    print("\n=== AGGREGATE STREAM CROSS-CHECK ===")
    print("Aggregate KPI run IDs:", len(aggregate_index))
    selected_ids = {r["run_id"] for r in output_rows if r["run_id"]}
    aggregate_ids = set(aggregate_index)
    print("Selected IDs present in aggregate:", len(selected_ids & aggregate_ids))
    print("Selected IDs absent from aggregate:", len(selected_ids - aggregate_ids))
    print("Aggregate IDs not selected:", len(aggregate_ids - selected_ids))

    print("\n=== TOTALS ===")
    print(f"Expected common-core cells: {len(expected)}")
    print(f"Authoritative valid cells: {valid_cells}")
    print(f"Missing cells: {len(missing_cells)}")
    print(f"Invalid cells: {len(invalid_cells)}")
    print(f"Cells with multiple historical candidates: {len(duplicate_cells)}")
    print(f"Stale/non-selected common-core candidates: {stale_candidates_total}")
    print(f"Manifest: {OUTPUT}")

    if valid_cells == len(expected):
        print("\nAUDIT VERDICT: PASS — 36/36")
    else:
        print(
            f"\nAUDIT VERDICT: FAIL — "
            f"{valid_cells}/{len(expected)} valid"
        )
        raise SystemExit(1)

if __name__ == "__main__":
    main()

