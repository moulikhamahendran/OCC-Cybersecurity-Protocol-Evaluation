import asyncio
import json
import os
import sys
import time
from pathlib import Path

from asyncua import Server, ua
from asyncua.crypto.permission_rules import User, UserRole


TESTBED_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(TESTBED_DIR))

from vehicles.data_generator import make_reading


CERT_DIR = TESTBED_DIR / "config" / "opcua" / "certs"
SERVER_CERT = CERT_DIR / "server_cert.der"
SERVER_KEY = CERT_DIR / "server_key.pem"

SECURITY_LEVEL = os.getenv(
    "OPCUA_SECURITY_LEVEL",
    "C0",
).upper()

USERNAME = os.getenv(
    "OPCUA_USERNAME",
    "occuser",
)

PASSWORD = os.getenv("OPCUA_PASSWORD")

PORTS = {
    "C0": 4840,
    "C1": 4841,
    "C2": 4842,
}

SERVER_URI = "urn:ovgu:occ-testbed:opcua"
NAMESPACE_URI = "urn:ovgu:occ-testbed:vehicle"

PUBLISH_INTERVAL_SECONDS = 0.1


class OCCUserManager:
    def get_user(
        self,
        iserver,
        username=None,
        password=None,
        certificate=None,
    ):
        if SECURITY_LEVEL == "C0":
            return User(
                role=UserRole.User,
            )

        if (
            username == USERNAME
            and password == PASSWORD
        ):
            return User(
                role=UserRole.User,
                name=username,
            )

        return None


async def configure_security(server):
    if SECURITY_LEVEL == "C0":
        server.set_security_policy(
            [
                ua.SecurityPolicyType.NoSecurity,
            ]
        )

        server.set_identity_tokens(
            [
                ua.AnonymousIdentityToken,
            ]
        )

        return

    if PASSWORD is None:
        raise RuntimeError(
            f"OPCUA_PASSWORD must be set for "
            f"{SECURITY_LEVEL}"
        )

    await server.load_certificate(
        SERVER_CERT
    )

    await server.load_private_key(
        SERVER_KEY
    )

    server.set_identity_tokens(
        [
            ua.UserNameIdentityToken,
        ]
    )

    if SECURITY_LEVEL == "C1":
        server.set_security_policy(
            [
                ua.SecurityPolicyType
                .Basic256Sha256_Sign,
            ]
        )

    elif SECURITY_LEVEL == "C2":
        server.set_security_policy(
            [
                ua.SecurityPolicyType
                .Basic256Sha256_SignAndEncrypt,
            ]
        )

    else:
        raise ValueError(
            f"Unknown security level: "
            f"{SECURITY_LEVEL}"
        )


async def main():
    if SECURITY_LEVEL not in PORTS:
        raise ValueError(
            f"Unknown security level: "
            f"{SECURITY_LEVEL}"
        )

    port = PORTS[SECURITY_LEVEL]

    server = Server(
        user_manager=OCCUserManager()
    )

    await server.init()

    await server.set_application_uri(
        SERVER_URI
    )

    server.set_server_name(
        "OvGU OCC Cybersecurity OPC UA Testbed"
    )

    server.set_endpoint(
        f"opc.tcp://0.0.0.0:{port}/occ/"
    )

    await configure_security(server)

    namespace_index = (
        await server.register_namespace(
            NAMESPACE_URI
        )
    )

    vehicle = (
        await server.nodes.objects.add_object(
            namespace_index,
            "Vehicle",
        )
    )

    reading = (
        await vehicle.add_variable(
            namespace_index,
            "Reading",
            "{}",
        )
    )

    heartbeat = (
        await vehicle.add_variable(
            namespace_index,
            "Heartbeat",
            0,
        )
    )

    print("Starting OPC UA server")
    print(
        f"Security level: {SECURITY_LEVEL}"
    )
    print(
        f"Endpoint: "
        f"opc.tcp://127.0.0.1:{port}/occ/"
    )
    print(
        "Payload semantics: "
        "VDA 5050 v2.1.0 aligned"
    )
    print(
        "Stream rate: 10 messages/second"
    )

    sequence = 0
    heartbeat_counter = 0
    last_heartbeat = time.monotonic()

    async with server:
        while True:
            sequence += 1

            payload = make_reading(
                sequence=sequence,
                serial_number="VM-001",
            )

            await reading.write_value(
                json.dumps(
                    payload,
                    separators=(",", ":"),
                )
            )

            now = time.monotonic()

            if (
                now - last_heartbeat
                >= 1.0
            ):
                heartbeat_counter += 1

                await heartbeat.write_value(
                    heartbeat_counter
                )

                last_heartbeat = now

            await asyncio.sleep(
                PUBLISH_INTERVAL_SECONDS
            )


if __name__ == "__main__":
    asyncio.run(main())