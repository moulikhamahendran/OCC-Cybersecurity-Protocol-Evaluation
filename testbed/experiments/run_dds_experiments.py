import argparse
import csv
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

PUBLISHER = (
    TESTBED_DIR
    / "protocols"
    / "dds"
    / "dds_publisher.py"
)

SUBSCRIBER = (
    TESTBED_DIR
    / "protocols"
    / "dds"
    / "dds_subscriber.py"
)

RESOURCE_MONITOR = (
    TESTBED_DIR
    / "analysis"
    / "resource_monitor.py"
)

SECURITY_DIR = (
    TESTBED_DIR
    / "config"
    / "dds"
    / "security"
)

RESULTS_DIR = (
    TESTBED_DIR
    / "results"
    / "dds"
)

LOG_DIR = RESULTS_DIR / "logs"
RESOURCE_DIR = (
    TESTBED_DIR
    / "results"
    / "resources"
)

LOG_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

RESOURCE_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


def utc_timestamp() -> str:
    return datetime.now(
        timezone.utc
    ).strftime("%Y%m%dT%H%M%SZ")


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

    print(f"Stopped {name}")


def security_config(
    level: str,
    role: str,
) -> Path | None:
    if level == "C0":
        return None

    return (
        SECURITY_DIR
        / f"{level.lower()}_{role}.xml"
    )


def build_environment(
    level: str,
    role: str,
    run_id: str,
    repeat: int,
    cyclonedds_home: Path,
) -> dict:
    environment = os.environ.copy()

    environment["RUN_ID"] = run_id
    environment["DDS_SECURITY_LEVEL"] = level
    environment["NET_PROFILE"] = "NET-ideal"
    environment["REPEAT_INDEX"] = str(repeat)
    environment["PYTHONUNBUFFERED"] = "1"

    if level == "C0":
        environment.pop(
            "CYCLONEDDS_URI",
            None,
        )
    else:
        config_path = security_config(
            level,
            role,
        )

        if (
            config_path is None
            or not config_path.exists()
        ):
            raise FileNotFoundError(
                "DDS Security configuration "
                f"was not found: {config_path}"
            )

        environment["CYCLONEDDS_HOME"] = str(
            cyclonedds_home
        )

        environment["CYCLONEDDS_URI"] = (
            config_path.resolve().as_uri()
        )

    return environment


def start_resource_monitor(
    run_id: str,
    level: str,
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
        "DDS",
        "--security-profile",
        level,
        "--scenario",
        "NET-ideal",
        "--duration",
        str(duration),
        "--interval",
        "1",
        "--process",
        "dds_publisher=dds_publisher.py",
        "--process",
        "dds_subscriber=dds_subscriber.py",
        "--output",
        str(output_path),
    ]

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
            "Resource CSV was not created "
            f"for {run_id}"
        )

    if resource_path.stat().st_size == 0:
        raise RuntimeError(
            "Resource CSV is empty "
            f"for {run_id}"
        )


def validate_kpi_results(
    run_id: str,
    expected_messages: int,
) -> None:
    summary_path = (
        RESULTS_DIR
        / "dds_kpi_stream.csv"
    )

    if not summary_path.exists():
        raise RuntimeError(
            "DDS KPI summary was not created"
        )

    with summary_path.open(
        newline="",
        encoding="utf-8",
    ) as summary_file:
        rows = list(
            csv.DictReader(summary_file)
        )

    matching_rows = [
        row
        for row in rows
        if row["run_id"] == run_id
    ]

    if len(matching_rows) != 1:
        raise RuntimeError(
            "Expected exactly one DDS KPI "
            f"row for {run_id}, found "
            f"{len(matching_rows)}"
        )

    row = matching_rows[0]

    if (
        int(row["expected_messages"])
        != expected_messages
    ):
        raise RuntimeError(
            "DDS KPI expected-message "
            "count does not match workload"
        )

    if int(row["invalid_messages"]) != 0:
        raise RuntimeError(
            "DDS run produced invalid messages"
        )


def run_one(
    level: str,
    repeat: int,
    duration: float,
    rate: float,
    domain: int,
    warmup: float,
    cooldown: float,
    match_timeout: float,
    cyclonedds_home: Path,
) -> None:
    expected_messages = round(
        duration * rate
    )

    subscriber_duration = (
        warmup
        + match_timeout
        + duration
        + cooldown
    )

    run_id = (
        f"dds_{level.lower()}_"
        "net-ideal_"
        f"repeat_{repeat}_"
        f"{utc_timestamp()}_"
        f"{uuid4().hex[:8]}"
    )

    publisher_log_path = (
        LOG_DIR
        / f"{run_id}_publisher.log"
    )

    subscriber_log_path = (
        LOG_DIR
        / f"{run_id}_subscriber.log"
    )

    resource_log_path = (
        LOG_DIR
        / f"{run_id}_resource.log"
    )

    resource_output_path = (
        RESOURCE_DIR
        / f"resource_{run_id}.csv"
    )

    publisher_environment = (
        build_environment(
            level=level,
            role="publisher",
            run_id=run_id,
            repeat=repeat,
            cyclonedds_home=cyclonedds_home,
        )
    )

    subscriber_environment = (
        build_environment(
            level=level,
            role="subscriber",
            run_id=run_id,
            repeat=repeat,
            cyclonedds_home=cyclonedds_home,
        )
    )

    print()
    print("=" * 76)
    print(f"Run ID: {run_id}")
    print(
        f"Starting DDS {level}, "
        "network=NET-ideal, "
        f"repeat={repeat}, "
        f"duration={duration:.1f}s"
    )
    print(f"Domain: {domain}")
    print(
        f"Expected messages: "
        f"{expected_messages}"
    )
    print("=" * 76)

    publisher_process = None
    subscriber_process = None
    monitor_process = None

    with (
        publisher_log_path.open(
            "w",
            encoding="utf-8",
        ) as publisher_log,
        subscriber_log_path.open(
            "w",
            encoding="utf-8",
        ) as subscriber_log,
        resource_log_path.open(
            "w",
            encoding="utf-8",
        ) as resource_log,
    ):
        try:
            subscriber_process = (
                subprocess.Popen(
                    [
                        sys.executable,
                        str(SUBSCRIBER),
                        "--domain",
                        str(domain),
                        "--duration",
                        str(subscriber_duration),
                        "--measurement-duration",
                        str(duration),
                        "--expected-messages",
                        str(expected_messages),
                    ],
                    cwd=PROJECT_DIR,
                    env=subscriber_environment,
                    stdout=subscriber_log,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
            )

            time.sleep(0.5)

            if (
                subscriber_process.poll()
                is not None
            ):
                raise RuntimeError(
                    "DDS subscriber exited early. "
                    f"See {subscriber_log_path}"
                )

            monitor_process = (
                start_resource_monitor(
                    run_id=run_id,
                    level=level,
                    duration=subscriber_duration,
                    output_path=(
                        resource_output_path
                    ),
                    log_file=resource_log,
                )
            )

            time.sleep(warmup)

            publisher_process = (
                subprocess.Popen(
                    [
                        sys.executable,
                        str(PUBLISHER),
                        "--domain",
                        str(domain),
                        "--duration",
                        str(duration),
                        "--rate",
                        str(rate),
                        "--match-timeout",
                        str(match_timeout),
                    ],
                    cwd=PROJECT_DIR,
                    env=publisher_environment,
                    stdout=publisher_log,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
            )

            publisher_return_code = (
                publisher_process.wait()
            )

            if publisher_return_code != 0:
                raise RuntimeError(
                    "DDS publisher failed. "
                    f"See {publisher_log_path}"
                )

            subscriber_return_code = (
                subscriber_process.wait()
            )

            if subscriber_return_code != 0:
                raise RuntimeError(
                    "DDS subscriber failed. "
                    f"See {subscriber_log_path}"
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
                publisher_process,
                "DDS publisher",
            )

            stop_process(
                subscriber_process,
                "DDS subscriber",
            )

            stop_process(
                monitor_process,
                "resource monitor",
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
        f"Resource results: "
        f"{resource_output_path}"
    )

    print(
        f"Completed DDS {level}, "
        "network=NET-ideal, "
        f"repeat={repeat}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Run reproducible DDS ideal-network "
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
        default=10.0,
    )

    parser.add_argument(
        "--cyclonedds-home",
        type=Path,
        default=Path(
            os.getenv(
                "CYCLONEDDS_HOME",
                (
                    Path.home()
                    / ".local"
                    / (
                        "cyclonedds-"
                        "11.0.1-security"
                    )
                ),
            )
        ),
    )

    arguments = parser.parse_args()

    if arguments.duration <= 0:
        raise ValueError(
            "duration must be greater than zero"
        )

    if arguments.rate <= 0:
        raise ValueError(
            "rate must be greater than zero"
        )

    if arguments.repeats < 1:
        raise ValueError(
            "repeats must be at least one"
        )

    if arguments.warmup < 0:
        raise ValueError(
            "warmup cannot be negative"
        )

    if arguments.cooldown < 0:
        raise ValueError(
            "cooldown cannot be negative"
        )

    if arguments.match_timeout <= 0:
        raise ValueError(
            "match-timeout must be greater than zero"
        )

    if not RESOURCE_MONITOR.exists():
        raise FileNotFoundError(
            "Resource monitor was not found: "
            f"{RESOURCE_MONITOR}"
        )

    if any(
        level in {"C1", "C2"}
        for level in arguments.levels
    ):
        if not arguments.cyclonedds_home.exists():
            raise FileNotFoundError(
                "Security-enabled Cyclone DDS "
                "installation was not found: "
                f"{arguments.cyclonedds_home}"
            )

    print("DDS experiment configuration")
    print(
        "Levels:",
        ", ".join(arguments.levels),
    )
    print("Network profile: NET-ideal")
    print(
        f"Duration: "
        f"{arguments.duration} seconds"
    )
    print(
        f"Rate: {arguments.rate} "
        "messages/second"
    )
    print(f"Repeats: {arguments.repeats}")
    print(f"Domain: {arguments.domain}")

    for level in arguments.levels:
        for repeat in range(
            1,
            arguments.repeats + 1,
        ):
            run_one(
                level=level,
                repeat=repeat,
                duration=arguments.duration,
                rate=arguments.rate,
                domain=arguments.domain,
                warmup=arguments.warmup,
                cooldown=arguments.cooldown,
                match_timeout=arguments.match_timeout,
                cyclonedds_home=(
                    arguments.cyclonedds_home
                ),
            )

            time.sleep(1)

    print()
    print(
        "All requested DDS ideal-network "
        "experiments completed"
    )
    print(
        "KPI results:",
        RESULTS_DIR
        / "dds_kpi_stream.csv",
    )
    print(
        "Run data:",
        RESULTS_DIR / "runs",
    )
    print(
        "Resource results:",
        RESOURCE_DIR,
    )


if __name__ == "__main__":
    main()
