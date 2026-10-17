from __future__ import annotations

import json
import os
from collections import Counter, defaultdict
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

PROFILES = ("C0", "C1", "C2")


def _empty(profile: str) -> dict:
    return {
        "profile": profile,
        "receive_events": 0,
        "transmit_events": 0,
        "matched_rx_tx_pairs": 0,
        "vehicles": [],
        "event_files": 0,
        "last_file_modified_utc": None,
    }


@lru_cache(maxsize=8)
def _summarize_cached(root_name: str, signatures: tuple) -> dict:
    root = Path(root_name)
    results = []

    for profile in PROFILES:
        summary = _empty(profile)
        pairs = defaultdict(Counter)
        vehicles = set()
        latest_mtime = None

        selected = [
            Path(name)
            for name, _, _ in signatures
            if Path(name).name.startswith(
                f"{profile.lower()}_service_"
            )
        ]

        summary["event_files"] = len(selected)

        for path in selected:
            try:
                mtime = path.stat().st_mtime
                latest_mtime = (
                    mtime if latest_mtime is None
                    else max(latest_mtime, mtime)
                )

                with path.open(errors="replace") as stream:
                    for line in stream:
                        try:
                            record = json.loads(line)
                        except (ValueError, TypeError):
                            continue

                        if not isinstance(record, dict):
                            continue

                        kind = record.get("event_type")
                        if kind not in ("occ_rx", "occ_tx"):
                            continue

                        vehicle = record.get("serialNumber")
                        seq = record.get("seq")

                        if not isinstance(vehicle, str):
                            continue
                        if not vehicle or len(vehicle) > 64:
                            continue
                        if isinstance(seq, bool) or not isinstance(seq, int):
                            continue

                        vehicles.add(vehicle)
                        pairs[(vehicle, seq)][kind] += 1

                        if kind == "occ_rx":
                            summary["receive_events"] += 1
                        else:
                            summary["transmit_events"] += 1

            except OSError:
                continue

        summary["matched_rx_tx_pairs"] = sum(
            min(c["occ_rx"], c["occ_tx"])
            for c in pairs.values()
        )
        summary["vehicles"] = sorted(vehicles)

        if latest_mtime is not None:
            summary["last_file_modified_utc"] = (
                datetime.fromtimestamp(
                    latest_mtime, timezone.utc
                ).isoformat()
            )

        results.append(summary)

    return {
        "source": "opcua-operational-event-logs",
        "evidence_type": "historical",
        "scientific_evidence": False,
        "provides_live_online_status": False,
        "available": True,
        "profiles": results,
        "vehicle_ids": sorted({
            vehicle
            for profile in results
            for vehicle in profile["vehicles"]
        }),
        "total_receive_events": sum(
            profile["receive_events"]
            for profile in results
        ),
        "total_transmit_events": sum(
            profile["transmit_events"]
            for profile in results
        ),
    }


def load_opcua_evidence() -> dict:
    location = os.environ.get(
        "OCC_OPCUA_EVIDENCE_DIR", ""
    ).strip()

    if not location:
        return {
            "available": False,
            "reason": "evidence_directory_not_configured",
            "evidence_type": "historical",
            "provides_live_online_status": False,
            "profiles": [_empty(p) for p in PROFILES],
        }

    root = Path(location)

    if not root.is_dir():
        return {
            "available": False,
            "reason": "evidence_directory_unavailable",
            "evidence_type": "historical",
            "provides_live_online_status": False,
            "profiles": [_empty(p) for p in PROFILES],
        }

    files = sorted(
        path for profile in PROFILES
        for path in root.glob(
            f"{profile.lower()}_service_*_events.jsonl"
        )
        if path.is_file()
    )

    # Only recognized event-log filenames are considered.
    # Size and mtime invalidate cached summaries after new events.
    signatures = tuple(
        (str(path), path.stat().st_size, path.stat().st_mtime_ns)
        for path in files
    )

    return _summarize_cached(str(root), signatures)
