import argparse
import asyncio
import csv
import os
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

SERVER_CERT = CERT_DIR / "server_cert.der"
CLIENT_CERT = CERT_DIR / "client_cert.der"
CLIENT_KEY = CERT_DIR / "client_key.pem"

CLIENT_URI = "urn:ovgu:occ-testbed:opcua:client"
NAMESPACE_URI = "urn:ovgu:occ-testbed:vehicle"

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


async def configure_correct_security(
    client,
    include_credentials=True,
):
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

    if include_credentials:
        client.set_user(USERNAME)
        client.set_password(PASSWORD)


async def configure_attack(client, attack):
    client.application_uri = CLIENT_URI

    if attack == "anonymous_access":
        await configure_correct_security(
            client,
            include_credentials=False,
        )
        return

    if attack == "invalid_credentials":
        if SECURITY_LEVEL == "C0":
            raise RuntimeError(
                "invalid_credentials is not applicable to C0"
            )

        await configure_correct_security(
            client,
            include_credentials=False,
        )

        client.set_user("invalid-user")
        client.set_password("invalid-password")
        return

    if attack == "wrong_security":
        if SECURITY_LEVEL == "C0":
            await client.set_security(
                SecurityPolicyBasic256Sha256,
                certificate=str(CLIENT_CERT),
                private_key=str(CLIENT_KEY),
                server_certificate=str(SERVER_CERT),
                mode=ua.MessageSecurityMode.Sign,
            )
            return

        client.set_user(USERNAME)

        if PASSWORD is not None:
            client.set_password(PASSWORD)

        return

    if attack == "unauthorized_write":
        await configure_correct_security(
            client,
            include_credentials=True,
        )
        return

    raise ValueError(
        f"Unknown attack: {attack}"
    )


def expected_outcome(attack):
    if attack == "anonymous_access":
        if SECURITY_LEVEL == "C0":
            return "ALLOWED"
        return "REJECTED"

    if attack in (
        "invalid_credentials",
        "wrong_security",
        "unauthorized_write",
    ):
        return "REJECTED"

    raise ValueError(
        f"Unknown attack: {attack}"
    )


async def test_connection_attack(client):
    try:
        await client.connect()
    except Exception as error:
        return (
            "REJECTED",
            type(error).__name__,
            str(error),
        )

    try:
        return (
            "ALLOWED",
            "",
            "Connection/session established",
        )
    finally:
        await client.disconnect()


async def test_unauthorized_write(client):
    try:
        await client.connect()
    except Exception as error:
        return (
            "CONNECTION_FAILED",
            type(error).__name__,
            str(error),
        )

    try:
        namespace_index = await client.get_namespace_index(
            NAMESPACE_URI
        )

        reading = await client.nodes.objects.get_child(
            [
                f"{namespace_index}:Vehicle",
                f"{namespace_index}:Reading",
            ]
        )

        try:
            await reading.write_value(
                '{"attack":"unauthorized-write"}'
            )

            return (
                "ALLOWED",
                "",
                "Client write unexpectedly succeeded",
            )

        except Exception as error:
            return (
                "REJECTED",
                type(error).__name__,
                str(error),
            )

    finally:
        await client.disconnect()


def append_result(path, result):
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    exists = path.exists()

    with path.open(
        "a",
        newline="",
        encoding="utf-8",
    ) as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=result.keys(),
        )

        if not exists:
            writer.writeheader()

        writer.writerow(result)


async def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--attack",
        required=True,
        choices=[
            "anonymous_access",
            "invalid_credentials",
            "wrong_security",
            "unauthorized_write",
        ],
    )

    parser.add_argument(
        "--results-file",
        default=(
            "testbed/results/opcua/"
            "opcua_attack_security_results.csv"
        ),
    )

    args = parser.parse_args()

    endpoint = (
        f"opc.tcp://127.0.0.1:"
        f"{PORTS[SECURITY_LEVEL]}/occ/"
    )

    run_id = (
        f"opcua_attack_"
        f"{SECURITY_LEVEL.lower()}_"
        f"{args.attack}_"
        f"repeat_{REPEAT_INDEX}_"
        f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_"
        f"{uuid4().hex[:8]}"
    )

    client = Client(
        url=endpoint,
        timeout=5,
    )

    await configure_attack(
        client,
        args.attack,
    )

    expected = expected_outcome(
        args.attack
    )

    start = time.perf_counter()

    if args.attack == "unauthorized_write":
        observed, error_type, notes = (
            await test_unauthorized_write(client)
        )
    else:
        observed, error_type, notes = (
            await test_connection_attack(client)
        )

    elapsed = time.perf_counter() - start

    control_passed = (
        observed == expected
    )

    result = {
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
        "attack_type":
            args.attack,
        "repeat_index":
            REPEAT_INDEX,
        "expected_outcome":
            expected,
        "observed_outcome":
            observed,
        "control_passed":
            control_passed,
        "elapsed_seconds":
            round(elapsed, 6),
        "error_type":
            error_type,
        "notes":
            notes.replace(
                "\n",
                " ",
            )[:300],
    }

    append_result(
        Path(args.results_file),
        result,
    )

    print()
    print("OPC UA SECURITY ATTACK TEST")
    print("Run ID          :", run_id)
    print("Security level  :", SECURITY_LEVEL)
    print("Attack          :", args.attack)
    print("Expected        :", expected)
    print("Observed        :", observed)
    print("Control passed  :", control_passed)
    print("Elapsed seconds :", round(elapsed, 3))

    if error_type:
        print("Response/error  :", error_type)

    print()


if __name__ == "__main__":
    asyncio.run(main())
