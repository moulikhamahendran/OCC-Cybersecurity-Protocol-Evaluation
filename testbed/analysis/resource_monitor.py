#!/usr/bin/env python3

import argparse
import csv
import json
import os
import re
import signal
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import psutil


STOP_REQUESTED = False

CSV_FIELDS = [
    "run_id",
    "protocol",
    "security_profile",
    "scenario",
    "timestamp_utc",
    "elapsed_s",
    "component",
    "source",
    "identifier",
    "status",
    "cpu_percent",
    "memory_mb",
    "memory_percent",
]


def request_stop(_signum, _frame):
    global STOP_REQUESTED
    STOP_REQUESTED = True


def utc_timestamp():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def safe_filename(value):
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value)


def parse_mapping(values, option_name):
    mappings = {}

    for value in values:
        if "=" not in value:
            raise ValueError(
                f"{option_name} must use LABEL=VALUE format: {value}"
            )

        label, target = value.split("=", 1)
        label = label.strip()
        target = target.strip()

        if not label or not target:
            raise ValueError(
                f"{option_name} must use non-empty LABEL=VALUE format"
            )

        mappings[label] = target

    return mappings


def parse_percentage(value):
    if value is None:
        return None

    text = str(value).strip().replace("%", "")

    try:
        return round(float(text), 4)
    except ValueError:
        return None


def memory_to_mb(value):
    if value is None:
        return None

    text = str(value).strip().split("/")[0].strip()
    match = re.match(
        r"^([0-9.]+)\s*([KMGT]?i?B)$",
        text,
        re.IGNORECASE,
    )

    if not match:
        return None

    amount = float(match.group(1))
    unit = match.group(2).upper()

    factors = {
        "B": 1 / (1024 * 1024),
        "KB": 1 / 1024,
        "KIB": 1 / 1024,
        "MB": 1,
        "MIB": 1,
        "GB": 1024,
        "GIB": 1024,
        "TB": 1024 * 1024,
        "TIB": 1024 * 1024,
    }

    factor = factors.get(unit)

    if factor is None:
        return None

    return round(amount * factor, 4)


def make_row(
    args,
    elapsed_s,
    component,
    source,
    identifier,
    status,
    cpu_percent=None,
    memory_mb=None,
    memory_percent=None,
):
    return {
        "run_id": args.run_id,
        "protocol": args.protocol,
        "security_profile": args.security_profile,
        "scenario": args.scenario,
        "timestamp_utc": utc_timestamp(),
        "elapsed_s": round(elapsed_s, 3),
        "component": component,
        "source": source,
        "identifier": identifier,
        "status": status,
        "cpu_percent": cpu_percent,
        "memory_mb": memory_mb,
        "memory_percent": memory_percent,
    }


def sample_host(args, elapsed_s):
    memory = psutil.virtual_memory()

    return make_row(
        args=args,
        elapsed_s=elapsed_s,
        component="host",
        source="host",
        identifier="local-host",
        status="running",
        cpu_percent=round(psutil.cpu_percent(interval=None), 4),
        memory_mb=round(memory.used / (1024 * 1024), 4),
        memory_percent=round(memory.percent, 4),
    )


def find_processes(pattern):
    pattern = pattern.lower()
    matches = []

    for process in psutil.process_iter(
        ["pid", "name", "cmdline", "memory_info", "memory_percent"]
    ):
        if process.pid == os.getpid():
            continue

        try:
            name = process.info.get("name") or ""
            cmdline = " ".join(process.info.get("cmdline") or [])
            searchable_text = f"{name} {cmdline}".lower()

            if pattern in searchable_text:
                matches.append(process)

        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    return matches


def sample_process(args, elapsed_s, label, pattern):
    matches = find_processes(pattern)

    if not matches:
        return make_row(
            args=args,
            elapsed_s=elapsed_s,
            component=label,
            source="process",
            identifier=pattern,
            status="not_found",
        )

    total_cpu = 0.0
    total_memory_bytes = 0
    total_memory_percent = 0.0
    pids = []

    for process in matches:
        try:
            pids.append(str(process.pid))
            total_cpu += process.cpu_percent(interval=None)
            total_memory_bytes += process.memory_info().rss
            total_memory_percent += process.memory_percent()

        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    if not pids:
        return make_row(
            args=args,
            elapsed_s=elapsed_s,
            component=label,
            source="process",
            identifier=pattern,
            status="not_found",
        )

    return make_row(
        args=args,
        elapsed_s=elapsed_s,
        component=label,
        source="process",
        identifier=",".join(pids),
        status="running",
        cpu_percent=round(total_cpu, 4),
        memory_mb=round(
            total_memory_bytes / (1024 * 1024),
            4,
        ),
        memory_percent=round(total_memory_percent, 4),
    )


def read_docker_stats():
    command = [
        "docker",
        "stats",
        "--no-stream",
        "--format",
        "{{json .}}",
    ]

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )

    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None

    if result.returncode != 0:
        return None

    records = []

    for line in result.stdout.splitlines():
        line = line.strip()

        if not line:
            continue

        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    return records


def sample_containers(args, elapsed_s, container_targets):
    if not container_targets:
        return []

    docker_records = read_docker_stats()
    rows = []

    if docker_records is None:
        for label, container_name in container_targets.items():
            rows.append(
                make_row(
                    args=args,
                    elapsed_s=elapsed_s,
                    component=label,
                    source="container",
                    identifier=container_name,
                    status="docker_unavailable",
                )
            )

        return rows

    for label, container_name in container_targets.items():
        matched_record = None

        for record in docker_records:
            actual_name = str(
                record.get("Name")
                or record.get("Container")
                or ""
            )

            if (
                actual_name == container_name
                or container_name in actual_name
            ):
                matched_record = record
                break

        if matched_record is None:
            rows.append(
                make_row(
                    args=args,
                    elapsed_s=elapsed_s,
                    component=label,
                    source="container",
                    identifier=container_name,
                    status="not_found",
                )
            )
            continue

        actual_name = str(
            matched_record.get("Name")
            or matched_record.get("Container")
            or container_name
        )

        rows.append(
            make_row(
                args=args,
                elapsed_s=elapsed_s,
                component=label,
                source="container",
                identifier=actual_name,
                status="running",
                cpu_percent=parse_percentage(
                    matched_record.get("CPUPerc")
                ),
                memory_mb=memory_to_mb(
                    matched_record.get("MemUsage")
                ),
                memory_percent=parse_percentage(
                    matched_record.get("MemPerc")
                ),
            )
        )

    return rows


def build_argument_parser():
    parser = argparse.ArgumentParser(
        description=(
            "Record host, process and Docker resource usage "
            "for one experiment run."
        )
    )

    parser.add_argument(
        "--run-id",
        required=True,
    )

    parser.add_argument(
        "--protocol",
        required=True,
    )

    parser.add_argument(
        "--security-profile",
        required=True,
    )

    parser.add_argument(
        "--scenario",
        required=True,
    )

    parser.add_argument(
        "--duration",
        type=float,
        required=True,
    )

    parser.add_argument(
        "--interval",
        type=float,
        default=1.0,
    )

    parser.add_argument(
        "--process",
        action="append",
        default=[],
        metavar="LABEL=PATTERN",
        help=(
            "Monitor processes whose name or command "
            "contains PATTERN."
        ),
    )

    parser.add_argument(
        "--container",
        action="append",
        default=[],
        metavar="LABEL=NAME",
        help="Monitor a Docker container by name.",
    )

    parser.add_argument(
        "--output",
        help="Optional output CSV path.",
    )

    return parser


def main():
    parser = build_argument_parser()
    args = parser.parse_args()

    if args.duration <= 0:
        parser.error("--duration must be greater than zero")

    if args.interval <= 0:
        parser.error("--interval must be greater than zero")

    try:
        process_targets = parse_mapping(
            args.process,
            "--process",
        )

        container_targets = parse_mapping(
            args.container,
            "--container",
        )

    except ValueError as error:
        parser.error(str(error))

    if args.output:
        output_path = Path(args.output)
    else:
        output_path = (
            Path("testbed/results/resources")
            / f"resource_{safe_filename(args.run_id)}.csv"
        )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    signal.signal(
        signal.SIGINT,
        request_stop,
    )

    signal.signal(
        signal.SIGTERM,
        request_stop,
    )

    psutil.cpu_percent(interval=None)

    for pattern in process_targets.values():
        for process in find_processes(pattern):
            try:
                process.cpu_percent(interval=None)

            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

    start_time = time.monotonic()
    sample_count = 0

    with output_path.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=CSV_FIELDS,
        )

        writer.writeheader()
        csv_file.flush()

        while not STOP_REQUESTED:
            elapsed_s = time.monotonic() - start_time

            if elapsed_s > args.duration:
                break

            rows = [
                sample_host(
                    args,
                    elapsed_s,
                )
            ]

            for label, pattern in process_targets.items():
                rows.append(
                    sample_process(
                        args,
                        elapsed_s,
                        label,
                        pattern,
                    )
                )

            rows.extend(
                sample_containers(
                    args,
                    elapsed_s,
                    container_targets,
                )
            )

            writer.writerows(rows)
            csv_file.flush()

            sample_count += 1

            next_sample_time = (
                start_time
                + sample_count * args.interval
            )

            sleep_seconds = (
                next_sample_time
                - time.monotonic()
            )

            if sleep_seconds > 0:
                time.sleep(sleep_seconds)

    print(
        f"Resource monitoring completed: {output_path}"
    )

    print(
        f"Sampling rounds recorded: {sample_count}"
    )


if __name__ == "__main__":
    main()