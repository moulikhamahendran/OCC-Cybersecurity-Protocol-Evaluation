import argparse
import os
import subprocess
import sys
import time
from pathlib import Path


TESTBED_DIR = Path(__file__).resolve().parents[1]

SERVER = (
    TESTBED_DIR
    / "protocols"
    / "opcua"
    / "opcua_server.py"
)

ATTACK_CLIENT = (
    TESTBED_DIR
    / "protocols"
    / "opcua"
    / "opcua_attack_client.py"
)

LOG_DIR = (
    TESTBED_DIR
    / "results"
    / "opcua"
    / "logs"
    / "attacks"
)

LOG_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


ATTACKS = {
    "C0": [
        "anonymous_access",
        "wrong_security",
        "unauthorized_write",
    ],

    "C1": [
        "anonymous_access",
        "invalid_credentials",
        "wrong_security",
        "unauthorized_write",
    ],

    "C2": [
        "anonymous_access",
        "invalid_credentials",
        "wrong_security",
        "unauthorized_write",
    ],
}


def run_one(
    level,
    attack,
    repeat,
    results_file,
):
    environment = os.environ.copy()

    environment[
        "OPCUA_SECURITY_LEVEL"
    ] = level

    environment[
        "REPEAT_INDEX"
    ] = str(repeat)

    environment[
        "PYTHONUNBUFFERED"
    ] = "1"

    log_path = (
        LOG_DIR
        / (
            f"{level.lower()}_"
            f"{attack}_"
            f"repeat_{repeat}_server.log"
        )
    )

    print()
    print("=" * 70)

    print(
        f"OPC UA {level} | "
        f"{attack} | "
        f"repeat {repeat}"
    )

    print("=" * 70)

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
            time.sleep(2)

            if server.poll() is not None:
                raise RuntimeError(
                    "Server exited early. "
                    f"See {log_path}"
                )

            subprocess.run(
                [
                    sys.executable,
                    str(ATTACK_CLIENT),
                    "--attack",
                    attack,
                    "--results-file",
                    str(results_file),
                ],
                env=environment,
                check=True,
            )

        finally:
            if server.poll() is None:
                server.terminate()

                try:
                    server.wait(
                        timeout=5
                    )

                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait()

            time.sleep(0.5)


def main():
    parser = argparse.ArgumentParser()

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
        "--repeats",
        type=int,
        default=3,
    )

    parser.add_argument(
        "--output",
        default=(
            "testbed/results/opcua/"
            "opcua_attack_security_results.csv"
        ),
    )

    args = parser.parse_args()

    if args.repeats < 1:
        raise ValueError(
            "repeats must be at least 1"
        )

    if (
        any(
            level in ("C1", "C2")
            for level in args.levels
        )
        and not os.getenv(
            "OPCUA_PASSWORD"
        )
    ):
        raise RuntimeError(
            "OPCUA_PASSWORD is not set"
        )

    results_file = Path(
        args.output
    )

    for level in args.levels:
        for attack in ATTACKS[level]:
            for repeat in range(
                1,
                args.repeats + 1,
            ):
                run_one(
                    level,
                    attack,
                    repeat,
                    results_file,
                )

    print()
    print(
        "All requested OPC UA "
        "security attack tests completed"
    )

    print(
        "Results:",
        results_file,
    )


if __name__ == "__main__":
    main()
