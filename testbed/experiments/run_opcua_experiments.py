import argparse
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

SERVER = (
    TESTBED_DIR
    / "protocols"
    / "opcua"
    / "opcua_server.py"
)

CLIENT = (
    TESTBED_DIR
    / "protocols"
    / "opcua"
    / "opcua_benchmark_client.py"
)

RESOURCE_MONITOR = (
    TESTBED_DIR
    / "analysis"
    / "resource_monitor.py"
)

RESULTS_DIR = TESTBED_DIR / "results"
OPCUA_RESULTS_DIR = RESULTS_DIR / "opcua"
LOG_DIR = OPCUA_RESULTS_DIR / "logs"
RESOURCE_DIR = RESULTS_DIR / "resources"

LOG_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

RESOURCE_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


PORTS_DIRECT = {
    "C0": 4840,
    "C1": 4841,
    "C2": 4842,
}


PORTS_PROXY = {
    "C0": 14840,
    "C1": 14841,
    "C2": 14842,
}


PROFILES = [
    "NET-ideal",
    "NET-proxy-ideal",
    "NET-delay",
    "NET-jitter",
    "NET-loss",
]


def utc_timestamp() -> str:
    return datetime.now(
        timezone.utc
    ).strftime(
        "%Y%m%dT%H%M%SZ"
    )


def run_command(
    command,
    check=True,
):
    return subprocess.run(
        command,
        check=check,
        text=True,
    )


def reset_netem() -> None:
    subprocess.run(
        [
            "docker",
            "exec",
            "testbed-netem-proxy",
            "tc",
            "qdisc",
            "del",
            "dev",
            "eth0",
            "root",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def configure_netem(
    profile: str,
) -> None:
    reset_netem()

    if profile in (
        "NET-ideal",
        "NET-proxy-ideal",
    ):
        return

    base = [
        "docker",
        "exec",
        "testbed-netem-proxy",
        "tc",
        "qdisc",
        "replace",
        "dev",
        "eth0",
        "root",
        "netem",
    ]

    if profile == "NET-delay":
        command = base + [
            "delay",
            "25ms",
        ]

    elif profile == "NET-jitter":
        command = base + [
            "delay",
            "25ms",
            "10ms",
            "distribution",
            "normal",
        ]

    elif profile == "NET-loss":
        command = base + [
            "loss",
            "2%",
        ]

    else:
        raise ValueError(
            f"Unknown network profile: {profile}"
        )

    run_command(command)


def endpoint_for(
    level: str,
    profile: str,
) -> str:
    if profile == "NET-ideal":
        port = PORTS_DIRECT[level]
    else:
        port = PORTS_PROXY[level]

    return (
        f"opc.tcp://127.0.0.1:"
        f"{port}/occ/"
    )


def check_proxy() -> None:
    result = subprocess.run(
        [
            "docker",
            "inspect",
            "-f",
            "{{.State.Running}}",
            "testbed-netem-proxy",
        ],
        capture_output=True,
        text=True,
    )

    if (
        result.returncode != 0
        or result.stdout.strip() != "true"
    ):
        raise RuntimeError(
            "testbed-netem-proxy is not running"
        )


def stop_process(
    process: subprocess.Popen | None,
    name: str,
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

        process.wait()

    print(
        f"Stopped {name}"
    )


def start_resource_monitor(
    run_id: str,
    level: str,
    profile: str,
    duration: float,
    output_path: Path,
    log_file,
) -> subprocess.Popen:
    command = [
        sys.executable,
        str(RESOURCE_MONITOR),
        "--run-id",
        run_id,
        "--protocol",
        "OPCUA",
        "--security-profile",
        level,
        "--scenario",
        profile,
        "--duration",
        str(duration),
        "--interval",
        "1",
        "--process",
        "opcua_server=opcua_server.py",
        "--process",
        (
            "opcua_client="
            "opcua_benchmark_client.py"
        ),
        "--output",
        str(output_path),
    ]

    if profile != "NET-ideal":
        command.extend(
            [
                "--container",
                (
                    "netem_proxy="
                    "testbed-netem-proxy"
                ),
            ]
        )

    return subprocess.Popen(
        command,
        cwd=PROJECT_DIR,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )


def validate_resource_results(
    resource_path: Path,
    run_id: str,
) -> None:
    if not resource_path.exists():
        raise RuntimeError(
            "Resource-monitor CSV was not created "
            f"for run {run_id}"
        )

    if resource_path.stat().st_size == 0:
        raise RuntimeError(
            "Resource-monitor CSV is empty "
            f"for run {run_id}"
        )


def run_one(
    level: str,
    profile: str,
    repeat: int,
    duration: float,
) -> None:
    configure_netem(profile)

    endpoint = endpoint_for(
        level,
        profile,
    )

    run_id = (
        f"opcua_{level.lower()}_"
        f"{profile.lower()}_"
        f"repeat_{repeat}_"
        f"{utc_timestamp()}_"
        f"{uuid4().hex[:8]}"
    )

    server_log_path = (
        LOG_DIR
        / f"{run_id}_server.log"
    )

    client_log_path = (
        LOG_DIR
        / f"{run_id}_client.log"
    )

    resource_log_path = (
        LOG_DIR
        / f"{run_id}_resource.log"
    )

    resource_output_path = (
        RESOURCE_DIR
        / f"resource_{run_id}.csv"
    )

    environment = os.environ.copy()

    environment["RUN_ID"] = run_id
    environment["OPCUA_SECURITY_LEVEL"] = level
    environment["NET_PROFILE"] = profile
    environment["REPEAT_INDEX"] = str(repeat)
    environment["OPCUA_ENDPOINT"] = endpoint
    environment["PYTHONUNBUFFERED"] = "1"

    print()
    print("=" * 76)

    print(
        f"Run ID: {run_id}"
    )

    print(
        f"Starting OPC UA {level}, "
        f"network={profile}, "
        f"repeat={repeat}, "
        f"duration={duration:.1f}s"
    )

    print(
        f"Endpoint: {endpoint}"
    )

    print(
        "Network path: "
        + (
            "direct server"
            if profile == "NET-ideal"
            else "netem proxy"
        )
    )

    print("=" * 76)

    server_process = None
    client_process = None
    monitor_process = None

    with (
        server_log_path.open(
            "w",
            encoding="utf-8",
        ) as server_log,
        client_log_path.open(
            "w",
            encoding="utf-8",
        ) as client_log,
        resource_log_path.open(
            "w",
            encoding="utf-8",
        ) as resource_log,
    ):
        try:
            server_process = subprocess.Popen(
                [
                    sys.executable,
                    str(SERVER),
                ],
                cwd=PROJECT_DIR,
                env=environment,
                stdout=server_log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )

            time.sleep(2.0)

            if server_process.poll() is not None:
                raise RuntimeError(
                    "OPC UA server exited early. "
                    f"See {server_log_path}"
                )

            client_process = subprocess.Popen(
                [
                    sys.executable,
                    str(CLIENT),
                    "--duration",
                    str(duration),
                ],
                cwd=PROJECT_DIR,
                env=environment,
                stdout=client_log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )

            time.sleep(0.2)

            if client_process.poll() is not None:
                raise RuntimeError(
                    "OPC UA client exited early. "
                    f"See {client_log_path}"
                )

            monitor_process = (
                start_resource_monitor(
                    run_id=run_id,
                    level=level,
                    profile=profile,
                    duration=duration,
                    output_path=resource_output_path,
                    log_file=resource_log,
                )
            )

            client_return_code = (
                client_process.wait()
            )

            if client_return_code != 0:
                raise RuntimeError(
                    "OPC UA client failed. "
                    f"See {client_log_path}"
                )

            if monitor_process.poll() is None:
                try:
                    monitor_process.wait(
                        timeout=3
                    )
                except subprocess.TimeoutExpired:
                    stop_process(
                        monitor_process,
                        "resource monitor",
                    )

            if (
                monitor_process.returncode
                not in (
                    0,
                    -signal.SIGTERM,
                )
            ):
                raise RuntimeError(
                    "Resource monitor failed. "
                    f"See {resource_log_path}"
                )

        finally:
            stop_process(
                client_process,
                "OPC UA client",
            )

            stop_process(
                monitor_process,
                "resource monitor",
            )

            stop_process(
                server_process,
                "OPC UA server",
            )

            reset_netem()

    validate_resource_results(
        resource_path=resource_output_path,
        run_id=run_id,
    )

    print(
        f"Resource results: "
        f"{resource_output_path}"
    )

    print(
        f"Completed OPC UA {level}, "
        f"network={profile}, "
        f"repeat={repeat}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Run reproducible OPC UA network "
            "experiments with resource monitoring"
        )
    )

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
        "--repeats",
        type=int,
        default=3,
    )

    arguments = parser.parse_args()

    if arguments.repeats < 1:
        raise ValueError(
            "repeats must be at least 1"
        )

    if arguments.duration <= 0:
        raise ValueError(
            "duration must be greater than zero"
        )

    if not RESOURCE_MONITOR.exists():
        raise FileNotFoundError(
            "Resource monitor was not found: "
            f"{RESOURCE_MONITOR}"
        )

    if (
        any(
            level in (
                "C1",
                "C2",
            )
            for level in arguments.levels
        )
        and not os.getenv("OPCUA_PASSWORD")
    ):
        raise RuntimeError(
            "OPCUA_PASSWORD is not set"
        )

    if any(
        profile != "NET-ideal"
        for profile in arguments.net_profiles
    ):
        check_proxy()

    print(
        "OPC UA experiment configuration"
    )

    print(
        "Levels:",
        ", ".join(arguments.levels),
    )

    print(
        "Network profiles:",
        ", ".join(
            arguments.net_profiles
        ),
    )

    print(
        "Duration:",
        arguments.duration,
        "seconds",
    )

    print(
        "Repeats:",
        arguments.repeats,
    )

    try:
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
                        duration=(
                            arguments.duration
                        ),
                    )

                    time.sleep(1)

    finally:
        reset_netem()

    print()

    print(
        "All requested OPC UA "
        "experiments completed"
    )

    print(
        "KPI results:",
        OPCUA_RESULTS_DIR
        / "opcua_kpi_stream.csv",
    )

    print(
        "Run data:",
        OPCUA_RESULTS_DIR
        / "runs",
    )

    print(
        "Resource results:",
        RESOURCE_DIR,
    )


if __name__ == "__main__":
    main()