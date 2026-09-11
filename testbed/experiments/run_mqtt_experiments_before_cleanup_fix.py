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
    """
    NET-ideal uses the original broker ports directly.

    Every other NET-* profile uses the network-emulation
    proxy. This includes NET-proxy-ideal, which provides
    a zero-impairment proxy baseline.
    """
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


def check_broker(
    host: str,
    port: int,
) -> None:
    try:
        with socket.create_connection(
            (host, port),
            timeout=3,
        ):
            return

    except OSError as error:
        raise RuntimeError(
            f"MQTT endpoint unavailable at {host}:{port}. "
            "Check Docker Compose and the netem proxy."
        ) from error


def build_environment(
    security_level: str,
    repeat_index: int,
    net_profile: str,
) -> dict[str, str]:

    profile = SECURITY_PROFILES[security_level]

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

        username = os.getenv("MQTT_USERNAME")
        password = os.getenv("MQTT_PASSWORD")

        if not username or not password:
            raise RuntimeError(
                f"{security_level} requires "
                "MQTT_USERNAME and MQTT_PASSWORD "
                "environment variables."
            )

        environment["MQTT_USERNAME"] = username
        environment["MQTT_PASSWORD"] = password

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

        environment["MQTT_CA_CERT"] = str(
            CA_CERT_PATH
        )

    else:
        environment.pop(
            "MQTT_CA_CERT",
            None,
        )

    return environment


def stop_process(
    process: subprocess.Popen,
    process_name: str,
) -> None:

    if process.poll() is not None:
        return

    process.send_signal(
        signal.SIGINT
    )

    try:
        process.wait(
            timeout=5
        )

    except subprocess.TimeoutExpired:

        print(
            f"{process_name} did not stop normally; "
            "terminating it."
        )

        process.terminate()

        try:
            process.wait(
                timeout=3
            )

        except subprocess.TimeoutExpired:

            process.kill()
            process.wait()


def run_single_experiment(
    security_level: str,
    repeat_index: int,
    duration_seconds: float,
    net_profile: str,
) -> None:

    mqtt_host, mqtt_port = connection_target(
        security_level,
        net_profile,
    )

    check_broker(
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

    gateway_log_path = LOGS_DIR / (
        f"{run_name}_gateway.log"
    )

    publisher_log_path = LOGS_DIR / (
        f"{run_name}_publisher.log"
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

    if use_proxy(net_profile):
        print(
            "Network path: netem proxy"
        )
    else:
        print(
            "Network path: direct broker"
        )

    gateway_process = None
    publisher_process = None

    with gateway_log_path.open(
        "w",
        encoding="utf-8",
    ) as gateway_log, publisher_log_path.open(
        "w",
        encoding="utf-8",
    ) as publisher_log:

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
            )

            experiment_end = (
                time.monotonic()
                + duration_seconds
            )

            while (
                time.monotonic()
                < experiment_end
            ):

                if (
                    gateway_process.poll()
                    is not None
                ):
                    raise RuntimeError(
                        "Gateway stopped unexpectedly. "
                        f"Check {gateway_log_path}"
                    )

                if (
                    publisher_process.poll()
                    is not None
                ):
                    raise RuntimeError(
                        "Publisher stopped unexpectedly. "
                        f"Check {publisher_log_path}"
                    )

                time.sleep(
                    0.25
                )

        finally:

            if publisher_process is not None:
                stop_process(
                    publisher_process,
                    "Publisher",
                )

            time.sleep(
                0.5
            )

            if gateway_process is not None:
                stop_process(
                    gateway_process,
                    "Gateway",
                )

    print(
        f"Completed MQTT {security_level}, "
        f"network={net_profile}, "
        f"repeat={repeat_index}"
    )


def main() -> None:

    parser = argparse.ArgumentParser(
        description=(
            "Run repeatable MQTT C0, C1 and C2 "
            "experiments through either the direct "
            "broker path or the network-emulation proxy."
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
        help=(
            "MQTT security levels to test."
        ),
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
            "Network profile. NET-ideal uses "
            "the direct broker path. Any other "
            "profile uses the netem proxy."
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

    print()
    print(
        "MQTT experiment configuration"
    )

    print(
        f"Levels: "
        f"{', '.join(arguments.levels)}"
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
        f"Run logs: "
        f"{LOGS_DIR}"
    )


if __name__ == "__main__":
    main()
