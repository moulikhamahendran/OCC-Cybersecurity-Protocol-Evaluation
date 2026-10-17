import argparse
import asyncio
import csv
import json
import os
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from asyncua import Client, ua
from asyncua.crypto.security_policies import (
    SecurityPolicyBasic256Sha256,
)


TESTBED_DIR = Path(__file__).resolve().parents[2]
CERT_DIR = TESTBED_DIR / "config" / "opcua" / "certs"
RESULTS_DIR = Path(
    os.getenv(
        "OPCUA_RESULTS_DIR",
        str(TESTBED_DIR / "results" / "opcua"),
    )
)

SERVER_CERT = CERT_DIR / "server_cert.der"
CLIENT_CERT = CERT_DIR / "client_cert.der"
CLIENT_KEY = CERT_DIR / "client_key.pem"

SECURITY_LEVEL = os.getenv(
    "OPCUA_SECURITY_LEVEL",
    "C0",
).upper()

USERNAME = os.getenv(
    "OPCUA_USERNAME",
    "occuser",
)

PASSWORD = os.getenv(
    "OPCUA_PASSWORD",
)

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

PORTS = {
    "C0": 4840,
    "C1": 4841,
    "C2": 4842,
}

CLIENT_URI = "urn:ovgu:occ-testbed:opcua:client"
NAMESPACE_URI = "urn:ovgu:occ-testbed:vehicle"


async def configure_client(client):
    client.application_uri = CLIENT_URI

    if SECURITY_LEVEL == "C0":
        return

    if PASSWORD is None:
        raise RuntimeError(
            f"OPCUA_PASSWORD must be set for {SECURITY_LEVEL}"
        )

    mode = (
        ua.MessageSecurityMode.Sign
        if SECURITY_LEVEL == "C1"
        else ua.MessageSecurityMode.SignAndEncrypt
    )

    await client.set_security(
        SecurityPolicyBasic256Sha256,
        certificate=str(CLIENT_CERT),
        private_key=str(CLIENT_KEY),
        server_certificate=str(SERVER_CERT),
        mode=mode,
    )

    client.set_user(USERNAME)
    client.set_password(PASSWORD)


class ReadingHandler:
    def __init__(self):
        self.samples = []
        self.previous_latency = None

    def datachange_notification(
        self,
        node,
        value,
        data,
    ):
        received_ns = time.time_ns()

        try:
            payload = json.loads(value)

            latency_ms = (
                received_ns
                - int(payload["t_send_ns"])
            ) / 1_000_000

            if self.previous_latency is None:
                jitter_ms = 0.0
            else:
                jitter_ms = abs(
                    latency_ms
                    - self.previous_latency
                )

            self.previous_latency = latency_ms

            self.samples.append(
                {
                    "timestamp":
                        datetime.now(
                            timezone.utc
                        ).isoformat(),
                    "header_id":
                        int(payload["headerId"]),
                    "latency_ms":
                        latency_ms,
                    "jitter_ms":
                        jitter_ms,
                    "payload_bytes":
                        len(
                            value.encode(
                                "utf-8"
                            )
                        ),
                }
            )

        except Exception as error:
            print(
                "Sample processing error:",
                error,
            )


async def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--duration",
        type=float,
        default=5.0,
    )

    args = parser.parse_args()

    port = PORTS[SECURITY_LEVEL]

    endpoint = os.getenv(
        "OPCUA_ENDPOINT",
        f"opc.tcp://127.0.0.1:{port}/occ/",
    )

    run_id = os.getenv("RUN_ID")

    if not run_id:
        run_id = (
            f"opcua_{SECURITY_LEVEL.lower()}_"
            f"{NET_PROFILE.lower()}_"
            f"repeat_{REPEAT_INDEX}_"
            f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_"
            f"{uuid4().hex[:8]}"
        )

    print("OPC UA benchmark")
    print("Run ID:", run_id)
    print("Security level:", SECURITY_LEVEL)
    print("Network profile:", NET_PROFILE)
    print("Endpoint:", endpoint)
    print("Duration:", args.duration)

    client = Client(url=endpoint)

    await configure_client(client)

    handler = ReadingHandler()

    started = time.monotonic()

    async with client:
        namespace_index = (
            await client.get_namespace_index(
                NAMESPACE_URI
            )
        )

        vehicle = (
            await client.nodes.objects
            .get_child(
                [
                    f"{namespace_index}:Vehicle"
                ]
            )
        )

        reading = (
            await vehicle.get_child(
                [
                    f"{namespace_index}:Reading"
                ]
            )
        )

        subscription = (
            await client.create_subscription(
                50,
                handler,
            )
        )

        handle = (
            await subscription
            .subscribe_data_change(
                reading
            )
        )

        await asyncio.sleep(
            args.duration
        )

        await subscription.unsubscribe(
            handle
        )

        await subscription.delete()

    elapsed = time.monotonic() - started

    samples = handler.samples

    if not samples:
        raise RuntimeError(
            "No OPC UA samples received"
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
        len(samples) / args.duration
    )

    throughput_kbps = (
        total_bytes
        * 8
        / 1000
        / args.duration
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
        run_dir
        / "samples.csv"
    )

    with samples_path.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "timestamp",
                "header_id",
                "latency_ms",
                "jitter_ms",
                "payload_bytes",
            ],
        )

        writer.writeheader()
        writer.writerows(samples)

    summary_path = (
        RESULTS_DIR
        / "opcua_kpi_stream.csv"
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
            "OPC UA",

        "security_level":
            SECURITY_LEVEL,

        "net_profile":
            NET_PROFILE,

        "repeat_index":
            REPEAT_INDEX,

        "duration_seconds":
            args.duration,

        "received_messages":
            len(samples),

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

        "max_latency_ms":
            round(
                max(latencies),
                3,
            ),
    }

    with summary_path.open(
        "a",
        newline="",
        encoding="utf-8",
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=summary.keys(),
        )

        if needs_header:
            writer.writeheader()

        writer.writerow(summary)

    print()
    print("RESULT")
    print(
        "received_messages =",
        len(samples),
    )
    print(
        "latency_ms =",
        summary["latency_ms"],
    )
    print(
        "jitter_ms =",
        summary["jitter_ms"],
    )
    print(
        "throughput_messages_per_second =",
        summary[
            "throughput_messages_per_second"
        ],
    )
    print(
        "throughput_kbps =",
        summary["throughput_kbps"],
    )
    print(
        "max_latency_ms =",
        summary["max_latency_ms"],
    )
    print(
        "samples =",
        samples_path,
    )


if __name__ == "__main__":
    asyncio.run(main())
