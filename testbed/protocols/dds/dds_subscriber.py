import argparse
import os
import json
import time

from cyclonedds.domain import DomainParticipant
from cyclonedds.qos import Policy, Qos
from cyclonedds.sub import DataReader
from cyclonedds.topic import Topic
from jsonschema import FormatChecker, ValidationError, validate

from dds_types import VehicleState


TOPIC_NAME = "OCCVehicleState"


def load_schema():
    from pathlib import Path

    schema_path = (
        Path(__file__).resolve().parents[2]
        / "schemas"
        / "vehicle_reading.schema.json"
    )

    with schema_path.open(encoding="utf-8") as schema_file:
        return json.load(schema_file)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Receive VDA 5050-style telemetry over DDS"
    )
    parser.add_argument("--duration", type=float, default=10.0)
    parser.add_argument("--domain", type=int, default=0)
    arguments = parser.parse_args()

    if arguments.duration <= 0:
        raise ValueError("duration must be greater than zero")

    schema = load_schema()
    participant = DomainParticipant(arguments.domain)

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

    deadline = time.monotonic() + arguments.duration
    received = 0
    invalid = 0
    latencies = []

    print("DDS subscriber started")
    print(f"Domain: {arguments.domain}")
    print(f"Topic: {TOPIC_NAME}")
    print(f"Security profile: {os.getenv('DDS_SECURITY_LEVEL', 'C0').upper()}")

    try:
        while time.monotonic() < deadline:
            samples = reader.take()

            if not samples:
                time.sleep(0.01)
                continue

            for sample in samples:
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

                try:
                    payload = json.loads(sample.payload_json)

                    validate(
                        instance=payload,
                        schema=schema,
                        format_checker=FormatChecker(),
                    )

                    if payload["headerId"] != sample.header_id:
                        raise ValueError(
                            "DDS header_id does not match payload"
                        )

                    if (
                        payload["serialNumber"]
                        != sample.serial_number
                    ):
                        raise ValueError(
                            "DDS serial number does not match payload"
                        )

                except (
                    json.JSONDecodeError,
                    ValidationError,
                    ValueError,
                ) as error:
                    invalid += 1
                    print(f"BLOCK | Invalid sample | {error}")
                    continue

                received_ns = time.time_ns()
                latency_ms = (
                    received_ns - sample.t_send_ns
                ) / 1_000_000

                latencies.append(latency_ms)
                received += 1

                print(
                    f"RECEIVE | headerId={sample.header_id} "
                    f"| vehicle={sample.serial_number} "
                    f"| latency={latency_ms:.3f} ms"
                )

    except KeyboardInterrupt:
        print("DDS subscriber interrupted")

    print()
    print("DDS subscriber summary")
    print(f"Received samples: {received}")
    print(f"Invalid samples: {invalid}")

    if latencies:
        print(
            "Mean latency: "
            f"{sum(latencies) / len(latencies):.3f} ms"
        )

    if received == 0:
        raise RuntimeError("No DDS samples received")

    if invalid:
        raise RuntimeError(
            f"{invalid} invalid DDS samples received"
        )


if __name__ == "__main__":
    main()
