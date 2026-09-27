import asyncio
import os
from asyncua import Client, ua

URL = "opc.tcp://192.168.1.115:4841/occ/"

async def main():
    client = Client(URL)
    client.application_uri = "urn:ovgu:occ:opcua:c1:client"

    client.set_user(os.getenv("OPCUA_USERNAME", "occuser"))
    client.set_password(os.environ["OPCUA_PASSWORD"])

    await client.set_security_string(
        "Basic256Sha256,Sign,"
        "certs/c1/client/client_cert.pem,"
        "certs/c1/client/client_key.pem,"
        "certs/c1/server_cert.pem"
    )

    async with client:
        print("OPC UA C1 SECURE CONNECTED")

        seq = client.get_node("ns=2;s=Vehicle1.Sequence")
        speed = client.get_node("ns=2;s=Vehicle1.Speed")
        battery = client.get_node("ns=2;s=Vehicle1.Battery")
        timestamp = client.get_node("ns=2;s=Vehicle1.TimestampMs")

        await seq.write_value(
            ua.Variant(1, ua.VariantType.UInt32)
        )

        await speed.write_value(
            ua.Variant(2.5, ua.VariantType.Double)
        )

        await battery.write_value(
            ua.Variant(87.0, ua.VariantType.Double)
        )

        await timestamp.write_value(
            ua.Variant(123456789, ua.VariantType.UInt64)
        )

        print("Sequence    =", await seq.read_value())
        print("Speed       =", await speed.read_value())
        print("Battery     =", await battery.read_value())
        print("TimestampMs =", await timestamp.read_value())

        print("C1 SECURE READ/WRITE PASS")

asyncio.run(main())
