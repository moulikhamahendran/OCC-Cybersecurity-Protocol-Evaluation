#!/usr/bin/env python3

import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

from run_dds_experiments import (
    LOG_DIR,
    PROJECT_DIR,
    RESOURCE_DIR,
    RESOURCE_MONITOR,
    RESULTS_DIR,
    stop_process,
    utc_timestamp,
    validate_kpi_results,
    validate_resource_results,
)


IMAGE = "occ-dds-security:11.0.1"
CONTAINER_ROOT = "/workspace"

SECURITY_CONFIG_DIR = (
    "/workspace/testbed/config/dds/"
    "security/container"
)

CONFIG_GENERATOR = (
    "testbed/config/dds/"
    "generate_container_runtime_configs.sh"
)

PROFILES = [
    "NET-ideal",
    "NET-delay",
    "NET-jitter",
    "NET-loss",
]

NETEM_COMMANDS = {
    "NET-ideal": None,
    "NET-delay": (
        "tc qdisc replace dev eth0 "
        "root netem delay 25ms"
    ),
    "NET-jitter": (
        "tc qdisc replace dev eth0 root "
        "netem delay 25ms 10ms distribution normal"
    ),
    "NET-loss": (
        "tc qdisc replace dev eth0 "
        "root netem loss 2%"
    ),
}


def run_command(command, **kwargs):
    return subprocess.run(
        command,
        check=True,
        text=True,
        **kwargs,
    )


def remove_container(name):
    subprocess.run(
        ["docker", "rm", "-f", name],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )


def remove_network(name):
    subprocess.run(
        ["docker", "network", "rm", name],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )


def wait_container(name):
    result = run_command(
        ["docker", "wait", name],
        capture_output=True,
    )

    output = result.stdout.strip()

    if not output:
        raise RuntimeError(
            f"Docker returned no exit status for {name}"
        )

    return int(output.splitlines()[-1])


def write_container_log(name, output_path):
    result = subprocess.run(
        ["docker", "logs", name],
        capture_output=True,
        text=True,
        check=False,
    )

    output_path.write_text(
        result.stdout + result.stderr,
        encoding="utf-8",
    )


def security_uri(level, role):
    if level == "C0":
        return None

    return (
        "file://"
        f"{SECURITY_CONFIG_DIR}/"
        f"{level.lower()}_{role}.xml"
    )


def docker_environment(
    level,
    profile,
    repeat,
    run_id=None,
    role=None,
):
    environment = [
        "-e",
        f"DDS_SECURITY_LEVEL={level}",
        "-e",
        f"NET_PROFILE={profile}",
        "-e",
        f"REPEAT_INDEX={repeat}",
        "-e",
        "PYTHONUNBUFFERED=1",
    ]

    if run_id is not None:
        environment.extend(
            ["-e", f"RUN_ID={run_id}"]
        )

    uri = (
        security_uri(level, role)
        if role is not None
        else None
    )

    if uri is not None:
        environment.extend(
            ["-e", f"CYCLONEDDS_URI={uri}"]
        )

    return environment


def start_resource_monitor(
    run_id,
    level,
    profile,
    duration,
    publisher_name,
    subscriber_name,
    output_path,
    log_file,
):
    return subprocess.Popen(
        [
            sys.executable,
            str(RESOURCE_MONITOR),
            "--run-id",
            run_id,
            "--protocol",
            "DDS",
            "--security-profile",
            level,
            "--scenario",
            profile,
            "--duration",
            str(duration),
            "--interval",
            "1",
            "--container",
            f"dds_publisher={publisher_name}",
            "--container",
            f"dds_subscriber={subscriber_name}",
            "--output",
            str(output_path),
        ],
        cwd=PROJECT_DIR,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )


def run_one(
    level,
    profile,
    repeat,
    duration,
    rate,
    domain,
    warmup,
    cooldown,
    match_timeout,
):
    expected_messages = round(duration * rate)

    if expected_messages < 1:
        raise ValueError(
            "duration and rate must produce "
            "at least one message"
        )

    subscriber_duration = (
        warmup
        + match_timeout
        + duration
        + cooldown
    )

    unique_id = uuid4().hex[:8]

    run_id = (
        f"dds_{level.lower()}_"
        f"{profile.lower()}_"
        f"repeat_{repeat}_"
        f"{utc_timestamp()}_"
        f"{unique_id}"
    )

    docker_suffix = unique_id.lower()
    network_name = f"occ-dds-net-{docker_suffix}"
    publisher_name = f"occ-dds-pub-{docker_suffix}"
    subscriber_name = f"occ-dds-sub-{docker_suffix}"

    publisher_log_path = (
        LOG_DIR / f"{run_id}_publisher.log"
    )
    subscriber_log_path = (
        LOG_DIR / f"{run_id}_subscriber.log"
    )
    resource_log_path = (
        LOG_DIR / f"{run_id}_resource.log"
    )
    resource_output_path = (
        RESOURCE_DIR / f"resource_{run_id}.csv"
    )

    monitor_process = None

    print()
    print("=" * 76)
    print(f"Run ID: {run_id}")
    print(
        f"Starting DDS {level}, "
        f"network={profile}, repeat={repeat}"
    )
    print(f"Expected messages: {expected_messages}")
    print("=" * 76)

    remove_container(publisher_name)
    remove_container(subscriber_name)
    remove_network(network_name)

    try:
        run_command(
            ["docker", "network", "create", network_name],
            stdout=subprocess.DEVNULL,
        )

        subscriber_command = [
            "docker",
            "run",
            "-d",
            "--name",
            subscriber_name,
            "--network",
            network_name,
            *docker_environment(
                level=level,
                profile=profile,
                repeat=repeat,
                run_id=run_id,
                role="subscriber",
            ),
            "-v",
            f"{PROJECT_DIR}:{CONTAINER_ROOT}",
            IMAGE,
            "python",
            "testbed/protocols/dds/dds_subscriber.py",
            "--domain",
            str(domain),
            "--duration",
            str(subscriber_duration),
            "--measurement-duration",
            str(duration),
            "--expected-messages",
            str(expected_messages),
        ]

        run_command(
            subscriber_command,
            stdout=subprocess.DEVNULL,
        )

        time.sleep(warmup)

        netem = NETEM_COMMANDS[profile]

        shell_parts = []

        if netem is not None:
            shell_parts.extend(
                [
                    netem,
                    "tc qdisc show dev eth0",
                ]
            )

        shell_parts.append(
            "exec python "
            "testbed/protocols/dds/dds_publisher.py "
            f"--domain {domain} "
            f"--duration {duration} "
            f"--rate {rate} "
            f"--match-timeout {match_timeout}"
        )

        publisher_command = [
            "docker",
            "run",
            "-d",
            "--name",
            publisher_name,
            "--network",
            network_name,
            "--cap-add",
            "NET_ADMIN",
            *docker_environment(
                level=level,
                profile=profile,
                repeat=repeat,
                role="publisher",
            ),
            "-v",
            f"{PROJECT_DIR}:{CONTAINER_ROOT}",
            IMAGE,
            "sh",
            "-c",
            " && ".join(shell_parts),
        ]

        run_command(
            publisher_command,
            stdout=subprocess.DEVNULL,
        )

        with resource_log_path.open(
            "w",
            encoding="utf-8",
        ) as resource_log:
            monitor_process = start_resource_monitor(
                run_id=run_id,
                level=level,
                profile=profile,
                duration=subscriber_duration,
                publisher_name=publisher_name,
                subscriber_name=subscriber_name,
                output_path=resource_output_path,
                log_file=resource_log,
            )

            publisher_status = wait_container(
                publisher_name
            )
            subscriber_status = wait_container(
                subscriber_name
            )

            stop_process(
                monitor_process,
                "DDS resource monitor",
            )

        write_container_log(
            publisher_name,
            publisher_log_path,
        )
        write_container_log(
            subscriber_name,
            subscriber_log_path,
        )

        if publisher_status != 0:
            raise RuntimeError(
                "DDS publisher container failed. "
                f"See {publisher_log_path}"
            )

        if subscriber_status != 0:
            raise RuntimeError(
                "DDS subscriber container failed. "
                f"See {subscriber_log_path}"
            )

        validate_kpi_results(
            run_id=run_id,
            expected_messages=expected_messages,
        )

        validate_resource_results(
            resource_path=resource_output_path,
            run_id=run_id,
        )

        print(
            f"Completed DDS {level}, "
            f"network={profile}, repeat={repeat}"
        )
        print(
            f"Resource results: "
            f"{resource_output_path}"
        )

    finally:
        stop_process(
            monitor_process,
            "DDS resource monitor",
        )
        remove_container(publisher_name)
        remove_container(subscriber_name)
        remove_network(network_name)


def prepare_environment():
    result = subprocess.run(
        ["docker", "image", "inspect", IMAGE],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"Docker image is missing: {IMAGE}"
        )

    run_command(
        [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{PROJECT_DIR}:{CONTAINER_ROOT}",
            IMAGE,
            "bash",
            CONFIG_GENERATOR,
        ],
        stdout=subprocess.DEVNULL,
    )


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Run DDS Docker network experiments "
            "with NetEm and resource monitoring"
        )
    )

    parser.add_argument(
        "--levels",
        nargs="+",
        choices=["C0", "C1", "C2"],
        default=["C0", "C1", "C2"],
    )
    parser.add_argument(
        "--net-profiles",
        nargs="+",
        choices=PROFILES,
        default=PROFILES,
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=60.0,
    )
    parser.add_argument(
        "--rate",
        type=float,
        default=10.0,
    )
    parser.add_argument(
        "--repeats",
        type=int,
        default=3,
    )
    parser.add_argument(
        "--domain",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--warmup",
        type=float,
        default=2.0,
    )
    parser.add_argument(
        "--cooldown",
        type=float,
        default=2.0,
    )
    parser.add_argument(
        "--match-timeout",
        type=float,
        default=20.0,
    )

    arguments = parser.parse_args()

    if arguments.duration <= 0:
        parser.error("--duration must be positive")
    if arguments.rate <= 0:
        parser.error("--rate must be positive")
    if arguments.repeats < 1:
        parser.error("--repeats must be at least one")
    if arguments.warmup < 0:
        parser.error("--warmup cannot be negative")
    if arguments.cooldown < 0:
        parser.error("--cooldown cannot be negative")
    if arguments.match_timeout <= 0:
        parser.error("--match-timeout must be positive")

    prepare_environment()

    print("DDS Docker network experiment configuration")
    print("Levels:", ", ".join(arguments.levels))
    print(
        "Network profiles:",
        ", ".join(arguments.net_profiles),
    )
    print("Duration:", arguments.duration)
    print("Rate:", arguments.rate)
    print("Repeats:", arguments.repeats)

    for profile in arguments.net_profiles:
        for level in arguments.levels:
            for repeat in range(
                1,
                arguments.repeats + 1,
            ):
                run_one(
                    level=level,
                    profile=profile,
                    repeat=repeat,
                    duration=arguments.duration,
                    rate=arguments.rate,
                    domain=arguments.domain,
                    warmup=arguments.warmup,
                    cooldown=arguments.cooldown,
                    match_timeout=(
                        arguments.match_timeout
                    ),
                )
                time.sleep(1)

    print()
    print(
        "All requested DDS Docker "
        "network experiments completed"
    )
    print(
        "KPI results:",
        RESULTS_DIR / "dds_kpi_stream.csv",
    )
    print("Resource results:", RESOURCE_DIR)


if __name__ == "__main__":
    main()
