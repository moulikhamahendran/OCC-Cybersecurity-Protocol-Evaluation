#!/usr/bin/env python3
"""Run controlled DDS application-layer flood experiments.

Threat model:
A compromised but authorized DDS publisher sends high-rate messages using
header IDs outside the legitimate publisher's expected range. This evaluates
availability under publisher flooding; it is not an unauthenticated network
attack.
"""

import argparse
import csv
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import run_dds_network_experiments as network


NETWORK_NAME = "occ_dds_dos_lab"
PROFILE = "DOS-authorized-publisher-flood"
RESULTS_ROOT = network.RESULTS_DIR / "dos"
SUMMARY_PATH = RESULTS_ROOT / "dds_dos_summary.csv"

SUMMARY_FIELDS = [
    "run_id",
    "security_level",
    "repeat",
    "legitimate_rate_mps",
    "legitimate_duration_s",
    "attack_rate_mps",
    "attack_duration_s",
    "attack_delay_s",
    "expected_legitimate_messages",
    "eligible_legitimate_messages",
    "received_legitimate_messages",
    "unexpected_attack_messages",
    "lost_legitimate_messages",
    "legitimate_loss_percent",
    "latency_ms",
    "jitter_ms",
    "throughput_messages_per_second",
    "subscriber_verdict",
    "publisher_exit_status",
    "attacker_exit_status",
    "subscriber_exit_status",
    "resource_monitor_exit_status",
    "attack_detected",
    "accounting_valid",
    "availability_outcome",
    "experiment_status",
    "threat_model",
]


def command(
    arguments: list[str],
    *,
    check: bool = True,
    capture_output: bool = False,
) -> subprocess.CompletedProcess:
    return subprocess.run(
        arguments,
        cwd=network.PROJECT_DIR,
        check=check,
        text=True,
        capture_output=capture_output,
    )


def ensure_network() -> None:
    inspected = command(
        ["docker", "network", "inspect", NETWORK_NAME],
        check=False,
        capture_output=True,
    )
    if inspected.returncode != 0:
        command(["docker", "network", "create", NETWORK_NAME])


def remove_container(name: str) -> None:
    network.remove_container(name)


def wait_container(name: str) -> int:
    result = command(
        ["docker", "wait", name],
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        return 125

    output = result.stdout.strip().splitlines()
    if not output:
        return 125

    return int(output[-1])


def save_container_log(name: str, output_path: Path) -> None:
    result = command(
        ["docker", "logs", name],
        check=False,
        capture_output=True,
    )
    output_path.write_text(
        result.stdout + result.stderr,
        encoding="utf-8",
    )


def start_monitor(
    run_id: str,
    level: str,
    duration: float,
    publisher_name: str,
    subscriber_name: str,
    attacker_name: str,
    output_path: Path,
    log_path: Path,
):
    log_file = log_path.open("w", encoding="utf-8")

    process = subprocess.Popen(
        [
            sys.executable,
            str(network.RESOURCE_MONITOR),
            "--run-id",
            run_id,
            "--protocol",
            "DDS",
            "--security-profile",
            level,
            "--scenario",
            PROFILE,
            "--duration",
            str(duration),
            "--interval",
            "1",
            "--container",
            f"dds_publisher={publisher_name}",
            "--container",
            f"dds_subscriber={subscriber_name}",
            "--container",
            f"dds_attacker={attacker_name}",
            "--output",
            str(output_path),
        ],
        cwd=network.PROJECT_DIR,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )

    return process, log_file


def stop_monitor(process, log_file) -> int:
    if process is None:
        return 125

    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)

    log_file.close()

    # SIGTERM after the measured containers finish is normal.
    if process.returncode in (0, -15):
        return 0

    return process.returncode


def docker_base(
    *,
    name: str,
    level: str,
    repeat: int,
    run_id: str,
    role: str,
) -> list[str]:
    return [
        "docker",
        "run",
        "-d",
        "--name",
        name,
        "--network",
        NETWORK_NAME,
        *network.docker_environment(
            level=level,
            profile=PROFILE,
            repeat=repeat,
            run_id=run_id,
            role=role,
        ),
        "-v",
        f"{network.PROJECT_DIR}:{network.CONTAINER_ROOT}",
    ]


def read_kpi(kpi_path: Path, run_id: str) -> dict[str, str]:
    if not kpi_path.exists():
        raise RuntimeError(f"DDS KPI file was not created: {kpi_path}")

    with kpi_path.open(newline="", encoding="utf-8") as file:
        rows = list(csv.DictReader(file))

    matches = [row for row in rows if row.get("run_id") == run_id]
    if len(matches) != 1:
        raise RuntimeError(
            f"Expected one KPI row for {run_id}, found {len(matches)}"
        )

    return matches[0]


def integer(row: dict[str, str], key: str) -> int:
    value = row.get(key, "")
    if value == "":
        return 0
    return int(float(value))


def decimal(row: dict[str, str], key: str) -> float:
    value = row.get(key, "")
    if value == "":
        return 0.0
    return float(value)


def append_summary(row: dict[str, object]) -> None:
    RESULTS_ROOT.mkdir(parents=True, exist_ok=True)
    write_header = not SUMMARY_PATH.exists()

    with SUMMARY_PATH.open(
        "a",
        newline="",
        encoding="utf-8",
    ) as file:
        writer = csv.DictWriter(file, fieldnames=SUMMARY_FIELDS)

        if write_header:
            writer.writeheader()

        writer.writerow(row)


def run_experiment(
    *,
    level: str,
    repeat: int,
    legitimate_rate: float,
    legitimate_duration: float,
    attack_rate: float,
    attack_duration: float,
    attack_delay: float,
    domain: int,
    attacker_cpus: float,
    attacker_memory: str,
) -> bool:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    token = uuid.uuid4().hex[:8]

    run_id = (
        f"dds_{level.lower()}_dos_repeat_{repeat}_"
        f"{timestamp}_{token}"
    )

    result_dir = RESULTS_ROOT / run_id
    result_dir.mkdir(parents=True, exist_ok=False)

    publisher_name = f"{run_id}_publisher"
    subscriber_name = f"{run_id}_subscriber"
    attacker_name = f"{run_id}_attacker"

    container_kpi = (
        f"{network.CONTAINER_ROOT}/"
        f"testbed/results/dds/dos/{run_id}/kpi.csv"
    )
    host_kpi = result_dir / "kpi.csv"
    resource_path = result_dir / "resources.csv"

    expected_messages = int(round(
        legitimate_rate * legitimate_duration
    ))

    monitor_process = None
    monitor_log_file = None

    publisher_status = 125
    attacker_status = 125
    subscriber_status = 125
    monitor_status = 125

    print("\n" + "=" * 72)
    print(
        f"Running DDS DoS: level={level}, repeat={repeat}, "
        f"run_id={run_id}"
    )
    print(
        f"Legitimate={legitimate_rate:g} msg/s for "
        f"{legitimate_duration:g}s; attacker={attack_rate:g} msg/s "
        f"for {attack_duration:g}s"
    )
    print("=" * 72)

    for name in (
        publisher_name,
        subscriber_name,
        attacker_name,
    ):
        remove_container(name)

    try:
        subscriber_command = [
            *docker_base(
                name=subscriber_name,
                level=level,
                repeat=repeat,
                run_id=run_id,
                role="subscriber",
            ),
            "-e",
            f"DDS_KPI_OUTPUT={container_kpi}",
            network.IMAGE,
            "python",
            "testbed/protocols/dds/dds_subscriber.py",
            "--domain",
            str(domain),
            "--duration",
            str(legitimate_duration + 15.0),
            "--measurement-duration",
            str(legitimate_duration),
            "--expected-messages",
            str(expected_messages),
        ]
        command(subscriber_command)

        time.sleep(1.0)

        publisher_command = [
            *docker_base(
                name=publisher_name,
                level=level,
                repeat=repeat,
                run_id=run_id,
                role="publisher",
            ),
            network.IMAGE,
            "python",
            "testbed/protocols/dds/dds_publisher.py",
            "--domain",
            str(domain),
            "--duration",
            str(legitimate_duration),
            "--rate",
            str(legitimate_rate),
            "--match-timeout",
            "20",
            "--serial-number",
            "VM-LEGITIMATE",
        ]
        command(publisher_command)

        time.sleep(attack_delay)

        attacker_command = [
            *docker_base(
                name=attacker_name,
                level=level,
                repeat=repeat,
                run_id=run_id,
                role="publisher",
            ),
            "--cpus",
            str(attacker_cpus),
            "--memory",
            attacker_memory,
            network.IMAGE,
            "python",
            "testbed/protocols/dds/dds_publisher.py",
            "--domain",
            str(domain),
            "--duration",
            str(attack_duration),
            "--rate",
            str(attack_rate),
            "--match-timeout",
            "20",
            "--serial-number",
            "VM-COMPROMISED",
            "--header-id-offset",
            "1000000",
        ]
        command(attacker_command)

        monitor_process, monitor_log_file = start_monitor(
            run_id=run_id,
            level=level,
            duration=legitimate_duration + 20.0,
            publisher_name=publisher_name,
            subscriber_name=subscriber_name,
            attacker_name=attacker_name,
            output_path=resource_path,
            log_path=result_dir / "resource_monitor.log",
        )

        publisher_status = wait_container(publisher_name)
        attacker_status = wait_container(attacker_name)
        subscriber_status = wait_container(subscriber_name)

    finally:
        if monitor_process is not None:
            monitor_status = stop_monitor(
                monitor_process,
                monitor_log_file,
            )

        for name, filename in (
            (publisher_name, "publisher.log"),
            (subscriber_name, "subscriber.log"),
            (attacker_name, "attacker.log"),
        ):
            save_container_log(name, result_dir / filename)
            remove_container(name)

    kpi = read_kpi(host_kpi, run_id)

    eligible = integer(kpi, "eligible_sent_messages")
    received = integer(kpi, "received_messages")
    unexpected = integer(kpi, "unexpected_messages")
    lost = integer(kpi, "lost_messages")

    accounting_valid = received + lost == eligible
    attack_detected = unexpected > 0

    experiment_passed = (
        attack_detected
        and accounting_valid
        and eligible == expected_messages
        and publisher_status == 0
        and attacker_status == 0
    )

    availability = "IMPACTED" if lost > 0 else "RESILIENT"

    summary = {
        "run_id": run_id,
        "security_level": level,
        "repeat": repeat,
        "legitimate_rate_mps": legitimate_rate,
        "legitimate_duration_s": legitimate_duration,
        "attack_rate_mps": attack_rate,
        "attack_duration_s": attack_duration,
        "attack_delay_s": attack_delay,
        "expected_legitimate_messages": expected_messages,
        "eligible_legitimate_messages": eligible,
        "received_legitimate_messages": received,
        "unexpected_attack_messages": unexpected,
        "lost_legitimate_messages": lost,
        "legitimate_loss_percent": decimal(kpi, "loss_percent"),
        "latency_ms": decimal(kpi, "latency_ms"),
        "jitter_ms": decimal(kpi, "jitter_ms"),
        "throughput_messages_per_second": decimal(
            kpi,
            "throughput_messages_per_second",
        ),
        "subscriber_verdict": kpi.get("verdict", ""),
        "publisher_exit_status": publisher_status,
        "attacker_exit_status": attacker_status,
        "subscriber_exit_status": subscriber_status,
        "resource_monitor_exit_status": monitor_status,
        "attack_detected": attack_detected,
        "accounting_valid": accounting_valid,
        "availability_outcome": availability,
        "experiment_status": (
            "PASS" if experiment_passed else "FAIL"
        ),
        "threat_model": "compromised_authorized_publisher_flood",
    }

    append_summary(summary)

    print(f"Expected legitimate: {expected_messages}")
    print(f"Eligible legitimate: {eligible}")
    print(f"Received legitimate: {received}")
    print(f"Unexpected attack messages: {unexpected}")
    print(f"Legitimate messages lost: {lost}")
    print(f"Availability outcome: {availability}")
    print(
        "Experiment status: "
        f"{summary['experiment_status']}"
    )
    print(f"Evidence: {result_dir}")

    return experiment_passed


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run reproducible DDS authorized-publisher flood "
            "availability experiments"
        )
    )
    parser.add_argument(
        "--levels",
        nargs="+",
        choices=["C0", "C1", "C2"],
        default=["C0", "C1", "C2"],
    )
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument(
        "--legitimate-rate",
        type=float,
        default=10.0,
    )
    parser.add_argument(
        "--legitimate-duration",
        type=float,
        default=60.0,
    )
    parser.add_argument(
        "--attack-rate",
        type=float,
        default=200.0,
    )
    parser.add_argument(
        "--attack-duration",
        type=float,
        default=30.0,
    )
    parser.add_argument(
        "--attack-delay",
        type=float,
        default=5.0,
    )
    parser.add_argument("--domain", type=int, default=0)
    parser.add_argument(
        "--attacker-cpus",
        type=float,
        default=0.50,
    )
    parser.add_argument(
        "--attacker-memory",
        default="256m",
    )
    return parser.parse_args()


def validate_arguments(arguments: argparse.Namespace) -> None:
    numeric_positive = {
        "repeats": arguments.repeats,
        "legitimate_rate": arguments.legitimate_rate,
        "legitimate_duration": arguments.legitimate_duration,
        "attack_rate": arguments.attack_rate,
        "attack_duration": arguments.attack_duration,
        "attacker_cpus": arguments.attacker_cpus,
    }

    for name, value in numeric_positive.items():
        if value <= 0:
            raise ValueError(f"{name} must be greater than zero")

    if arguments.attack_delay < 0:
        raise ValueError("attack_delay must not be negative")

    if arguments.attack_delay >= arguments.legitimate_duration:
        raise ValueError(
            "attack_delay must be shorter than legitimate_duration"
        )


def main() -> None:
    arguments = parse_arguments()
    validate_arguments(arguments)

    RESULTS_ROOT.mkdir(parents=True, exist_ok=True)
    ensure_network()

    total = len(arguments.levels) * arguments.repeats
    passed = 0

    print("DDS DoS experiment campaign")
    print(
        "Threat model: compromised authorized publisher "
        "application-layer flood"
    )
    print(f"Planned runs: {total}")

    for level in arguments.levels:
        for repeat in range(1, arguments.repeats + 1):
            if run_experiment(
                level=level,
                repeat=repeat,
                legitimate_rate=arguments.legitimate_rate,
                legitimate_duration=arguments.legitimate_duration,
                attack_rate=arguments.attack_rate,
                attack_duration=arguments.attack_duration,
                attack_delay=arguments.attack_delay,
                domain=arguments.domain,
                attacker_cpus=arguments.attacker_cpus,
                attacker_memory=arguments.attacker_memory,
            ):
                passed += 1

    print("\nDDS DOS CAMPAIGN SUMMARY")
    print(f"Passed: {passed}/{total}")
    print(f"Summary: {SUMMARY_PATH}")

    if passed != total:
        raise RuntimeError(
            f"{total - passed} DDS DoS experiment(s) failed"
        )

    print("PASS: all requested DDS DoS experiments validated")


if __name__ == "__main__":
    main()
