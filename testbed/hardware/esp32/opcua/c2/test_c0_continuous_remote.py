import asyncio
import time
from asyncua import Client, ua

URL = "opc.tcp://192.168.1.115:4840/occ/"

async def main():
    async with Client(URL) as client:
        print("OPC UA C0 CONTINUOUS CONNECTED")

        seq_node = client.get_node("ns=2;s=Vehicle1.Sequence")
        speed_node = client.get_node("ns=2;s=Vehicle1.Speed")
        battery_node = client.get_node("ns=2;s=Vehicle1.Battery")
        timestamp_node = client.get_node("ns=2;s=Vehicle1.TimestampMs")

        for seq in range(1, 31):
            speed = 2.5 + ((seq % 5) * 0.1)
            battery = 87.0 - (seq * 0.01)
            timestamp_ms = time.time_ns() // 1_000_000

            await seq_node.write_value(
                ua.Variant(seq, ua.VariantType.UInt32)
            )

            await speed_node.write_value(
                ua.Variant(speed, ua.VariantType.Double)
            )

            await battery_node.write_value(
                ua.Variant(battery, ua.VariantType.Double)
            )

            await timestamp_node.write_value(
                ua.Variant(timestamp_ms, ua.VariantType.UInt64)
            )

            print(
                f"seq={seq:02d} "
                f"speed={speed:.2f} "
                f"battery={battery:.2f} "
                f"timestamp={timestamp_ms}"
            )

            await asyncio.sleep(1)

        print("OPC UA C0 30-SECOND CONTINUOUS TEST PASS")

asyncio.run(main())
