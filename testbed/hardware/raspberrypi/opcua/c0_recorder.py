import asyncio
import csv
import time
from pathlib import Path
from asyncua import Client

URL = "opc.tcp://127.0.0.1:4840/occ/"
EXPECTED = 600
POLL_S = 0.001

async def main():
    run_name = input("Run name [repeat1]: ").strip() or "repeat1"

    path = Path(f"results/opcua_c0/{run_name}.csv")

    async with Client(URL) as client:
        seq_node = client.get_node("ns=2;s=Vehicle1.Sequence")
        ts_node = client.get_node("ns=2;s=Vehicle1.TimestampMs")
        speed_node = client.get_node("ns=2;s=Vehicle1.Speed")
        battery_node = client.get_node("ns=2;s=Vehicle1.Battery")

        print()
        print("====================================")
        print("OPC UA C0 POLLING RECORDER READY")
        print(f"Output: {path}")
        print("Waiting for NEW RUN seq=1...")
        print("====================================")
        print()

        # Ignore old seq=600 and wait for next experiment
        while True:
            seq = int(await seq_node.read_value())
            if seq == 1:
                break
            await asyncio.sleep(POLL_S)

        print("OFFICIAL RUN DETECTED: seq=1")
        print()

        seen = set()
        rows = []
        previous_latency = None

        while True:
            seq = int(await seq_node.read_value())

            if 1 <= seq <= EXPECTED and seq not in seen:
                receive_ms = time.time_ns() // 1_000_000

                timestamp_ms = int(await ts_node.read_value())
                speed = float(await speed_node.read_value())
                battery = float(await battery_node.read_value())

                # Verify that Sequence did not change while reading fields
                seq_confirm = int(await seq_node.read_value())

                if seq_confirm != seq:
                    await asyncio.sleep(0)
                    continue

                latency_ms = receive_ms - timestamp_ms

                if previous_latency is None:
                    jitter_ms = 0
                else:
                    jitter_ms = abs(latency_ms - previous_latency)

                previous_latency = latency_ms
                seen.add(seq)

                rows.append([
                    seq,
                    timestamp_ms,
                    receive_ms,
                    latency_ms,
                    jitter_ms,
                    speed,
                    battery
                ])

                print(
                    f"{len(seen):03d}/600 "
                    f"seq={seq} "
                    f"latency={latency_ms}ms "
                    f"jitter={jitter_ms}ms"
                )

            if seq >= EXPECTED:
                # small grace period for final observation
                await asyncio.sleep(0.1)
                break

            await asyncio.sleep(POLL_S)

        rows.sort(key=lambda x: x[0])

        with path.open("w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "sequence",
                "send_timestamp_ms",
                "receive_timestamp_ms",
                "latency_ms",
                "jitter_ms",
                "speed",
                "battery"
            ])
            writer.writerows(rows)

        missing = sorted(set(range(1, EXPECTED + 1)) - seen)

        print()
        print("====================================")
        print("C0 CAPTURE FINISHED")
        print(f"Recorded   : {len(seen)}")
        print(f"Missing    : {missing}")
        print(f"Duplicates : 0")
        print(f"Saved      : {path}")
        print("====================================")

        if len(seen) == 600 and not missing:
            print("RESULT: VALID OFFICIAL REPEAT ✅")
        else:
            print("RESULT: INVALID - DO NOT USE ❌")

asyncio.run(main())
