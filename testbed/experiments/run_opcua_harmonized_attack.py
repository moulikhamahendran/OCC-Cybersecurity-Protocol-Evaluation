#!/usr/bin/env python3

"""Run harmonized OPC UA authorized read-service availability experiments."""

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


TESTBED_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = TESTBED_DIR.parent

IMAGE = "occ-opcua-smoke:local"

SERVER_SCRIPT = (
    TESTBED_DIR
    / "protocols"
    / "opcua"
    / "opcua_server.py"
)

BENCHMARK_SCRIPT = (
    TESTBED_DIR
    / "protocols"
    / "opcua"
    / "opcua_benchmark_client.py"
)

ATTACK_SCRIPT = (
    TESTBED_DIR
    / "experiments"
    / "opcua_harmonized_read_flood.py"
)

RESOURCE_MONITOR = (
    TESTBED_DIR
    / "analysis"
    / "resource_monitor.py"
)

RESULTS_ROOT = (
    TESTBED_DIR
    / "results"
    / "opcua"
    / "harmonized_security"
)

RUNS_ROOT = RESULTS_ROOT / "runs"

PORTS = {
    "C0": 4840,
    "C1": 4841,
    "C2": 4842,
}

PROFILE = "DOS-authorized-read-flood"


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime(
        "%Y%m%dT%H%M%SZ"
    )


def run_command(
    args: list[str],
    *,
    check: bool = True,
    capture_output: bool = False,
) -> subprocess.CompletedProcess:
    return subprocess.run(
        args,
        cwd=PROJECT_DIR,
        check=check,
        text=True,
        capture_output=capture_output,
    )


def docker_rm(name: str) -> None:
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


def env_args(
    environment: dict[str, str],
) -> list[str]:
    args = []

    for key, value in environment.items():
        args.extend(
            [
                "-e",
                f"{key}={value}",
            ]
        )

    return args


def ensure_image() -> None:
    result = run_command(
        [
            "docker",
            "image",
            "inspect",
            IMAGE,
        ],
        check=False,
        capture_output=True,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"Docker image {IMAGE!r} "
            "is not available."
        )


def wait_container(name: str) -> int:
    result = run_command(
        [
            "docker",
            "wait",
            name,
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


def save_container_log(
    name: str,
    path: Path,
) -> None:
    result = run_command(
        [
            "docker",
            "logs",
            name,
        ],
        check=False,
        capture_output=True,
    )

    path.write_text(
        result.stdout + result.stderr,
        encoding="utf-8",
    )


def run_one(
    *,
    level: str,
    repeat: int,
    duration: float,
    attack_delay: float,
    attack_duration: float,
    workers: int,
    attacker_cpus: float,
    attacker_memory: str,
) -> None:
    ensure_image()

    run_id = (
        f"opcua_{level.lower()}_"
        f"harmonized-dos_"
        f"repeat_{repeat}_"
        f"{utc_timestamp()}_"
        f"{uuid4().hex[:8]}"
    )

    short_id = uuid4().hex[:10]

    network_name = (
        f"occ-opcua-harmonized-{short_id}"
    )

    server_container = (
        f"opcua-harm-{short_id}-server"
    )

    client_container = (
        f"opcua-harm-{short_id}-client"
    )

    attacker_container = (
        f"opcua-harm-{short_id}-attacker"
    )

    run_dir = RUNS_ROOT / run_id
    run_dir.mkdir(
        parents=True,
        exist_ok=False,
    )

    server_log_path = (
        run_dir / "server.log"
    )

    client_log_path = (
        run_dir / "client.log"
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

    limits_path = (
        run_dir
        / "attacker_docker_limits.json"
    )

    metadata_path = (
        run_dir / "metadata.json"
    )

    password = os.getenv(
        "OPCUA_PASSWORD"
    )

    if level in ("C1", "C2") and not password:
        raise RuntimeError(
            "OPCUA_PASSWORD must be set "
            "for C1/C2"
        )

    endpoint = (
        f"opc.tcp://{server_container}:"
        f"{PORTS[level]}/occ/"
    )

    environment = {
        "RUN_ID": run_id,
        "OPCUA_SECURITY_LEVEL": level,
        "NET_PROFILE": "NET-ideal",
        "REPEAT_INDEX": str(repeat),
        "OPCUA_ENDPOINT": endpoint,
        "PYTHONUNBUFFERED": "1",
        "OPCUA_USERNAME": "occuser",
        # Keep benchmark-generated KPI run directories separate
        # from the harmonized orchestration/log directory. The
        # benchmark client creates its own runs/<RUN_ID> directory
        # with exist_ok=False.
        "OPCUA_RESULTS_DIR": (
            "/app/testbed/results/"
            "opcua/harmonized_security/benchmark"
        ),
    }

    if password:
        environment[
            "OPCUA_PASSWORD"
        ] = password

    run_command(
        [
            "docker",
            "network",
            "create",
            network_name,
        ]
    )

    benchmark_process = None
    resource_process = None

    benchmark_log = None
    resource_log = None

    attacker_started = False
    attacker_exit_status = None
    benchmark_exit_status = None

    started_wall = (
        datetime.now(
            timezone.utc
        ).isoformat()
    )

    started_monotonic = (
        time.monotonic()
    )

    print()
    print(f"Run ID: {run_id}")
    print(
        f"Starting OPC UA {level} "
        "harmonized availability experiment"
    )
    print(
        f"Legitimate duration: {duration}s"
    )
    print(
        f"Attack: t={attack_delay}s, "
        f"duration={attack_duration}s, "
        f"workers={workers}"
    )
    print(
        f"Attacker limit: "
        f"{attacker_cpus} CPU, "
        f"{attacker_memory}"
    )

    try:
        server_command = [
            "docker",
            "run",
            "-d",
            "--name",
            server_container,
            "--network",
            network_name,
            *env_args(environment),
            "-v",
            f"{PROJECT_DIR.resolve()}:/app",
            "-w",
            "/app",
            IMAGE,
            "python",
            "testbed/protocols/opcua/"
            "opcua_server.py",
        ]

        run_command(
            server_command
        )

        time.sleep(2.0)

        server_state = run_command(
            [
                "docker",
                "inspect",
                "-f",
                "{{.State.Running}}",
                server_container,
            ],
            capture_output=True,
        )

        if (
            server_state.stdout.strip()
            != "true"
        ):
            raise RuntimeError(
                "OPC UA server failed "
                "to start."
            )

        client_command = [
            "docker",
            "run",
            "--rm",
            "--name",
            client_container,
            "--network",
            network_name,
            *env_args(environment),
            "-v",
            f"{PROJECT_DIR.resolve()}:/app",
            "-w",
            "/app",
            IMAGE,
            "python",
            "testbed/protocols/opcua/"
            "opcua_benchmark_client.py",
            "--duration",
            str(duration),
        ]

        benchmark_log = (
            client_log_path.open(
                "w",
                encoding="utf-8",
            )
        )

        benchmark_process = (
            subprocess.Popen(
                client_command,
                cwd=PROJECT_DIR,
                stdout=benchmark_log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        )

        time.sleep(0.5)

        if (
            benchmark_process.poll()
            is not None
        ):
            raise RuntimeError(
                "OPC UA benchmark client "
                "failed to start."
            )

        resource_log = (
            resource_log_path.open(
                "w",
                encoding="utf-8",
            )
        )

        resource_command = [
            sys.executable,
            str(RESOURCE_MONITOR),
            "--run-id",
            run_id,
            "--protocol",
            "OPCUA",
            "--security-profile",
            level,
            "--scenario",
            PROFILE,
            "--duration",
            str(duration + 5.0),
            "--interval",
            "1",
            "--container",
            (
                "server="
                + server_container
            ),
            "--container",
            (
                "client="
                + client_container
            ),
            "--container",
            (
                "attacker="
                + attacker_container
            ),
            "--output",
            str(resource_output_path),
        ]

        resource_process = (
            subprocess.Popen(
                resource_command,
                cwd=PROJECT_DIR,
                stdout=resource_log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
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
            + duration
        )

        while (
            time.monotonic()
            < experiment_end
        ):
            now = time.monotonic()

            if (
                not attacker_started
                and now >= attack_start_at
            ):
                attacker_command = [
                    "docker",
                    "run",
                    "-d",
                    "--name",
                    attacker_container,
                    "--network",
                    network_name,
                    "--cpus",
                    str(attacker_cpus),
                    "--memory",
                    attacker_memory,
                    *env_args(environment),
                    "-v",
                    (
                        f"{PROJECT_DIR.resolve()}"
                        ":/app"
                    ),
                    "-w",
                    "/app",
                    IMAGE,
                    "python",
                    "testbed/experiments/"
                    "opcua_harmonized_read_flood.py",
                    "--duration",
                    str(attack_duration),
                    "--workers",
                    str(workers),
                ]

                run_command(
                    attacker_command
                )

                inspect_result = (
                    run_command(
                        [
                            "docker",
                            "inspect",
                            attacker_container,
                            "--format",
                            (
                                '{"NanoCpus":'
                                '{{.HostConfig.NanoCpus}},'
                                '"Memory":'
                                '{{.HostConfig.Memory}},'
                                '"MemorySwap":'
                                '{{.HostConfig.MemorySwap}}}'
                            ),
                        ],
                        capture_output=True,
                    )
                )

                limits_path.write_text(
                    (
                        inspect_result
                        .stdout
                        .strip()
                        + "\n"
                    ),
                    encoding="utf-8",
                )

                attacker_started = True

                print(
                    "Attack started at "
                    f"t≈{now - experiment_start:.2f}s"
                )

            if (
                benchmark_process.poll()
                is not None
                and time.monotonic()
                < experiment_end - 1.0
            ):
                raise RuntimeError(
                    "OPC UA benchmark client "
                    "stopped unexpectedly."
                )

            time.sleep(0.1)

        benchmark_exit_status = (
            benchmark_process.wait()
        )

        if benchmark_exit_status != 0:
            raise RuntimeError(
                "OPC UA benchmark client "
                f"failed with exit status "
                f"{benchmark_exit_status}."
            )

        if not attacker_started:
            raise RuntimeError(
                "OPC UA harmonized attacker "
                "never started."
            )

        attacker_exit_status = (
            wait_container(
                attacker_container
            )
        )

        save_container_log(
            attacker_container,
            attacker_log_path,
        )

        if attacker_exit_status != 0:
            raise RuntimeError(
                "OPC UA harmonized attacker "
                f"failed with exit status "
                f"{attacker_exit_status}. "
                f"Check {attacker_log_path}"
            )

        print(
            f"Completed OPC UA {level}, "
            f"repeat={repeat}"
        )

    finally:
        if (
            benchmark_process
            is not None
            and benchmark_process.poll()
            is None
        ):
            stop_process(
                benchmark_process
            )

        if (
            resource_process
            is not None
            and resource_process.poll()
            is None
        ):
            stop_process(
                resource_process
            )

        if benchmark_log is not None:
            benchmark_log.close()

        if resource_log is not None:
            resource_log.close()

        if attacker_started:
            if (
                not attacker_log_path.exists()
            ):
                save_container_log(
                    attacker_container,
                    attacker_log_path,
                )

        save_container_log(
            server_container,
            server_log_path,
        )

        docker_rm(
            attacker_container
        )

        docker_rm(
            client_container
        )

        docker_rm(
            server_container
        )

        run_command(
            [
                "docker",
                "network",
                "rm",
                network_name,
            ],
            check=False,
            capture_output=True,
        )

        ended_wall = (
            datetime.now(
                timezone.utc
            ).isoformat()
        )

        metadata = {
            "run_id": run_id,
            "protocol": "OPC UA",
            "security_level": level,
            "repeat": repeat,
            "scenario": PROFILE,
            "threat_model": (
                "compromised_authorized_"
                "client_read_flood"
            ),
            "legitimate_duration_s": duration,
            "attack_delay_s": attack_delay,
            "attack_duration_s": attack_duration,
            "attack_workers": workers,
            "attacker_cpu_limit": attacker_cpus,
            "attacker_memory_limit": attacker_memory,
            "endpoint": endpoint,
            "attacker_started": attacker_started,
            "attacker_exit_status": (
                attacker_exit_status
            ),
            "benchmark_exit_status": (
                benchmark_exit_status
            ),
            "started_utc": started_wall,
            "ended_utc": ended_wall,
            "runner_elapsed_s": round(
                time.monotonic()
                - started_monotonic,
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
        "--workers",
        type=int,
        default=5,
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

    if not 1 <= args.workers <= 20:
        raise ValueError(
            "workers must be between 1 and 20"
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
            run_one(
                level=level,
                repeat=repeat,
                duration=args.duration,
                attack_delay=args.attack_delay,
                attack_duration=args.attack_duration,
                workers=args.workers,
                attacker_cpus=args.attacker_cpus,
                attacker_memory=args.attacker_memory,
            )

    print()
    print(
        "All requested harmonized OPC UA "
        "experiments completed."
    )
    print(
        f"Results: {RUNS_ROOT}"
    )


if __name__ == "__main__":
    main()
