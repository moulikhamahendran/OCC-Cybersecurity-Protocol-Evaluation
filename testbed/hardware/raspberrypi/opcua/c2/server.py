import asyncio
import logging
import os

from asyncua.crypto.permission_rules import User, UserRole

from asyncua import Server, ua

ENDPOINT = "opc.tcp://0.0.0.0:4842/occ/"
NAMESPACE = "urn:ovgu:occ:vehicle1"



class OCCUserManager:
    def get_user(
        self,
        iserver,
        username=None,
        password=None,
        certificate=None
    ):
        expected_user = os.getenv("OPCUA_USERNAME", "occuser")
        expected_password = os.getenv("OPCUA_PASSWORD")

        if (
            expected_password
            and username == expected_user
            and password == expected_password
        ):
            return User(role=UserRole.User)

        return None


async def main():
    logging.basicConfig(level=logging.INFO)

    server = Server(user_manager=OCCUserManager())
    await server.init()

    # C1 requires username/password; anonymous access disabled
    server.set_identity_tokens([
        ua.UserNameIdentityToken
    ])

    server.set_endpoint(ENDPOINT)
    server.set_server_name("OvGU OCC OPC UA C2")

    # C2 = Basic256Sha256 + SignAndEncrypt
    await server.set_application_uri("urn:ovgu:occ:opcua:c1:server")
    await server.load_certificate("certs/c1/server_cert.pem")
    await server.load_private_key("certs/c1/server_key.pem")

    server.set_security_policy([
        ua.SecurityPolicyType.Basic256Sha256_SignAndEncrypt
    ])

    idx = await server.register_namespace(NAMESPACE)

    vehicle = await server.nodes.objects.add_object(
        ua.NodeId("Vehicle1", idx),
        "Vehicle1"
    )

    vehicle_id = await vehicle.add_variable(
        ua.NodeId("Vehicle1.VehicleId", idx),
        "VehicleId",
        "VEHICLE_1"
    )

    sequence = await vehicle.add_variable(
        ua.NodeId("Vehicle1.Sequence", idx),
        "Sequence",
        ua.Variant(0, ua.VariantType.UInt32)
    )

    speed = await vehicle.add_variable(
        ua.NodeId("Vehicle1.Speed", idx),
        "Speed",
        ua.Variant(0.0, ua.VariantType.Double)
    )

    battery = await vehicle.add_variable(
        ua.NodeId("Vehicle1.Battery", idx),
        "Battery",
        ua.Variant(100.0, ua.VariantType.Double)
    )

    timestamp_ms = await vehicle.add_variable(
        ua.NodeId("Vehicle1.TimestampMs", idx),
        "TimestampMs",
        ua.Variant(0, ua.VariantType.UInt64)
    )

    # ESP32 client will update these values
    await sequence.set_writable()
    await speed.set_writable()
    await battery.set_writable()
    await timestamp_ms.set_writable()

    print()
    print("==========================================")
    print("OCC OPC UA C2 SERVER")
    print("==========================================")
    print("Endpoint:")
    print("opc.tcp://192.168.1.115:4842/occ/")
    print()
    print("SecurityPolicy: Basic256Sha256")
    print("SecurityMode: SignAndEncrypt")
    print("Vehicle: VEHICLE_1")
    print()
    print("Stable Node IDs:")
    print(f"ns={idx};s=Vehicle1.VehicleId")
    print(f"ns={idx};s=Vehicle1.Sequence")
    print(f"ns={idx};s=Vehicle1.Speed")
    print(f"ns={idx};s=Vehicle1.Battery")
    print(f"ns={idx};s=Vehicle1.TimestampMs")
    print("==========================================")
    print()

    async with server:
        while True:
            await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main())
