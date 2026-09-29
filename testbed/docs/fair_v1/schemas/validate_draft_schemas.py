from pathlib import Path
import json
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parent
VALID = ROOT / "examples" / "valid"
INVALID = ROOT / "examples" / "invalid"

mapping = {
    "run_metadata_": "fair_v1_run_metadata.schema.json",
    "raw_row_": "fair_v1_raw_row.schema.json",
    "occ_message_event_": "fair_v1_occ_message_event.schema.json",
    "mqtt_echo_": "fair_v1_mqtt_echo.schema.json",
    "middleware_event_": "fair_v1_middleware_event.schema.json",
    "occ_system_": "fair_v1_occ_system_sample.schema.json",
    "attack_event_": "fair_v1_attack_event.schema.json",
}

def schema_for(filename):
    for prefix, schema_name in mapping.items():
        if filename.startswith(prefix):
            return ROOT / schema_name
    raise RuntimeError(f"No schema mapping for {filename}")

schemas = {}

for schema_path in ROOT.glob("*.schema.json"):
    obj = json.loads(schema_path.read_text())
    Draft202012Validator.check_schema(obj)
    schemas[schema_path.name] = obj

print(f"Schema self-check: PASS ({len(schemas)} schemas)")

valid_count = 0

for example in sorted(VALID.glob("*.json")):
    sp = schema_for(example.name)
    schema = schemas[sp.name]
    data = json.loads(example.read_text())

    Draft202012Validator(
        schema,
        format_checker=FormatChecker()
    ).validate(data)

    print("VALID PASS  ", example.name)
    valid_count += 1

invalid_count = 0

for example in sorted(INVALID.glob("*.json")):
    sp = schema_for(example.name)
    schema = schemas[sp.name]
    data = json.loads(example.read_text())

    validator = Draft202012Validator(
        schema,
        format_checker=FormatChecker()
    )

    errors = list(validator.iter_errors(data))

    if not errors:
        raise SystemExit(
            f"FAIL: invalid example unexpectedly passed: {example.name}"
        )

    print("INVALID PASS", example.name)
    invalid_count += 1

print()
print("Draft validation complete.")
print("Valid examples passed:", valid_count)
print("Invalid examples correctly rejected:", invalid_count)
print("STATUS: DRAFT - NOT FROZEN")
