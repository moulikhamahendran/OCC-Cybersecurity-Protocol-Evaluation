def make_reading(sequence: int) -> dict:
    """Generate deterministic test data, not real sensor measurements."""
    return {
        "vehicle_id": "vehicle-001",
        "sequence": sequence,
        "speed_mps": 1.0,
        "battery_percent": round(90.0 - sequence * 0.01, 2),
        "position": {
            "x_m": round(sequence * 1.0, 2),
            "y_m": 0.0,
        },
    }


if __name__ == "__main__":
    import json

    for sequence in range(10):
        print(json.dumps(make_reading(sequence)))