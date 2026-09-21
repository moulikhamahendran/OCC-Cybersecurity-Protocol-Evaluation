import argparse
import os
import signal
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from mqtt_netem import (
    PROFILES as NETEM_PROFILES,
    configure_netem,
    qdisc_state,
    reset_netem,
    state_matches,
    write_netem_log,
)


TESTBED_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = TESTBED_DIR.parent

GATEWAY_PATH = TESTBED_DIR / "gateway" / "mqtt_gateway.py"
PUBLISHER_PATH = TESTBED_DIR / "vehicles" / "mqtt_publisher.py"
CA_CERT_PATH = TESTBED_DIR / "config" / "certs" / "ca.crt"

RESULTS_DIR = TESTBED_DIR / "results"
LOGS_DIR = RESULTS_DIR / "logs"

BROKER_HOST = os.getenv("MQTT_HOST", "127.0.0.1")
PROXY_HOST = os.getenv("MQTT_PROXY_HOST", "127.0.0.1")


SECURITY_PROFILES = {
    "C0": {
        "port": 1883,
        "tls": False,
        "authentication": False,
    },
    "C1": {
        "port": 1884,
        "tls": False,
        "authentication": True,
    },
    "C2": {
        "port": 8883,
        "tls": True,
        "authentication": True,
    },
}


PROXY_PORTS = {
    "C0": 2883,
    "C1": 2884,
    "C2": 9883,
}


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime(
        "%Y%m%dT%H%M%SZ"
    )


def use_proxy(net_profile: str) -> bool:
    return net_profile != "NET-ideal"


def connection_target(
    security_level: str,
    net_profile: str,
) -> tuple[str, int]:

    if use_proxy(net_profile):
        return (
            PROXY_HOST,
            PROXY_PORTS[security_level],
        )

    return (
        BROKER_HOST,
        SECURITY_PROFILES[security_level]["port"],
    )


def check_endpoint(
    host: str,
    port: int,
) -> None:

    try:
        with socket.create_connection(
            (host, port),
            timeout=3,
        ):
            pass

    except OSError as error:
        raise RuntimeError(
            f"MQTT endpoint unavailable at "
            f"{host}:{port}"
        ) from error


def process_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True

    except ProcessLookupError:
        return False

    except PermissionError:
        return True


def find_stale_testbed_processes() -> list[tuple[int, str]]:
    """
    Find old gateway/publisher processes from this repository.

    A stale process can continue writing KPI rows using an old
    RUN_ID and contaminate later experiments.
    """

    result = subprocess.run(
        [
            "ps",
            "-Ao",
            "pid=,command=",
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    gateway_path = str(GATEWAY_PATH)
    publisher_path = str(PUBLISHER_PATH)

    stale = []

    for line in result.stdout.splitlines():

        stripped = line.strip()

        if not stripped:
            continue

        parts = stripped.split(
            None,
            1,
        )

        if len(parts) != 2:
            continue

        try:
            pid = int(parts[0])

        except ValueError:
            continue

        if pid == os.getpid():
            continue

        command = parts[1]

        if gateway_path in command:
            stale.append(
                (pid, "Gateway")
            )

        elif publisher_path in command:
            stale.append(
                (pid, "Publisher")
            )

    return stale


def clean_stale_testbed_processes() -> None:
    stale = find_stale_testbed_processes()

    if not stale:
        return

    print()
    print(
        "WARNING: stale MQTT testbed "
        "processes detected."
    )

    for pid, name in stale:
        print(
            f"Stopping stale {name}: PID {pid}"
        )

        try:
            os.kill(
                pid,
                signal.SIGTERM,
            )

        except ProcessLookupError:
            continue

    deadline = time.monotonic() + 2.0

    while time.monotonic() < deadline:

        remaining = [
            (pid, name)
            for pid, name in stale
            if process_exists(pid)
        ]

        if not remaining:
            break

        time.sleep(0.1)

    for pid, name in stale:

        if not process_exists(pid):
            continue

        print(
            f"Force killing stale "
            f"{name}: PID {pid}"
        )

        try:
            os.kill(
                pid,
                signal.SIGKILL,
            )

        except ProcessLookupError:
            pass

    time.sleep(0.25)

    remaining = find_stale_testbed_processes()

    if remaining:
        raise RuntimeError(
            "Could not clean stale MQTT "
            f"processes: {remaining}"
        )


def build_environment(
    security_level: str,
    repeat_index: int,
    net_profile: str,
) -> dict[str, str]:

    profile = SECURITY_PROFILES[
        security_level
    ]

    mqtt_host, mqtt_port = connection_target(
        security_level,
        net_profile,
    )

    environment = os.environ.copy()

    environment.update(
        {
            "PYTHONUNBUFFERED": "1",
            "PROTOCOL": "MQTT",
            "MQTT_HOST": mqtt_host,
            "MQTT_PORT": str(mqtt_port),
            "MQTT_TLS": (
                "true"
                if profile["tls"]
                else "false"
            ),
            "MQTT_SECURITY_LEVEL": security_level,
            "NET_PROFILE": net_profile,
            "REPEAT_INDEX": str(repeat_index),
        }
    )

    if profile["authentication"]:

        username = os.getenv(
            "MQTT_USERNAME"
        )

        password = os.getenv(
            "MQTT_PASSWORD"
        )

        if not username or not password:
            raise RuntimeError(
                f"{security_level} requires "
                "MQTT_USERNAME and "
                "MQTT_PASSWORD."
            )

        environment[
            "MQTT_USERNAME"
        ] = username

        environment[
            "MQTT_PASSWORD"
        ] = password

    else:
        environment.pop(
            "MQTT_USERNAME",
            None,
        )

        environment.pop(
            "MQTT_PASSWORD",
            None,
        )

    if profile["tls"]:

        if not CA_CERT_PATH.exists():
            raise RuntimeError(
                f"CA certificate not found: "
                f"{CA_CERT_PATH}"
            )

        environment[
            "MQTT_CA_CERT"
        ] = str(CA_CERT_PATH)

    else:
        environment.pop(
            "MQTT_CA_CERT",
            None,
        )

    return environment


def signal_process_group(
    process: subprocess.Popen,
    sig: signal.Signals,
) -> None:

    if process.poll() is not None:
        return

    try:
        os.killpg(
            process.pid,
            sig,
        )

    except ProcessLookupError:
        pass


def stop_process(
    process: subprocess.Popen,
    process_name: str,
) -> None:

    if process.poll() is not None:
        return

    # Because every child is started with start_new_session=True,
    # its PID is also the process-group ID.
    signal_process_group(
        process,
        signal.SIGINT,
    )

    try:
        process.wait(
            timeout=5,
        )

        return

    except subprocess.TimeoutExpired:
        print(
            f"{process_name} ignored SIGINT; "
            "sending SIGTERM."
        )

    signal_process_group(
        process,
        signal.SIGTERM,
    )

    try:
        process.wait(
            timeout=3,
        )

        return

    except subprocess.TimeoutExpired:
        print(
            f"{process_name} ignored SIGTERM; "
            "sending SIGKILL."
        )

    signal_process_group(
        process,
        signal.SIGKILL,
    )

    process.wait(
        timeout=3,
    )


def _run_single_experiment_inner(
    security_level: str,
    repeat_index: int,
    duration_seconds: float,
    net_profile: str,
) -> str:

    # Critical isolation guard.
    # Nothing from an earlier experiment is allowed to survive.
    clean_stale_testbed_processes()

    mqtt_host, mqtt_port = connection_target(
        security_level,
        net_profile,
    )

    check_endpoint(
        mqtt_host,
        mqtt_port,
    )

    environment = build_environment(
        security_level=security_level,
        repeat_index=repeat_index,
        net_profile=net_profile,
    )

    run_name = (
        f"mqtt_{security_level.lower()}_"
        f"{net_profile.lower()}_"
        f"repeat_{repeat_index}_"
        f"{utc_timestamp()}_"
        f"{uuid4().hex[:8]}"
    )

    environment["RUN_ID"] = run_name

    resource_monitor_path = (
        TESTBED_DIR
        / "analysis"
        / "resource_monitor.py"
    )

    resource_output_path = (
        RESULTS_DIR
        / "resources"
        / f"resource_{run_name}.csv"
    )

    broker_containers = {
        "C0": "testbed-mqtt-1",
        "C1": "testbed-mqtt-c1-1",
        "C2": "testbed-mqtt-c2-1",
    }

    gateway_log_path = LOGS_DIR / (
        f"{run_name}_gateway.log"
    )

    publisher_log_path = LOGS_DIR / (
        f"{run_name}_publisher.log"
    )

    resource_log_path = LOGS_DIR / (
        f"{run_name}_resource_monitor.log"
    )

    print()
    print(
        f"Run ID: {run_name}"
    )

    print(
        f"Starting MQTT {security_level}, "
        f"network={net_profile}, "
        f"repeat={repeat_index}, "
        f"duration={duration_seconds} seconds"
    )

    print(
        f"MQTT endpoint: "
        f"{mqtt_host}:{mqtt_port}"
    )

    print(
        "Network path: "
        + (
            "netem proxy"
            if use_proxy(net_profile)
            else "direct broker"
        )
    )

    print(
        f"Resource results: {resource_output_path}"
    )

    gateway_process = None
    publisher_process = None
    resource_process = None

    with gateway_log_path.open(
        "w",
        encoding="utf-8",
    ) as gateway_log, publisher_log_path.open(
        "w",
        encoding="utf-8",
    ) as publisher_log, resource_log_path.open(
        "w",
        encoding="utf-8",
    ) as resource_log:

        try:
            gateway_process = subprocess.Popen(
                [
                    sys.executable,
                    str(GATEWAY_PATH),
                ],
                cwd=PROJECT_DIR,
                env=environment,
                stdout=gateway_log,
                stderr=subprocess.STDOUT,

                # Creates a dedicated process group so cleanup
                # can reliably terminate the entire experiment.
                start_new_session=True,
            )

            time.sleep(1.5)

            if gateway_process.poll() is not None:
                raise RuntimeError(
                    "Gateway failed to start. "
                    f"Check {gateway_log_path}"
                )

            publisher_process = subprocess.Popen(
                [
                    sys.executable,
                    str(PUBLISHER_PATH),
                ],
                cwd=PROJECT_DIR,
                env=environment,
                stdout=publisher_log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )

            resource_command = [
                sys.executable,
                str(resource_monitor_path),
                "--run-id",
                run_name,
                "--protocol",
                "MQTT",
                "--security-profile",
                security_level,
                "--scenario",
                net_profile,
                "--duration",
                str(duration_seconds + 5.0),
                "--interval",
                "1",
                "--process",
                "gateway=mqtt_gateway.py",
                "--process",
                "publisher=mqtt_publisher.py",
                "--container",
                (
                    "broker="
                    + broker_containers[security_level]
                ),
                "--output",
                str(resource_output_path),
            ]

            if use_proxy(net_profile):
                resource_command.extend(
                    [
                        "--container",
                        "netem_proxy=testbed-netem-proxy",
                    ]
                )

            resource_process = subprocess.Popen(
                resource_command,
                cwd=PROJECT_DIR,
                env=environment,
                stdout=resource_log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )

            time.sleep(0.5)

            if publisher_process.poll() is not None:
                raise RuntimeError(
                    "Publisher failed to start. "
                    f"Check {publisher_log_path}"
                )

            if resource_process.poll() is not None:
                raise RuntimeError(
                    "Resource monitor failed to start. "
                    f"Check {resource_log_path}"
                )

            experiment_end = (
                time.monotonic()
                + duration_seconds
            )

            while (
                time.monotonic()
                < experiment_end
            ):

                if gateway_process.poll() is not None:
                    raise RuntimeError(
                        "Gateway stopped unexpectedly. "
                        f"Check {gateway_log_path}"
                    )

                if publisher_process.poll() is not None:
                    raise RuntimeError(
                        "Publisher stopped unexpectedly. "
                        f"Check {publisher_log_path}"
                    )

                if resource_process.poll() is not None:
                    raise RuntimeError(
                        "Resource monitor stopped unexpectedly. "
                        f"Check {resource_log_path}"
                    )

                time.sleep(0.25)

        finally:

            # Stop publisher first so no new messages enter
            # the network while the gateway is shutting down.
            if publisher_process is not None:
                stop_process(
                    publisher_process,
                    "Publisher",
                )

            time.sleep(0.5)

            if gateway_process is not None:
                stop_process(
                    gateway_process,
                    "Gateway",
                )

            # Stop monitoring after the application processes so
            # their shutdown is included in the measurement window.
            if (
                resource_process is not None
                and resource_process.poll() is None
            ):
                stop_process(
                    resource_process,
                    "Resource monitor",
                )

    # Final process-level isolation check.
    stale_after_run = (
        find_stale_testbed_processes()
    )

    if stale_after_run:

        clean_stale_testbed_processes()

        raise RuntimeError(
            "Experiment processes remained alive "
            "after shutdown. They were terminated. "
            f"Invalid run: {run_name}"
        )

    if not resource_output_path.exists():
        raise RuntimeError(
            "Resource CSV was not created. "
            f"Invalid run: {run_name}. "
            f"Check {resource_log_path}"
        )

    print(
        f"Completed MQTT {security_level}, "
        f"network={net_profile}, "
        f"repeat={repeat_index}"
    )

    return run_name


def run_single_experiment(
    security_level: str,
    repeat_index: int,
    duration_seconds: float,
    net_profile: str,
) -> None:
    """
    Configure, verify, log, and always reset MQTT NetEm
    around one experiment.
    """

    if net_profile not in NETEM_PROFILES:
        raise ValueError(
            f"Unknown MQTT network profile {net_profile!r}; "
            f"expected one of {sorted(NETEM_PROFILES)}"
        )

    started = utc_timestamp()
    run_id = ""
    run_status = "FAILED"

    state_before = ""
    state_after = ""

    verified_before = False
    verified_after = False

    try:
        state_before = configure_netem(net_profile)
        verified_before = state_matches(
            net_profile,
            state_before,
        )

        run_id = _run_single_experiment_inner(
            security_level=security_level,
            repeat_index=repeat_index,
            duration_seconds=duration_seconds,
            net_profile=net_profile,
        )

        run_status = "COMPLETED"

    finally:
        try:
            if use_proxy(net_profile):
                state_after = qdisc_state(
                    with_stats=True
                )
                verified_after = state_matches(
                    net_profile,
                    state_after,
                )
            else:
                state_after = (
                    "not applicable: direct broker path"
                )
                verified_after = True

        except Exception as error:
            state_after = f"UNAVAILABLE: {error}"
            verified_after = False

        reset_netem()

        if not run_id:
            run_id = (
                f"mqtt_{security_level.lower()}_"
                f"{net_profile.lower()}_"
                f"repeat_{repeat_index}_"
                f"{started}_failed_before_run_id"
            )

        write_netem_log(
            LOGS_DIR / f"{run_id}_netem.log",
            run_id,
            net_profile,
            started,
            utc_timestamp(),
            run_status,
            verified_before,
            verified_after,
            state_before,
            state_after,
        )

    if not (
        verified_before
        and verified_after
        and run_status == "COMPLETED"
    ):
        raise RuntimeError(
            "MQTT NetEm verification failed. "
            f"Invalid run: {run_id}"
        )


def main() -> None:

    parser = argparse.ArgumentParser(
        description=(
            "Run isolated, repeatable MQTT "
            "C0/C1/C2 experiments."
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
        help="MQTT security levels.",
    )

    parser.add_argument(
        "--duration",
        type=float,
        default=10.0,
        help=(
            "Duration of each experiment "
            "in seconds."
        ),
    )

    parser.add_argument(
        "--repeats",
        type=int,
        default=1,
        help=(
            "Number of repetitions per "
            "security level."
        ),
    )

    parser.add_argument(
        "--net-profile",
        default="NET-ideal",
        help=(
            "NET-ideal uses direct broker "
            "ports. Other profiles use "
            "the network-emulation proxy."
        ),
    )

    arguments = parser.parse_args()

    if arguments.duration <= 0:
        parser.error(
            "--duration must be greater than zero"
        )

    if arguments.repeats <= 0:
        parser.error(
            "--repeats must be greater than zero"
        )

    LOGS_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    # Clean anything left behind by an earlier interrupted run.
    clean_stale_testbed_processes()

    print()
    print(
        "MQTT experiment configuration"
    )

    print(
        "Levels: "
        + ", ".join(arguments.levels)
    )

    print(
        f"Network profile: "
        f"{arguments.net_profile}"
    )

    print(
        f"Duration: "
        f"{arguments.duration} seconds"
    )

    print(
        f"Repeats: "
        f"{arguments.repeats}"
    )

    for security_level in arguments.levels:

        for repeat_index in range(
            1,
            arguments.repeats + 1,
        ):

            run_single_experiment(
                security_level=security_level,
                repeat_index=repeat_index,
                duration_seconds=arguments.duration,
                net_profile=arguments.net_profile,
            )

    print()
    print(
        "All requested MQTT experiments completed"
    )

    print(
        f"KPI results: "
        f"{RESULTS_DIR / 'kpi_stream.csv'}"
    )

    print(
        f"Run logs: {LOGS_DIR}"
    )


if __name__ == "__main__":
    main()
