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
PUBLISHER_PATH = TESTBED_DIR / "protocols" / "mqtt" / "mqtt_publisher.py"
CA_CERT_PATH = TESTBED_DIR / "config" / "certs" / "ca.crt"
RESULTS_DIR = TESTBED_DIR / "results"
LOGS_DIR = RESULTS_DIR / "logs"

BROKER_HOST = os.getenv("MQTT_HOST", "127.0.0.1")

SECURITY_PROFILES = {
    "C0": {
        "port": "1883",
        "tls": "false",
        "authentication": False,
    },
    "C1": {
        "port": "1884",
        "tls": "false",
        "authentication": True,
    },
    "C2": {
        "port": "8883",
        "tls": "true",
        "authentication": True,
    },
}


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime(
        "%Y%m%dT%H%M%SZ"
    )


def check_broker(host: str, port: int) -> None:
    try:
        with socket.create_connection(
            (host, port),
            timeout=3,
        ):
            return
    except OSError as error:
        raise RuntimeError(
            f"MQTT broker is unavailable at {host}:{port}. "
            "Start Docker Compose before running experiments."
        ) from error


def build_environment(
    security_level: str,
    repeat_index: int,
    net_profile: str,
) -> dict[str, str]:
    profile = SECURITY_PROFILES[security_level]
    environment = os.environ.copy()

    environment.update(
        {
            "PYTHONUNBUFFERED": "1",
            "PROTOCOL": "MQTT",
            "MQTT_HOST": BROKER_HOST,
            "MQTT_PORT": profile["port"],
            "MQTT_TLS": profile["tls"],
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
                f"{security_level} requires MQTT_USERNAME "
                "and MQTT_PASSWORD environment variables."
            )

        environment["MQTT_USERNAME"] = username
        environment["MQTT_PASSWORD"] = password

    else:
        environment.pop("MQTT_USERNAME", None)
        environment.pop("MQTT_PASSWORD", None)

    if profile["tls"] == "true":
        if not CA_CERT_PATH.exists():
            raise RuntimeError(
                f"CA certificate not found: {CA_CERT_PATH}"
            )

        environment["MQTT_CA_CERT"] = str(CA_CERT_PATH)
    else:
        environment.pop("MQTT_CA_CERT", None)

    return environment


def stop_process(
    process: subprocess.Popen,
    process_name: str,
) -> None:
    if process.poll() is not None:
        return

    process.send_signal(signal.SIGINT)

    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        print(
            f"{process_name} did not stop normally; terminating it."
        )
        process.terminate()

        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def run_single_experiment(
    security_level: str,
    repeat_index: int,
    duration_seconds: float,
    net_profile: str,
) -> None:
    profile = SECURITY_PROFILES[security_level]
    broker_port = int(profile["port"])

    check_broker(BROKER_HOST, broker_port)

    environment = build_environment(
        security_level=security_level,
        repeat_index=repeat_index,
        net_profile=net_profile,
    )

    run_name = (
        f"mqtt_{security_level.lower()}_"
        f"{net_profile.lower()}_"
        f"repeat_{repeat_index}_"
        f"{utc_timestamp()}_{uuid4().hex[:8]}"
    )

    environment["RUN_ID"] = run_name

    gateway_log_path = LOGS_DIR / (
        f"{run_name}_gateway.log"
    )
    publisher_log_path = LOGS_DIR / (
        f"{run_name}_publisher.log"
    )

    print()
    print(f"Run ID: {run_name}")
    print(
        f"Starting MQTT {security_level}, "
        f"network={net_profile}, "
        f"repeat={repeat_index}, "
        f"duration={duration_seconds} seconds"
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
                time.monotonic() + duration_seconds
            )

            while time.monotonic() < experiment_end:
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

                time.sleep(0.25)

        finally:
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

    print(
        f"Completed MQTT {security_level}, "
        f"network={net_profile}, "
        f"repeat={repeat_index}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Run repeatable MQTT C0, C1 and C2 "
            "baseline experiments."
        )
    )

    parser.add_argument(
        "--levels",
        nargs="+",
        choices=["C0", "C1", "C2"],
        default=["C0", "C1", "C2"],
        help="MQTT security levels to test.",
    )

    parser.add_argument(
        "--duration",
        type=float,
        default=10.0,
        help="Duration of each experiment in seconds.",
    )

    parser.add_argument(
        "--repeats",
        type=int,
        default=1,
        help="Number of repetitions per security level.",
    )

    parser.add_argument(
        "--net-profile",
        default="NET-ideal",
        help="Network profile label written to KPI results.",
    )

    arguments = parser.parse_args()

    if arguments.duration <= 0:
        parser.error("--duration must be greater than zero")

    if arguments.repeats <= 0:
        parser.error("--repeats must be greater than zero")

    LOGS_DIR.mkdir(
        parents=True,
        exist_ok=True,
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
    print("All requested MQTT experiments completed")
    print(f"KPI results: {RESULTS_DIR / 'kpi_stream.csv'}")
    print(f"Run logs: {LOGS_DIR}")


if __name__ == "__main__":
    main()