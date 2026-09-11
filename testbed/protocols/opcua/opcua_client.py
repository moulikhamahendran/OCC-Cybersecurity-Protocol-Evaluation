import asyncio
import os
import socket
from pathlib import Path

from asyncua import Client, ua
from asyncua.crypto.security_policies import (
    SecurityPolicyBasic256Sha256,
)


TESTBED_DIR = Path(__file__).resolve().parents[2]
CERT_DIR = TESTBED_DIR / "config" / "opcua" / "certs"

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

PORTS = {
    "C0": 4840,
    "C1": 4841,
    "C2": 4842,
}

CLIENT_URI = "urn:ovgu:occ-testbed:opcua:client"
NAMESPACE_URI = "urn:ovgu:occ-testbed:vehicle"


async def configure_client(
    client,
):
    client.application_uri = (
        CLIENT_URI
    )

    if SECURITY_LEVEL == "C0":
        return

    if PASSWORD is None:
        raise RuntimeError(
            "OPCUA_PASSWORD must be set "
            f"for {SECURITY_LEVEL}"
        )

    for path in [
        SERVER_CERT,
        CLIENT_CERT,
        CLIENT_KEY,
    ]:
        if not path.exists():
            raise RuntimeError(
                f"Missing OPC UA certificate: "
                f"{path}"
            )

    if SECURITY_LEVEL == "C1":
        mode = (
            ua.MessageSecurityMode.Sign
        )

    elif SECURITY_LEVEL == "C2":
        mode = (
            ua.MessageSecurityMode
            .SignAndEncrypt
        )

    else:
        raise ValueError(
            f"Unknown security level: "
            f"{SECURITY_LEVEL}"
        )

    await client.set_security(
        SecurityPolicyBasic256Sha256,
        certificate=str(
            CLIENT_CERT
        ),
        private_key=str(
            CLIENT_KEY
        ),
        server_certificate=str(
            SERVER_CERT
        ),
        mode=mode,
    )

    client.set_user(
        USERNAME
    )

    client.set_password(
        PASSWORD
    )


async def main():
    if SECURITY_LEVEL not in PORTS:
        raise ValueError(
            "OPCUA_SECURITY_LEVEL must be "
            "C0, C1 or C2"
        )

    port = PORTS[
        SECURITY_LEVEL
    ]

    url = (
        f"opc.tcp://127.0.0.1:"
        f"{port}/occ/"
    )

    print(
        f"Connecting OPC UA client "
        f"to {url}"
    )

    print(
        f"Security level: "
        f"{SECURITY_LEVEL}"
    )

    client = Client(
        url=url
    )

    await configure_client(
        client
    )

    async with client:

        namespace_index = (
            await client
            .get_namespace_index(
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

        heartbeat = (
            await vehicle.get_child(
                [
                    f"{namespace_index}:Heartbeat"
                ]
            )
        )

        serial_number = (
            await vehicle.get_child(
                [
                    f"{namespace_index}:SerialNumber"
                ]
            )
        )

        heartbeat_value = (
            await heartbeat.read_value()
        )

        serial_value = (
            await serial_number.read_value()
        )

        print(
            "Connected successfully"
        )
        print(
            f"Vehicle: {serial_value}"
        )
        print(
            f"Heartbeat: "
            f"{heartbeat_value}"
        )


if __name__ == "__main__":
    asyncio.run(main())
