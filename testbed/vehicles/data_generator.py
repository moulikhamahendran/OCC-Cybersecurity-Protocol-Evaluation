import json
import math
import time
from datetime import datetime, timezone


def make_reading(
    sequence: int,
    serial_number: str = "VM-001",
) -> dict:
    """Generate deterministic VDA 5050-aligned telemetry."""

    x_position = round(sequence * 0.1, 3)
    y_position = round(
        5.0 * math.sin(sequence / 20),
        3,
    )

    battery_charge = round(
        max(0.0, 90.0 - sequence * 0.001),
        3,
    )

    timestamp = (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )

    return {
        "headerId": sequence,
        "timestamp": timestamp,
        "version": "2.1.0",
        "manufacturer": "OvGU-IEPS",
        "serialNumber": serial_number,
        "orderId": "OCC-TEST-ORDER",
        "orderUpdateId": 0,
        "lastNodeId": "NODE-START",
        "lastNodeSequenceId": 0,
        "nodeStates": [],
        "edgeStates": [],
        "agvPosition": {
            "positionInitialized": True,
            "localizationScore": 1.0,
            "x": x_position,
            "y": y_position,
            "theta": 0.0,
            "mapId": "OvGU-Testbed-Map",
        },
        "velocity": {
            "vx": 1.0,
            "vy": 0.0,
            "omega": 0.0,
        },
        "driving": True,
        "paused": False,
        "newBaseRequest": False,
        "distanceSinceLastNode": x_position,
        "actionStates": [],
        "batteryState": {
            "batteryCharge": battery_charge,
            "batteryVoltage": 48.0,
            "batteryHealth": 100.0,
            "charging": False,
        },
        "operatingMode": "AUTOMATIC",
        "errors": [],
        "safetyState": {
            "eStop": "NONE",
            "fieldViolation": False,
        },
        "t_send_ns": time.time_ns(),
    }


if __name__ == "__main__":
    for sequence in range(10):
        print(
            json.dumps(
                make_reading(sequence),
                indent=2,
            )
        )