import time
import random

vehicle_id = "AGV-01"

while True:
    speed = random.randint(20, 80)
    battery = random.randint(40, 100)
    latency = round(random.uniform(5, 20), 2)

    print(f"""
========================
Vehicle ID : {vehicle_id}
Speed      : {speed} km/h
Battery    : {battery} %
Latency    : {latency} ms
========================
""")

    time.sleep(2)
