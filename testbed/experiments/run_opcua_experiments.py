import argparse
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


TESTBED_DIR = Path(__file__).resolve().parents[1]

SERVER = TESTBED_DIR / "protocols" / "opcua" / "opcua_server.py"
CLIENT = TESTBED_DIR / "protocols" / "opcua" / "opcua_benchmark_client.py"

LOG_DIR = TESTBED_DIR / "results" / "opcua" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

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


def run_command(command, check=True):
    return subprocess.run(
        command,
        check=check,
        text=True,
    )


def reset_netem():
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


def configure_netem(profile):
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


def endpoint_for(level, profile):
    if profile == "NET-ideal":
        port = PORTS_DIRECT[level]
    else:
        port = PORTS_PROXY[level]

    return f"opc.tcp://127.0.0.1:{port}/occ/"


def check_proxy():
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


def run_one(level, profile, repeat, duration):
    configure_netem(profile)

    endpoint = endpoint_for(
        level,
        profile,
    )

    timestamp = datetime.now(
        timezone.utc
    ).strftime("%Y%m%dT%H%M%SZ")

    label = (
        f"opcua_{level.lower()}_"
        f"{profile.lower()}_"
        f"repeat_{repeat}_"
        f"{timestamp}"
    )

    log_path = LOG_DIR / f"{label}_server.log"

    environment = os.environ.copy()
    environment["OPCUA_SECURITY_LEVEL"] = level
    environment["NET_PROFILE"] = profile
    environment["REPEAT_INDEX"] = str(repeat)
    environment["OPCUA_ENDPOINT"] = endpoint
    environment["PYTHONUNBUFFERED"] = "1"

    print()
    print("=" * 76)
    print(
        f"Starting OPC UA {level}, "
        f"network={profile}, "
        f"repeat={repeat}, "
        f"duration={duration:.1f}s"
    )
    print("Endpoint:", endpoint)
    print("=" * 76)

    with log_path.open(
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

        try:
            time.sleep(2.0)

            if server.poll() is not None:
                raise RuntimeError(
                    f"OPC UA server exited early. "
                    f"See {log_path}"
                )

            subprocess.run(
                [
                    sys.executable,
                    str(CLIENT),
                    "--duration",
                    str(duration),
                ],
                env=environment,
                check=True,
            )

        finally:
            if server.poll() is None:
                server.terminate()

                try:
                    server.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait()

            reset_netem()

    print(
        f"Completed OPC UA {level}, "
        f"network={profile}, "
        f"repeat={repeat}"
    )


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Run reproducible OPC UA "
            "network experiments"
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

    if (
        any(
            level in ("C1", "C2")
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

    print("OPC UA experiment configuration")
    print(
        "Levels:",
        ", ".join(arguments.levels),
    )
    print(
        "Network profiles:",
        ", ".join(arguments.net_profiles),
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
                        duration=arguments.duration,
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
        TESTBED_DIR
        / "results"
        / "opcua"
        / "opcua_kpi_stream.csv",
    )

    print(
        "Run data:",
        TESTBED_DIR
        / "results"
        / "opcua"
        / "runs",
    )


if __name__ == "__main__":
    main()
