import copy
import json
import sys
from pathlib import Path

from jsonschema import (
    FormatChecker,
    ValidationError,
    validate,
)


TESTBED_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TESTBED_DIR))

from vehicles.data_generator import make_reading


SCHEMA_PATH = (
    TESTBED_DIR
    / "schemas"
    / "vehicle_reading.schema.json"
)

with SCHEMA_PATH.open(
    encoding="utf-8",
) as schema_file:
    schema = json.load(schema_file)


def validate_reading(reading):
    validate(
        instance=reading,
        schema=schema,
        format_checker=FormatChecker(),
    )


def expect_rejected(reading, description):
    try:
        validate_reading(reading)
    except ValidationError:
        print(f"PASS: {description}")
    else:
        raise AssertionError(
            f"Invalid payload accepted: {description}"
        )


valid_reading = make_reading(1)
validate_reading(valid_reading)

print(
    "PASS: Valid VDA 5050-aligned "
    "vehicle state accepted"
)

invalid_battery = copy.deepcopy(valid_reading)
invalid_battery["batteryState"]["batteryCharge"] = 101

expect_rejected(
    invalid_battery,
    "invalid battery charge rejected",
)

missing_serial = copy.deepcopy(valid_reading)
del missing_serial["serialNumber"]

expect_rejected(
    missing_serial,
    "missing serial number rejected",
)

missing_safety_state = copy.deepcopy(valid_reading)
del missing_safety_state["safetyState"]

expect_rejected(
    missing_safety_state,
    "missing safety state rejected",
)

invalid_operating_mode = copy.deepcopy(valid_reading)
invalid_operating_mode["operatingMode"] = "INVALID"

expect_rejected(
    invalid_operating_mode,
    "invalid operating mode rejected",
)

unknown_property = copy.deepcopy(valid_reading)
unknown_property["temperature"] = 25.0

expect_rejected(
    unknown_property,
    "unknown property rejected",
)

missing_measurement_time = copy.deepcopy(valid_reading)
del missing_measurement_time["t_send_ns"]

expect_rejected(
    missing_measurement_time,
    "missing latency timestamp rejected",
)

print("All vehicle schema tests passed")