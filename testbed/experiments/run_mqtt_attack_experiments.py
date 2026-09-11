import argparse
import csv
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
ATTACK_PATH = TESTBED_DIR / "experiments" / "mqtt_attack_simulator.py"

CA_CERT_PATH = TESTBED_DIR / "config" / "certs" / "ca.crt"

RESULTS_DIR = TESTBED_DIR / "results"
LOGS_DIR = RESULTS_DIR / "logs"
RUNS_DIR = RESULTS_DIR / "runs"


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


EXPECTED_EVENT = {
    "malformed": "malformed_payload",
    "schema": "schema_violation",
    "replay": "replay",
    "stale": "stale_message",
    "spoofing": "spoofing",
    "dos": "dos_rate",
}


def utc_timestamp():
    return datetime.now(
        timezone.utc
    ).strftime("%Y%m%dT%H%M%SZ")


def check_broker(host, port):
    try:
        with socket.create_connection(
            (host, port),
            timeout=3,
        ):
            pass
    except OSError as error:
        raise RuntimeError(
            f"MQTT broker unavailable at "
            f"{host}:{port}"
        ) from error


def build_environment(
    security_level,
    repeat_index,
    attack,
):
    profile = SECURITY_PROFILES[
        security_level
    ]

    env = os.environ.copy()

    env.update(
        {
            "PYTHONUNBUFFERED": "1",
            "PROTOCOL": "MQTT",
            "MQTT_HOST": "127.0.0.1",
            "MQTT_PORT": profile["port"],
            "MQTT_TLS": profile["tls"],
            "MQTT_SECURITY_LEVEL": security_level,
            "NET_PROFILE": "NET-ideal",
            "REPEAT_INDEX": str(
                repeat_index
            ),
            "ATTACK_TYPE": attack,
            "TRUSTED_SERIAL_NUMBERS": "VM-001",
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
                "MQTT_USERNAME and MQTT_PASSWORD."
            )

        env["MQTT_USERNAME"] = username
        env["MQTT_PASSWORD"] = password

    else:
        env.pop(
            "MQTT_USERNAME",
            None,
        )
        env.pop(
            "MQTT_PASSWORD",
            None,
        )

    if profile["tls"] == "true":
        if not CA_CERT_PATH.exists():
            raise RuntimeError(
                f"CA certificate missing: "
                f"{CA_CERT_PATH}"
            )

        env["MQTT_CA_CERT"] = str(
            CA_CERT_PATH
        )

    else:
        env.pop(
            "MQTT_CA_CERT",
            None,
        )

    return env


def stop_process(process):
    if process.poll() is not None:
        return

    try:
        os.killpg(
            process.pid,
            signal.SIGINT,
        )
        process.wait(
            timeout=5
        )

    except subprocess.TimeoutExpired:
        try:
            os.killpg(
                process.pid,
                signal.SIGTERM,
            )
            process.wait(
                timeout=3
            )

        except subprocess.TimeoutExpired:
            os.killpg(
                process.pid,
                signal.SIGKILL,
            )
            process.wait()


def verify_attack(
    run_id,
    attack,
):
    events_path = (
        RUNS_DIR
        / run_id
        / "events.csv"
    )

    if not events_path.exists():
        return False, 0

    with events_path.open(
        newline="",
        encoding="utf-8",
    ) as f:
        rows = list(
            csv.DictReader(f)
        )

    expected = EXPECTED_EVENT[
        attack
    ]

    matches = [
        row
        for row in rows
        if (
            row.get("attack_type")
            == expected
            and row.get("action")
            == "BLOCK"
        )
    ]

    return bool(matches), len(matches)


def run_single_attack(
    security_level,
    attack,
    repeat_index,
):
    profile = SECURITY_PROFILES[
        security_level
    ]

    port = int(
        profile["port"]
    )

    check_broker(
        "127.0.0.1",
        port,
    )

    env = build_environment(
        security_level,
        repeat_index,
        attack,
    )

    run_id = (
        f"mqtt_attack_"
        f"{attack}_"
        f"{security_level.lower()}_"
        f"repeat_{repeat_index}_"
        f"{utc_timestamp()}_"
        f"{uuid4().hex[:8]}"
    )

    env["RUN_ID"] = run_id

    gateway_log_path = (
        LOGS_DIR
        / f"{run_id}_gateway.log"
    )

    attack_log_path = (
        LOGS_DIR
        / f"{run_id}_attack.log"
    )

    print()
    print("=" * 70)
    print(
        f"Attack: {attack} | "
        f"Level: {security_level} | "
        f"Repeat: {repeat_index}"
    )
    print(f"Run ID: {run_id}")
    print("=" * 70)

    gateway_process = None

    with gateway_log_path.open(
        "w",
        encoding="utf-8",
    ) as gateway_log, attack_log_path.open(
        "w",
        encoding="utf-8",
    ) as attack_log:

        try:
            gateway_process = (
                subprocess.Popen(
                    [
                        sys.executable,
                        str(
                            GATEWAY_PATH
                        ),
                    ],
                    cwd=PROJECT_DIR,
                    env=env,
                    stdout=gateway_log,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
            )

            time.sleep(1.5)

            if (
                gateway_process.poll()
                is not None
            ):
                raise RuntimeError(
                    "Gateway failed to start. "
                    f"Check {gateway_log_path}"
                )

            result = subprocess.run(
                [
                    sys.executable,
                    str(
                        ATTACK_PATH
                    ),
                    "--attack",
                    attack,
                ],
                cwd=PROJECT_DIR,
                env=env,
                stdout=attack_log,
                stderr=subprocess.STDOUT,
                timeout=30,
            )

            if result.returncode != 0:
                raise RuntimeError(
                    "Attack simulator failed. "
                    f"Check {attack_log_path}"
                )

            # Allow gateway to finish
            # processing queued messages.
            time.sleep(
                2.0
                if attack == "dos"
                else 1.0
            )

        finally:
            if (
                gateway_process
                is not None
            ):
                stop_process(
                    gateway_process
                )

    detected, count = verify_attack(
        run_id,
        attack,
    )

    if detected:
        print(
            f"PASS: {attack} detected "
            f"and blocked "
            f"({count} event(s))"
        )
    else:
        print(
            f"FAIL: expected "
            f"{EXPECTED_EVENT[attack]} "
            "BLOCK event not found"
        )

    return {
        "run_id": run_id,
        "security_level": security_level,
        "attack": attack,
        "repeat": repeat_index,
        "detected": detected,
        "events": count,
    }


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Run repeatable MQTT "
            "cybersecurity attack experiments."
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
        "--attacks",
        nargs="+",
        choices=[
            "malformed",
            "schema",
            "replay",
            "stale",
            "spoofing",
            "dos",
        ],
        default=[
            "malformed",
            "schema",
            "replay",
            "stale",
            "spoofing",
            "dos",
        ],
    )

    parser.add_argument(
        "--repeats",
        type=int,
        default=1,
    )

    args = parser.parse_args()

    if args.repeats <= 0:
        parser.error(
            "--repeats must be > 0"
        )

    LOGS_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    RUNS_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    print(
        "\nMQTT ATTACK EXPERIMENT MATRIX"
    )
    print(
        "Levels:",
        ", ".join(args.levels),
    )
    print(
        "Attacks:",
        ", ".join(args.attacks),
    )
    print(
        "Repeats:",
        args.repeats,
    )
    print(
        "Network: NET-ideal"
    )

    results = []

    for security_level in args.levels:
        for attack in args.attacks:
            for repeat_index in range(
                1,
                args.repeats + 1,
            ):
                results.append(
                    run_single_attack(
                        security_level,
                        attack,
                        repeat_index,
                    )
                )

    print()
    print("=" * 70)
    print("FINAL ATTACK SUMMARY")
    print("=" * 70)

    passed = 0

    for result in results:
        status = (
            "PASS"
            if result["detected"]
            else "FAIL"
        )

        if result["detected"]:
            passed += 1

        print(
            f"{status} | "
            f"{result['security_level']} | "
            f"{result['attack']} | "
            f"repeat={result['repeat']} | "
            f"events={result['events']} | "
            f"{result['run_id']}"
        )

    print()
    print(
        f"Successful detections: "
        f"{passed}/{len(results)}"
    )

    print(
        f"Logs: {LOGS_DIR}"
    )

    if passed != len(results):
        sys.exit(1)


if __name__ == "__main__":
    main()
