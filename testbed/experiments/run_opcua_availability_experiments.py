import argparse
import csv
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


TESTBED_DIR = Path(__file__).resolve().parents[1]

SERVER = (
    TESTBED_DIR
    / "protocols"
    / "opcua"
    / "opcua_server.py"
)

BENCHMARK = (
    TESTBED_DIR
    / "protocols"
    / "opcua"
    / "opcua_benchmark_client.py"
)

STRESS = (
    TESTBED_DIR
    / "protocols"
    / "opcua"
    / "opcua_stress_client.py"
)

LOG_DIR = (
    TESTBED_DIR
    / "results"
    / "opcua"
    / "logs"
    / "availability"
)

RESULTS_DIR = (
    TESTBED_DIR
    / "results"
    / "opcua"
)

LOG_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

RESULTS_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

STRESS_METRICS = (
    RESULTS_DIR
    / "opcua_availability_stress_metrics.csv"
)

ATTACKS = [
    "connection",
    "read",
    "subscription",
]


def parse_stress_log(text):
    values = {}

    mappings = {
        "Successful ops": "successful_ops",
        "Failed ops": "failed_ops",
        "Total ops": "total_ops",
        "Operations/sec": "operations_per_second",
    }

    for line in text.splitlines():
        for prefix, key in mappings.items():
            if line.strip().startswith(prefix):
                value = line.split(":", 1)[1].strip()

                try:
                    values[key] = float(value)
                except ValueError:
                    values[key] = value

    return values


def append_stress_metrics(row):
    exists = STRESS_METRICS.exists()

    with STRESS_METRICS.open(
        "a",
        newline="",
        encoding="utf-8",
    ) as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=row.keys(),
        )

        if not exists:
            writer.writeheader()

        writer.writerow(row)


def terminate_process(process):
    if process is None:
        return

    if process.poll() is None:
        process.terminate()

        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def run_one(
    level,
    attack,
    repeat,
    duration,
    workers,
    subscriptions_per_client,
):
    environment = os.environ.copy()

    environment["OPCUA_SECURITY_LEVEL"] = level
    environment["NET_PROFILE"] = f"STRESS-{attack}"
    environment["REPEAT_INDEX"] = str(repeat)
    environment["PYTHONUNBUFFERED"] = "1"

    stamp = datetime.now(
        timezone.utc
    ).strftime("%Y%m%dT%H%M%SZ")

    server_log_path = (
        LOG_DIR
        / f"{level}_{attack}_{repeat}_{stamp}_server.log"
    )

    stress_log_path = (
        LOG_DIR
        / f"{level}_{attack}_{repeat}_{stamp}_stress.log"
    )

    print()
    print("=" * 76)
    print(
        f"Starting OPC UA {level}, "
        f"stress={attack}, "
        f"repeat={repeat}, "
        f"benchmark={duration:.1f}s"
    )
    print("=" * 76)

    server = None
    stress = None

    try:
        with server_log_path.open(
            "w",
            encoding="utf-8",
        ) as server_log:

            server = subprocess.Popen(
                [
                    sys.executable,
                    str(SERVER),
                ],
                env=environment,
                stdout=server_log,
                stderr=subprocess.STDOUT,
            )

            time.sleep(2)

            if server.poll() is not None:
                raise RuntimeError(
                    f"Server exited early. "
                    f"See {server_log_path}"
                )

            stress_command = [
                sys.executable,
                str(STRESS),
                "--attack",
                attack,
                "--duration",
                str(duration + 2),
                "--workers",
                str(workers),
            ]

            if attack == "subscription":
                stress_command += [
                    "--subscriptions-per-client",
                    str(subscriptions_per_client),
                ]

            with stress_log_path.open(
                "w",
                encoding="utf-8",
            ) as stress_log:

                stress = subprocess.Popen(
                    stress_command,
                    env=environment,
                    stdout=stress_log,
                    stderr=subprocess.STDOUT,
                )

                time.sleep(1)

                subprocess.run(
                    [
                        sys.executable,
                        str(BENCHMARK),
                        "--duration",
                        str(duration),
                    ],
                    env=environment,
                    check=True,
                )

                stress.wait(timeout=duration + 15)

        stress_text = stress_log_path.read_text(
            encoding="utf-8"
        )

        metrics = parse_stress_log(
            stress_text
        )

        row = {
            "timestamp":
                datetime.now(
                    timezone.utc
                ).isoformat(),
            "security_level":
                level,
            "stress_type":
                attack,
            "repeat_index":
                repeat,
            "benchmark_duration_seconds":
                duration,
            "stress_workers":
                workers,
            "subscriptions_per_client":
                (
                    subscriptions_per_client
                    if attack == "subscription"
                    else 0
                ),
            "successful_ops":
                metrics.get(
                    "successful_ops",
                    "",
                ),
            "failed_ops":
                metrics.get(
                    "failed_ops",
                    "",
                ),
            "total_ops":
                metrics.get(
                    "total_ops",
                    "",
                ),
            "operations_per_second":
                metrics.get(
                    "operations_per_second",
                    "",
                ),
        }

        append_stress_metrics(row)

    finally:
        terminate_process(stress)
        terminate_process(server)

    print(
        f"Completed OPC UA {level}, "
        f"stress={attack}, "
        f"repeat={repeat}"
    )


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--levels",
        nargs="+",
        choices=[
            "C0",
            "C1",
            "C2",
        ],
        default=[
            "C0",
            "C1",
            "C2",
        ],
    )

    parser.add_argument(
        "--attacks",
        nargs="+",
        choices=ATTACKS,
        default=ATTACKS,
    )

    parser.add_argument(
        "--duration",
        type=float,
        default=60,
    )

    parser.add_argument(
        "--repeats",
        type=int,
        default=3,
    )

    parser.add_argument(
        "--workers",
        type=int,
        default=5,
    )

    parser.add_argument(
        "--subscriptions-per-client",
        type=int,
        default=5,
    )

    args = parser.parse_args()

    if args.repeats < 1:
        raise ValueError(
            "repeats must be at least 1"
        )

    if args.duration <= 0:
        raise ValueError(
            "duration must be greater than zero"
        )

    if (
        any(
            level in ("C1", "C2")
            for level in args.levels
        )
        and not os.getenv("OPCUA_PASSWORD")
    ):
        raise RuntimeError(
            "OPCUA_PASSWORD is not set"
        )

    for level in args.levels:
        for attack in args.attacks:
            for repeat in range(
                1,
                args.repeats + 1,
            ):
                run_one(
                    level=level,
                    attack=attack,
                    repeat=repeat,
                    duration=args.duration,
                    workers=args.workers,
                    subscriptions_per_client=(
                        args.subscriptions_per_client
                    ),
                )

                time.sleep(1)

    print()
    print(
        "All requested OPC UA "
        "availability experiments completed"
    )

    print(
        "Stress metrics:",
        STRESS_METRICS,
    )


if __name__ == "__main__":
    main()
