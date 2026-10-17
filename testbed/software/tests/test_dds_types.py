import json
import sys
from pathlib import Path


TESTBED_DIR = Path(__file__).resolve().parents[1]
DDS_DIR = TESTBED_DIR / "protocols" / "dds"

sys.path.insert(0, str(TESTBED_DIR))
sys.path.insert(0, str(DDS_DIR))

from protocols.dds.dds_types import VehicleState
from vehicles.data_generator import make_reading


payload = make_reading(7, serial_number="VM-TEST")

sample = VehicleState(
    header_id=payload["headerId"],
    timestamp=payload["timestamp"],
    version=payload["version"],
    manufacturer=payload["manufacturer"],
    serial_number=payload["serialNumber"],
    payload_json=json.dumps(
        payload,
        separators=(",", ":"),
    ),
    t_send_ns=payload["t_send_ns"],
)

decoded = json.loads(sample.payload_json)

assert sample.header_id == 7
assert sample.serial_number == "VM-TEST"
assert decoded["version"] == "2.1.0"
assert decoded["agvPosition"]["positionInitialized"] is True
assert decoded["driving"] is True
assert decoded["paused"] is False
assert decoded["safetyState"]["eStop"] == "NONE"
assert decoded["t_send_ns"] == sample.t_send_ns

print("PASS: DDS VehicleState type created")
print("PASS: VDA 5050-style payload preserved")
print("All DDS type tests passed")
