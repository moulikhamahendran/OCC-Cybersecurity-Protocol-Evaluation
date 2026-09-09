import copy
import json
import sys
from pathlib import Path

from jsonschema import FormatChecker, ValidationError, validate

TESTBED_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TESTBED_DIR))

from vehicles.data_generator import make_reading

SCHEMA_PATH = TESTBED_DIR / "schemas" / "vehicle_reading.schema.json"

with SCHEMA_PATH.open(encoding="utf-8") as schema_file:
    schema = json.load(schema_file)


def validate_reading(reading):
    validate(
        instance=reading,
        schema=schema,
        format_checker=FormatChecker(),
    )


valid_reading = make_reading(0)
validate_reading(valid_reading)
print("PASS: Valid VDA 5050-style vehicle state accepted")


invalid_battery = copy.deepcopy(valid_reading)
invalid_battery["batteryState"]["batteryCharge"] = 101

try:
    validate_reading(invalid_battery)
except ValidationError:
    print("PASS: Invalid battery charge rejected")
else:
    raise AssertionError("Invalid battery charge was accepted")


missing_serial = copy.deepcopy(valid_reading)
del missing_serial["serialNumber"]

try:
    validate_reading(missing_serial)
except ValidationError:
    print("PASS: Missing serial number rejected")
else:
    raise AssertionError("Missing serial number was accepted")


print("All vehicle schema tests passed")