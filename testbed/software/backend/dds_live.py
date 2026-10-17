"""Read-only DDS operational telemetry. Never synthesizes telemetry."""
import json
import math
import os
import time
from pathlib import Path

DEFAULT_PATH = "/var/lib/occ-dashboard/dds-live/state.json"
MAX_AGE_SECONDS = 5.0

def dds_live_snapshot(path=None, now=None):
    path = Path(path or os.getenv("OCC_DDS_LIVE_STATE", DEFAULT_PATH))
    now = time.time() if now is None else float(now)

    result = {
        "source": "dds_occ_rx_observer",
        "scientific_evidence": False,
        "available": False,
        "protocol": "dds",
        "online_rule": "fresh observer state AND fresh source event, <=5s",
        "vehicle_count": 0,
        "online_count": 0,
        "vehicles": [],
    }
    try:
        stat = path.stat()
        record = json.loads(path.read_text())
    except (OSError, ValueError, TypeError) as exc:
        result["reason"] = type(exc).__name__
        return result

    if not isinstance(record, dict):
        result["reason"] = "invalid_state_type"
        return result

    result["available"] = True
    seq = record.get("seq")
    serial = record.get("serial_number", record.get("serialNumber", "VM-001"))
    if serial != "VM-001" or type(seq) is not int or seq < 0:
        result["reason"] = "invalid_vehicle_or_sequence"
        return result

    state_age = max(0.0, now - stat.st_mtime)
    source_age = record.get("source_age_seconds")
    fresh_source = (
        type(source_age) in (float, int)
        and math.isfinite(source_age)
        and 0 <= source_age <= MAX_AGE_SECONDS
    )
    online = (
        state_age <= MAX_AGE_SECONDS and fresh_source
        and record.get("source") == "new_dds_occ_rx"
        and record.get("online_at_observation") is True
    )

    telemetry = record.get("telemetry")
    required = ("speed", "battery", "pos_x", "pos_y", "heading")
    validated = None
    if isinstance(telemetry, dict) and all(
        type(telemetry.get(k)) in (int, float)
        and math.isfinite(telemetry[k])
        for k in required
    ) and isinstance(telemetry.get("state"), str):
        validated = dict(telemetry)

    vehicle = {
        "vehicle_id": serial,
        "protocol": "dds",
        "security_profile": "UNKNOWN",
        "online": online,
        "seq": seq,
        "telemetry_availability": "full" if validated else "identity_seq_only",
        "observer_state_age_seconds": round(state_age, 3),
        "source_age_seconds": source_age,
        "source": "dds_occ_rx_observer",
    }
    if validated is not None:
        vehicle["telemetry"] = validated

    result["vehicles"] = [vehicle]
    result["vehicle_count"] = 1
    result["online_count"] = int(online)
    result["reason"] = "fresh" if online else "stale"
    return result

def merge_dds_vehicle_snapshot(existing):
    # Keep historical MQTT/OPC UA state intact. A fresh DDS event
    # can take precedence over a stale record for the same vehicle.
    dds = dds_live_snapshot()
    merged = dict(existing)
    vehicles = [
        dict(v) for v in existing.get("vehicles", [])
        if isinstance(v, dict)
    ]
    for incoming in dds["vehicles"]:
        matching = next(
            (i for i, v in enumerate(vehicles)
             if v.get("vehicle_id") == incoming["vehicle_id"]),
            None
        )
        if matching is None:
            vehicles.append(incoming)
        elif incoming["online"] and not vehicles[matching].get("online"):
            vehicles[matching] = incoming
    merged["vehicles"] = vehicles
    merged["vehicle_count"] = len(vehicles)
    merged["online_count"] = sum(
        v.get("online") is True for v in vehicles
    )
    merged["dds_observer_available"] = dds["available"]
    merged["dds_observer_reason"] = dds.get("reason")
    return merged
