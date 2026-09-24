#!/usr/bin/env python3

"""Run harmonized MQTT authorized-publisher availability experiments.

Threat model:
A compromised but authorized MQTT publisher sends schema-valid telemetry
through the normal broker path at sustained high rate.

Default harmonized methodology:
- legitimate workload: 60 s
- attacker starts: t = 5 s
- attack duration: 30 s
- attacker CPU limit: 0.50 CPU
- attacker memory limit: 256 MB
- attacker rate: 200 msg/s
- profiles: C0, C1, C2
- repeats: n = 3
"""

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import run_mqtt_experiments as base


TESTBED_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = TESTBED_DIR.parent

ATTACK_SCRIPT = (
    TESTBED_DIR
    / "experiments"
    / "mqtt_harmonized_flood.py"
)

RESOURCE_MONITOR = (
    TESTBED_DIR
    / "analysis"
    / "resource_monitor.py"
)

RESULTS_ROOT = (
    TESTBED_DIR
    / "results"
    / "mqtt"
    / "harmonized_security"
)

RUNS_ROOT = RESULTS_ROOT / "runs"

DOCKER_NETWORK = "testbed_mqtt_lab"
ATTACKER_IMAGE = "testbed-vehicle-publisher:latest"

PROFILE = "DOS-authorized-publisher-flood"

BROKER_CONTAINERS = {
    "C0": "testbed-mqtt-1",
    "C1": "testbed-mqtt-c1-1",
    "C2": "testbed-mqtt-c2-1",
}

ATTACK_TARGETS = {
    "C0": {
        "host": "mqtt",
        "port": 1883,
        "tls": False,
        "authentication": False,
    },
    "C1": {
        "host": "mqtt-c1",
        "port": 1883,
        "tls": False,
        "authentication": True,
    },
    "C2": {
        "host": "mqtt-c2",
        "port": 8883,
        "tls": True,
        "authentication": True,
    },
}


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime(
        "%Y%m%dT%H%M%SZ"
    )


def run_command(
    command: list[str],
    *,
    check: bool = True,
    capture_output: bool = False,
) -> subprocess.CompletedProcess:
    return subprocess.run(
        command,
        cwd=PROJECT_DIR,
        check=check,
        text=True,
        capture_output=capture_output,
    )


def remove_container(name: str) -> None:
    run_command(
        [
            "docker",
            "rm",
            "-f",
            name,
        ],
        check=False,
        capture_output=True,
    )


def stop_process(
    process: subprocess.Popen | None,
) -> None:
    if process is None:
        return

    if process.poll() is not None:
        return

    try:
        os.killpg(
            process.pid,
            signal.SIGTERM,
        )
    except ProcessLookupError:
        return

    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(
                process.pid,
                signal.SIGKILL,
            )
        except ProcessLookupError:
            pass

        process.wait(timeout=5)


def ensure_docker_network() -> None:
    result = run_command(
        [
            "docker",
            "network",
            "inspect",
            DOCKER_NETWORK,
        ],
        check=False,
        capture_output=True,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"Docker network {DOCKER_NETWORK!r} "
            "does not exist. Start testbed/compose.yaml first."
        )


def ensure_broker(level: str) -> None:
    container = BROKER_CONTAINERS[level]

    result = run_command(
        [
            "docker",
            "inspect",
            "-f",
            "{{.State.Running}}",
            container,
        ],
        check=False,
        capture_output=True,
    )

    if (
        result.returncode != 0
        or result.stdout.strip() != "true"
    ):
        raise RuntimeError(
            f"Required MQTT broker container "
            f"{container!r} is not running."
        )


def attacker_command(
    *,
    level: str,
    run_id: str,
    container_name: str,
    attack_duration: float,
    attack_rate: float,
    attacker_cpus: float,
    attacker_memory: str,
) -> list[str]:
    target = ATTACK_TARGETS[level]

    command = [
        "docker",
        "run",
        "-d",
        "--name",
        container_name,
        "--network",
        DOCKER_NETWORK,
        "--cpus",
        str(attacker_cpus),
        "--memory",
        attacker_memory,
        "-v",
        f"{PROJECT_DIR}:/workspace",
        "-w",
        "/workspace",
        ATTACKER_IMAGE,
        "python",
        "testbed/experiments/"
        "mqtt_harmonized_flood.py",
        "--host",
        target["host"],
        "--port",
        str(target["port"]),
        "--duration",
        str(attack_duration),
        "--rate",
        str(attack_rate),
        "--serial-number",
        "VM-COMPROMISED",
        "--header-id-offset",
        "1000000",
        "--client-id",
        (
            "mqtt-harmonized-attacker-"
            f"{run_id[-12:]}"
        ),
    ]

    if target["authentication"]:
        username = os.getenv("MQTT_USERNAME")
        password = os.getenv("MQTT_PASSWORD")

        if not username or not password:
            raise RuntimeError(
                f"{level} requires MQTT_USERNAME "
                "and MQTT_PASSWORD."
            )

        command.extend(
            [
                "--username",
                username,
                "--password",
                password,
            ]
        )

    if target["tls"]:
        command.extend(
            [
                "--tls",
                "--ca-cert",
                "/workspace/testbed/config/certs/ca.crt",
            ]
        )

    return command


def start_resource_monitor(
    *,
    run_id: str,
    level: str,
    duration: float,
    attacker_name: str,
    output_path: Path,
    log_path: Path,
    environment: dict[str, str],
):
    command = [
        sys.executable,
        str(RESOURCE_MONITOR),
        "--run-id",
        run_id,
        "--protocol",
        "MQTT",
        "--security-profile",
        level,
        "--scenario",
        PROFILE,
        "--duration",
        str(duration + 5.0),
        "--interval",
        "1",
        "--process",
        "gateway=mqtt_gateway.py",
        "--process",
        "publisher=mqtt_publisher.py",
        "--container",
        (
            "broker="
            + BROKER_CONTAINERS[level]
        ),
        "--container",
        (
            "attacker="
            + attacker_name
        ),
        "--output",
        str(output_path),
    ]

    log_file = log_path.open(
        "w",
        encoding="utf-8",
    )

    process = subprocess.Popen(
        command,
        cwd=PROJECT_DIR,
        env=environment,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )

    return process, log_file


def wait_for_attacker(
    container_name: str,
) -> int:
    result = run_command(
        [
            "docker",
            "wait",
            container_name,
        ],
        check=False,
        capture_output=True,
    )

    if result.returncode != 0:
        return 125

    lines = result.stdout.strip().splitlines()

    if not lines:
        return 125

    try:
        return int(lines[-1])
    except ValueError:
        return 125


def save_attacker_log(
    container_name: str,
    path: Path,
) -> None:
    result = run_command(
        [
            "docker",
            "logs",
            container_name,
        ],
        check=False,
        capture_output=True,
    )

    path.write_text(
        result.stdout + result.stderr,
        encoding="utf-8",
    )


def run_experiment(
    *,
    level: str,
    repeat: int,
    legitimate_duration: float,
    attack_delay: float,
    attack_duration: float,
    attack_rate: float,
    attacker_cpus: float,
    attacker_memory: str,
) -> None:
    base.clean_stale_testbed_processes()

    ensure_docker_network()
    ensure_broker(level)

    run_id = (
        f"mqtt_{level.lower()}_"
        f"harmonized-dos_"
        f"repeat_{repeat}_"
        f"{utc_timestamp()}_"
        f"{uuid4().hex[:8]}"
    )

    run_dir = RUNS_ROOT / run_id
    run_dir.mkdir(
        parents=True,
        exist_ok=False,
    )

    attacker_name = (
        "mqtt-harmonized-attacker-"
        + uuid4().hex[:10]
    )

    environment = base.build_environment(
        security_level=level,
        repeat_index=repeat,
        net_profile="NET-ideal",
    )

    environment["RUN_ID"] = run_id

    # Harmonized threat model:
    # VM-COMPROMISED represents an authorized endpoint whose
    # credentials/identity have been legitimately admitted but
    # whose publisher has been compromised.
    environment["TRUSTED_SERIAL_NUMBERS"] = (
        "VM-001,VM-COMPROMISED"
    )

    gateway_log_path = (
        run_dir / "gateway.log"
    )

    publisher_log_path = (
        run_dir / "publisher.log"
    )

    attacker_log_path = (
        run_dir / "attacker.log"
    )

    resource_log_path = (
        run_dir / "resource_monitor.log"
    )

    resource_output_path = (
        run_dir / "resources.csv"
    )

    metadata_path = (
        run_dir / "metadata.json"
    )

    gateway_process = None
    publisher_process = None
    resource_process = None

    gateway_log = None
    publisher_log = None
    resource_log = None

    attack_started = False
    attacker_exit_status = None

    started_wall = datetime.now(
        timezone.utc
    ).isoformat()

    started_monotonic = time.monotonic()

    print()
    print(f"Run ID: {run_id}")
    print(
        f"Starting MQTT {level} harmonized "
        f"availability experiment"
    )
    print(
        f"Legitimate duration: "
        f"{legitimate_duration}s"
    )
    print(
        f"Attack: t={attack_delay}s, "
        f"duration={attack_duration}s, "
        f"rate={attack_rate} msg/s"
    )
    print(
        f"Attacker limit: "
        f"{attacker_cpus} CPU, "
        f"{attacker_memory}"
    )

    try:
        gateway_log = gateway_log_path.open(
            "w",
            encoding="utf-8",
        )

        gateway_process = subprocess.Popen(
            [
                sys.executable,
                str(base.GATEWAY_PATH),
            ],
            cwd=PROJECT_DIR,
            env=environment,
            stdout=gateway_log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )

        time.sleep(1.0)

        if gateway_process.poll() is not None:
            raise RuntimeError(
                "Gateway failed to start. "
                f"Check {gateway_log_path}"
            )

        publisher_log = (
            publisher_log_path.open(
                "w",
                encoding="utf-8",
            )
        )

        publisher_process = subprocess.Popen(
            [
                sys.executable,
                str(base.PUBLISHER_PATH),
            ],
            cwd=PROJECT_DIR,
            env=environment,
            stdout=publisher_log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )

        resource_process, resource_log = (
            start_resource_monitor(
                run_id=run_id,
                level=level,
                duration=legitimate_duration,
                attacker_name=attacker_name,
                output_path=resource_output_path,
                log_path=resource_log_path,
                environment=environment,
            )
        )

        time.sleep(0.5)

        if (
            publisher_process.poll()
            is not None
        ):
            raise RuntimeError(
                "Publisher failed to start. "
                f"Check {publisher_log_path}"
            )

        if (
            resource_process.poll()
            is not None
        ):
            raise RuntimeError(
                "Resource monitor failed "
                "to start. "
                f"Check {resource_log_path}"
            )

        experiment_start = (
            time.monotonic()
        )

        attack_start_at = (
            experiment_start
            + attack_delay
        )

        experiment_end = (
            experiment_start
            + legitimate_duration
        )

        while (
            time.monotonic()
            < experiment_end
        ):
            now = time.monotonic()

            if (
                not attack_started
                and now >= attack_start_at
            ):
                command = attacker_command(
                    level=level,
                    run_id=run_id,
                    container_name=attacker_name,
                    attack_duration=attack_duration,
                    attack_rate=attack_rate,
                    attacker_cpus=attacker_cpus,
                    attacker_memory=attacker_memory,
                )

                run_command(command)

                # Preserve independent Docker evidence that the
                # harmonized attacker resource limits were applied.
                inspect_result = run_command(
                    [
                        "docker",
                        "inspect",
                        attacker_name,
                        "--format",
                        (
                            '{"NanoCpus":{{.HostConfig.NanoCpus}},'
                            '"Memory":{{.HostConfig.Memory}},'
                            '"MemorySwap":{{.HostConfig.MemorySwap}}}'
                        ),
                    ],
                    capture_output=True,
                )

                (
                    run_dir
                    / "attacker_docker_limits.json"
                ).write_text(
                    inspect_result.stdout.strip() + "\n",
                    encoding="utf-8",
                )

                attack_started = True

                print(
                    f"Attack started at "
                    f"t≈{now - experiment_start:.2f}s"
                )

            if (
                gateway_process.poll()
                is not None
            ):
                raise RuntimeError(
                    "Gateway stopped unexpectedly."
                )

            if (
                publisher_process.poll()
                is not None
            ):
                raise RuntimeError(
                    "Publisher stopped unexpectedly."
                )

            time.sleep(0.1)

        if attack_started:
            attacker_exit_status = (
                wait_for_attacker(
                    attacker_name
                )
            )

            save_attacker_log(
                attacker_name,
                attacker_log_path,
            )

            if attacker_exit_status != 0:
                raise RuntimeError(
                    "Harmonized MQTT attacker failed "
                    f"with exit status {attacker_exit_status}. "
                    f"Check {attacker_log_path}"
                )

        if not attack_started:
            raise RuntimeError(
                "Harmonized MQTT attacker never started."
            )

        print(
            f"Completed MQTT {level}, "
            f"repeat={repeat}"
        )

    finally:
        stop_process(publisher_process)
        stop_process(gateway_process)
        stop_process(resource_process)

        if gateway_log is not None:
            gateway_log.close()

        if publisher_log is not None:
            publisher_log.close()

        if resource_log is not None:
            resource_log.close()

        if attack_started:
            if not attacker_log_path.exists():
                save_attacker_log(
                    attacker_name,
                    attacker_log_path,
                )

            remove_container(
                attacker_name
            )

        ended_wall = datetime.now(
            timezone.utc
        ).isoformat()

        elapsed = (
            time.monotonic()
            - started_monotonic
        )

        metadata = {
            "run_id": run_id,
            "protocol": "MQTT",
            "security_level": level,
            "repeat": repeat,
            "scenario": PROFILE,
            "threat_model": (
                "compromised_authorized_"
                "publisher_flood"
            ),
            "legitimate_duration_s": (
                legitimate_duration
            ),
            "attack_delay_s": (
                attack_delay
            ),
            "attack_duration_s": (
                attack_duration
            ),
            "attack_rate_target_mps": (
                attack_rate
            ),
            "attacker_cpu_limit": (
                attacker_cpus
            ),
            "attacker_memory_limit": (
                attacker_memory
            ),
            "attacker_serial_number": (
                "VM-COMPROMISED"
            ),
            "attacker_header_id_offset": (
                1000000
            ),
            "attacker_qos": 0,
            "legitimate_qos": 1,
            "docker_network": (
                DOCKER_NETWORK
            ),
            "broker_container": (
                BROKER_CONTAINERS[level]
            ),
            "attacker_image": (
                ATTACKER_IMAGE
            ),
            "attack_started": (
                attack_started
            ),
            "attacker_exit_status": (
                attacker_exit_status
            ),
            "started_utc": (
                started_wall
            ),
            "ended_utc": (
                ended_wall
            ),
            "runner_elapsed_s": round(
                elapsed,
                6,
            ),
        }

        metadata_path.write_text(
            json.dumps(
                metadata,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--levels",
        nargs="+",
        choices=["C0", "C1", "C2"],
        default=["C0", "C1", "C2"],
    )

    parser.add_argument(
        "--repeats",
        type=int,
        default=3,
    )

    parser.add_argument(
        "--duration",
        type=float,
        default=60.0,
    )

    parser.add_argument(
        "--attack-delay",
        type=float,
        default=5.0,
    )

    parser.add_argument(
        "--attack-duration",
        type=float,
        default=30.0,
    )

    parser.add_argument(
        "--attack-rate",
        type=float,
        default=200.0,
    )

    parser.add_argument(
        "--attacker-cpus",
        type=float,
        default=0.50,
    )

    parser.add_argument(
        "--attacker-memory",
        default="256m",
    )

    args = parser.parse_args()

    if args.repeats < 1:
        raise ValueError(
            "repeats must be >= 1"
        )

    if args.duration <= 0:
        raise ValueError(
            "duration must be > 0"
        )

    if args.attack_delay < 0:
        raise ValueError(
            "attack-delay must be >= 0"
        )

    if args.attack_duration <= 0:
        raise ValueError(
            "attack-duration must be > 0"
        )

    if (
        args.attack_delay
        + args.attack_duration
        > args.duration
    ):
        raise ValueError(
            "attack window must fit "
            "inside legitimate duration"
        )

    RUNS_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    for level in args.levels:
        for repeat in range(
            1,
            args.repeats + 1,
        ):
            run_experiment(
                level=level,
                repeat=repeat,
                legitimate_duration=args.duration,
                attack_delay=args.attack_delay,
                attack_duration=args.attack_duration,
                attack_rate=args.attack_rate,
                attacker_cpus=args.attacker_cpus,
                attacker_memory=args.attacker_memory,
            )

    print()
    print(
        "All requested harmonized MQTT "
        "experiments completed."
    )
    print(
        f"Results: {RUNS_ROOT}"
    )


if __name__ == "__main__":
    main()
