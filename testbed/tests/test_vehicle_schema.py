import json
import sys
from pathlib import Path

from jsonschema import ValidationError, validate

TESTBED_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TESTBED_DIR))

from vehicles.data_generator import make_reading

SCHEMA_PATH = TESTBED_DIR / "schemas" / "vehicle_reading.schema.json"

with SCHEMA_PATH.open(encoding="utf-8") as schema_file:
    schema = json.load(schema_file)

valid_reading = make_reading(0)
validate(instance=valid_reading, schema=schema)
print("PASS: Valid vehicle reading accepted")

invalid_reading = make_reading(1)
invalid_reading["battery_percent"] = 101

try:
    validate(instance=invalid_reading, schema=schema)
except ValidationError:
    print("PASS: Invalid vehicle reading rejected")
else:
    raise AssertionError("Invalid vehicle reading was incorrectly accepted")