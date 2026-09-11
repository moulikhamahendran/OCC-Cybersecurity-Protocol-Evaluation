import asyncio
import socket
from pathlib import Path

from cryptography.x509.oid import ExtendedKeyUsageOID
from asyncua.crypto.cert_gen import setup_self_signed_certificate


TESTBED_DIR = Path(__file__).resolve().parents[2]
CERT_DIR = TESTBED_DIR / "config" / "opcua" / "certs"

SERVER_KEY = CERT_DIR / "server_key.pem"
SERVER_CERT = CERT_DIR / "server_cert.der"

CLIENT_KEY = CERT_DIR / "client_key.pem"
CLIENT_CERT = CERT_DIR / "client_cert.der"

HOSTNAME = socket.gethostname()

SERVER_URI = "urn:ovgu:occ-testbed:opcua:server"
CLIENT_URI = "urn:ovgu:occ-testbed:opcua:client"

SUBJECT = {
    "countryName": "DE",
    "stateOrProvinceName": "Saxony-Anhalt",
    "localityName": "Magdeburg",
    "organizationName": "OvGU OCC Testbed",
}


async def main():
    CERT_DIR.mkdir(parents=True, exist_ok=True)

    await setup_self_signed_certificate(
        SERVER_KEY,
        SERVER_CERT,
        SERVER_URI,
        HOSTNAME,
        [
            ExtendedKeyUsageOID.SERVER_AUTH,
            ExtendedKeyUsageOID.CLIENT_AUTH,
        ],
        SUBJECT,
    )

    await setup_self_signed_certificate(
        CLIENT_KEY,
        CLIENT_CERT,
        CLIENT_URI,
        HOSTNAME,
        [
            ExtendedKeyUsageOID.CLIENT_AUTH,
        ],
        SUBJECT,
    )

    print("OPC UA certificates ready")
    print("Server certificate:", SERVER_CERT)
    print("Client certificate:", CLIENT_CERT)


if __name__ == "__main__":
    asyncio.run(main())
