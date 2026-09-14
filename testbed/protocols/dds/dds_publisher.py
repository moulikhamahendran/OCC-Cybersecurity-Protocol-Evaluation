import argparse
import json
import sys
import time
from pathlib import Path

from cyclonedds.domain import DomainParticipant
from cyclonedds.pub import DataWriter
from cyclonedds.qos import Policy, Qos
from cyclonedds.topic import Topic


TESTBED_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(TESTBED_DIR))

from vehicles.data_generator import make_reading

from dds_types import VehicleState


TOPIC_NAME = "OCCVehicleState"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Publish VDA 5050-style telemetry over DDS"
    )
    parser.add_argument("--duration", type=float, default=10.0)
    parser.add_argument("--rate", type=float, default=10.0)
    parser.add_argument("--domain", type=int, default=0)
    parser.add_argument(
        "--serial-number",
        default="VM-001",
    )
    arguments = parser.parse_args()

    if arguments.duration <= 0:
        raise ValueError("duration must be greater than zero")

    if arguments.rate <= 0:
        raise ValueError("rate must be greater than zero")

    participant = DomainParticipant(arguments.domain)

    topic = Topic(
        participant,
        TOPIC_NAME,
        VehicleState,
    )

    writer = DataWriter(
        participant,
        topic,
        qos=Qos(
            Policy.Reliability.Reliable(
                max_blocking_time=1_000_000_000
            ),
            Policy.History.KeepLast(10),
        ),
    )

    interval = 1.0 / arguments.rate
    deadline = time.monotonic() + arguments.duration
    sequence = 0

    print("DDS publisher started")
    print(f"Domain: {arguments.domain}")
    print(f"Topic: {TOPIC_NAME}")
    print(f"Rate: {arguments.rate:.1f} messages/second")
    print("Security profile: C0")

    try:
        while time.monotonic() < deadline:
            payload = make_reading(
                sequence,
                serial_number=arguments.serial_number,
            )

            sample = VehicleState(
                header_id=payload["headerId"],
                timestamp=payload["timestamp"],
                version=payload["version"],
                manufacturer=payload["manufacturer"],
                serial_number=payload["serialNumber"],
                payload_json=json.dumps(
                    payload,
                    separators=(",", ":"),
                ),
                t_send_ns=payload["t_send_ns"],
            )

            writer.write(sample)

            print(
                f"PUBLISH | headerId={sample.header_id} "
                f"| vehicle={sample.serial_number}"
            )

            sequence += 1
            time.sleep(interval)

    except KeyboardInterrupt:
        print("DDS publisher interrupted")

    print(f"DDS publisher stopped after {sequence} samples")


if __name__ == "__main__":
    main()
