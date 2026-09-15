import argparse
import csv
import json
import os
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from cyclonedds.domain import DomainParticipant
from cyclonedds.qos import Policy, Qos
from cyclonedds.sub import DataReader
from cyclonedds.topic import Topic
from jsonschema import FormatChecker, ValidationError, validate

from dds_types import VehicleState


TESTBED_DIR = Path(__file__).resolve().parents[2]
RESULTS_DIR = TESTBED_DIR / "results" / "dds"
TOPIC_NAME = "OCCVehicleState"

SECURITY_LEVEL = os.getenv(
    "DDS_SECURITY_LEVEL",
    "C0",
).upper()

NET_PROFILE = os.getenv(
    "NET_PROFILE",
    "NET-ideal",
)

REPEAT_INDEX = int(
    os.getenv(
        "REPEAT_INDEX",
        "1",
    )
)


def load_schema() -> dict:
    schema_path = (
        TESTBED_DIR
        / "schemas"
        / "vehicle_reading.schema.json"
    )

    with schema_path.open(
        encoding="utf-8",
    ) as schema_file:
        return json.load(schema_file)


def make_run_id() -> str:
    supplied_run_id = os.getenv("RUN_ID")

    if supplied_run_id:
        return supplied_run_id

    timestamp = datetime.now(
        timezone.utc
    ).strftime("%Y%m%dT%H%M%SZ")

    return (
        f"dds_{SECURITY_LEVEL.lower()}_"
        f"{NET_PROFILE.lower()}_"
        f"repeat_{REPEAT_INDEX}_"
        f"{timestamp}_{uuid4().hex[:8]}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Receive and measure VDA 5050-style "
            "telemetry over DDS"
        )
    )

    parser.add_argument(
        "--duration",
        type=float,
        default=10.0,
    )

    parser.add_argument(
        "--domain",
        type=int,
        default=0,
    )

    parser.add_argument(
        "--measurement-duration",
        type=float,
        default=None,
        help=(
            "Publisher workload duration used "
            "for throughput calculation"
        ),
    )

    parser.add_argument(
        "--expected-messages",
        type=int,
        default=None,
        help=(
            "Exact number of messages the "
            "publisher is configured to send"
        ),
    )

    arguments = parser.parse_args()

    if arguments.duration <= 0:
        raise ValueError(
            "duration must be greater than zero"
        )

    measurement_duration = (
        arguments.measurement_duration
        if arguments.measurement_duration
        is not None
        else arguments.duration
    )

    if measurement_duration <= 0:
        raise ValueError(
            "measurement-duration must be "
            "greater than zero"
        )

    if (
        arguments.expected_messages
        is not None
        and arguments.expected_messages < 1
    ):
        raise ValueError(
            "expected-messages must be "
            "at least one"
        )

    if SECURITY_LEVEL not in {
        "C0",
        "C1",
        "C2",
    }:
        raise ValueError(
            f"Unknown DDS security level: "
            f"{SECURITY_LEVEL}"
        )

    run_id = make_run_id()
    schema = load_schema()

    participant = DomainParticipant(
        arguments.domain
    )

    topic = Topic(
        participant,
        TOPIC_NAME,
        VehicleState,
    )

    reader = DataReader(
        participant,
        topic,
        qos=Qos(
            Policy.Reliability.Reliable(
                max_blocking_time=1_000_000_000
            ),
            Policy.History.KeepLast(10),
        ),
    )

    deadline = (
        time.monotonic()
        + arguments.duration
    )

    received = 0
    invalid = 0
    duplicate_count = 0
    previous_latency = None
    seen_header_ids = set()
    samples = []

    print("DDS subscriber started")
    print(f"Run ID: {run_id}")
    print(f"Domain: {arguments.domain}")
    print(f"Topic: {TOPIC_NAME}")
    print(
        f"Security profile: "
        f"{SECURITY_LEVEL}"
    )
    print(
        f"Network profile: "
        f"{NET_PROFILE}"
    )

    started = time.monotonic()

    try:
        while (
            time.monotonic() < deadline
            and (
                arguments.expected_messages
                is None
                or received
                < arguments.expected_messages
            )
        ):
            received_samples = reader.take()

            if not received_samples:
                time.sleep(0.01)
                continue

            for sample in received_samples:
                sample_info = getattr(
                    sample,
                    "sample_info",
                    None,
                )

                if (
                    sample_info is not None
                    and not sample_info.valid_data
                ):
                    continue

                received_ns = time.time_ns()

                try:
                    payload = json.loads(
                        sample.payload_json
                    )

                    validate(
                        instance=payload,
                        schema=schema,
                        format_checker=FormatChecker(),
                    )

                    if (
                        payload["headerId"]
                        != sample.header_id
                    ):
                        raise ValueError(
                            "DDS header_id does not "
                            "match payload"
                        )

                    if (
                        payload["serialNumber"]
                        != sample.serial_number
                    ):
                        raise ValueError(
                            "DDS serial number does "
                            "not match payload"
                        )

                    if (
                        int(payload["t_send_ns"])
                        != sample.t_send_ns
                    ):
                        raise ValueError(
                            "DDS send timestamp does "
                            "not match payload"
                        )

                except (
                    json.JSONDecodeError,
                    ValidationError,
                    ValueError,
                    KeyError,
                    TypeError,
                ) as error:
                    invalid += 1
                    print(
                        "BLOCK | Invalid sample "
                        f"| {error}"
                    )
                    continue

                header_id = int(
                    sample.header_id
                )

                if header_id in seen_header_ids:
                    duplicate_count += 1
                    print(
                        "BLOCK | Duplicate sample "
                        f"| headerId={header_id}"
                    )
                    continue

                seen_header_ids.add(header_id)

                latency_ms = (
                    received_ns
                    - sample.t_send_ns
                ) / 1_000_000

                if previous_latency is None:
                    jitter_ms = 0.0
                else:
                    jitter_ms = abs(
                        latency_ms
                        - previous_latency
                    )

                previous_latency = latency_ms

                payload_bytes = len(
                    sample.payload_json.encode(
                        "utf-8"
                    )
                )

                samples.append(
                    {
                        "timestamp":
                            datetime.now(
                                timezone.utc
                            ).isoformat(),
                        "header_id":
                            header_id,
                        "serial_number":
                            sample.serial_number,
                        "send_ns":
                            sample.t_send_ns,
                        "received_ns":
                            received_ns,
                        "latency_ms":
                            round(
                                latency_ms,
                                6,
                            ),
                        "jitter_ms":
                            round(
                                jitter_ms,
                                6,
                            ),
                        "payload_bytes":
                            payload_bytes,
                        "verdict":
                            "PASS",
                    }
                )

                received += 1

                print(
                    "RECEIVE "
                    f"| headerId={header_id} "
                    f"| vehicle="
                    f"{sample.serial_number} "
                    f"| latency="
                    f"{latency_ms:.3f} ms"
                )

    except KeyboardInterrupt:
        print(
            "DDS subscriber interrupted"
        )

    elapsed = time.monotonic() - started

    if received == 0:
        raise RuntimeError(
            "No DDS samples received"
        )

    ordered_ids = sorted(
        seen_header_ids
    )

    observed_sequence_span = (
        ordered_ids[-1]
        - ordered_ids[0]
        + 1
    )

    expected_messages = (
        arguments.expected_messages
        if arguments.expected_messages
        is not None
        else observed_sequence_span
    )

    lost_messages = max(
        0,
        expected_messages - received,
    )

    loss_percent = (
        lost_messages
        / expected_messages
        * 100
        if expected_messages
        else 0.0
    )

    latencies = [
        sample["latency_ms"]
        for sample in samples
    ]

    jitters = [
        sample["jitter_ms"]
        for sample in samples
    ]

    total_bytes = sum(
        sample["payload_bytes"]
        for sample in samples
    )

    throughput_messages = (
        received / measurement_duration
    )

    throughput_kbps = (
        total_bytes
        * 8
        / 1000
        / measurement_duration
    )

    run_dir = (
        RESULTS_DIR
        / "runs"
        / run_id
    )

    run_dir.mkdir(
        parents=True,
        exist_ok=False,
    )

    samples_path = (
        run_dir / "samples.csv"
    )

    with samples_path.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as samples_file:
        writer = csv.DictWriter(
            samples_file,
            fieldnames=samples[0].keys(),
        )

        writer.writeheader()
        writer.writerows(samples)

    summary_path = (
        RESULTS_DIR
        / "dds_kpi_stream.csv"
    )

    summary_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    needs_header = (
        not summary_path.exists()
        or summary_path.stat().st_size == 0
    )

    summary = {
        "timestamp":
            datetime.now(
                timezone.utc
            ).isoformat(),
        "run_id":
            run_id,
        "protocol":
            "DDS",
        "security_level":
            SECURITY_LEVEL,
        "net_profile":
            NET_PROFILE,
        "repeat_index":
            REPEAT_INDEX,
        "domain_id":
            arguments.domain,
        "duration_seconds":
            measurement_duration,
        "subscriber_elapsed_seconds":
            round(
                elapsed,
                3,
            ),
        "expected_messages":
            expected_messages,
        "received_messages":
            received,
        "invalid_messages":
            invalid,
        "duplicate_messages":
            duplicate_count,
        "lost_messages":
            lost_messages,
        "loss_percent":
            round(
                loss_percent,
                3,
            ),
        "latency_ms":
            round(
                statistics.mean(
                    latencies
                ),
                3,
            ),
        "jitter_ms":
            round(
                statistics.mean(
                    jitters
                ),
                3,
            ),
        "max_latency_ms":
            round(
                max(latencies),
                3,
            ),
        "throughput_messages_per_second":
            round(
                throughput_messages,
                3,
            ),
        "throughput_kbps":
            round(
                throughput_kbps,
                3,
            ),
        "verdict":
            (
                "PASS"
                if invalid == 0
                else "BLOCK"
            ),
    }

    with summary_path.open(
        "a",
        newline="",
        encoding="utf-8",
    ) as summary_file:
        writer = csv.DictWriter(
            summary_file,
            fieldnames=summary.keys(),
        )

        if needs_header:
            writer.writeheader()

        writer.writerow(summary)

    print()
    print("DDS subscriber summary")
    print(
        f"Received samples: {received}"
    )
    print(
        f"Invalid samples: {invalid}"
    )
    print(
        "Duplicate samples: "
        f"{duplicate_count}"
    )
    print(
        f"Lost samples: {lost_messages}"
    )
    print(
        "Loss percent: "
        f"{loss_percent:.3f}%"
    )
    print(
        "Mean latency: "
        f"{summary['latency_ms']:.3f} ms"
    )
    print(
        "Mean jitter: "
        f"{summary['jitter_ms']:.3f} ms"
    )
    print(
        "Throughput: "
        f"{summary['throughput_messages_per_second']:.3f} "
        "messages/second"
    )
    print(
        f"Samples: {samples_path}"
    )
    print(
        f"KPI summary: {summary_path}"
    )

    if invalid:
        raise RuntimeError(
            f"{invalid} invalid DDS "
            "samples received"
        )


if __name__ == "__main__":
    main()
