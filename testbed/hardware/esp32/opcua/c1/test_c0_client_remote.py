import asyncio
from asyncua import Client, ua

URL = "opc.tcp://192.168.1.115:4840/occ/"

async def main():
    async with Client(URL) as client:
        print("OPC UA C0 CONNECTED")

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

        print("OPC UA C0 READ/WRITE PASS")

asyncio.run(main())
