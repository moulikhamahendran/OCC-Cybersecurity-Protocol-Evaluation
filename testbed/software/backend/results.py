from __future__ import annotations

import csv
import json
import os
from pathlib import Path


TESTBED_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_MQTT_QUALIFICATION_ROOT = (
    TESTBED_ROOT
    / "results"
    / "fair_v1"
    / "mqtt"
    / "qualification_analysis"
)


def mqtt_qualification_root() -> Path:
    configured = os.getenv(
        "OCC_MQTT_QUALIFICATION_ROOT",
        "",
    ).strip()

    if configured:
        return Path(configured).expanduser().resolve()

    return DEFAULT_MQTT_QUALIFICATION_ROOT


def _coerce_csv_value(value: str):
    if value == "":
        return None

    try:
        return int(value)
    except ValueError:
        pass

    try:
        return float(value)
    except ValueError:
        return value


def _read_csv(path: Path) -> list[dict]:
    if not path.is_file():
        raise FileNotFoundError(path)

    with path.open(
        "r",
        encoding="utf-8",
        newline="",
    ) as handle:
        rows = list(csv.DictReader(handle))

    return [
        {
            key: _coerce_csv_value(value)
            for key, value in row.items()
        }
        for row in rows
    ]


def _read_json(path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(path)

    with path.open(
        "r",
        encoding="utf-8",
    ) as handle:
        return json.load(handle)


def load_mqtt_qualification_bundle() -> dict:
    root = mqtt_qualification_root()

    manifest = _read_json(
        root / "analysis_manifest.json"
    )

    aggregate = _read_csv(
        root
        / "mqtt_qualification_profile_aggregate.csv"
    )

    comparison = _read_csv(
        root
        / "mqtt_qualification_profile_comparison.csv"
    )

    repeats = _read_csv(
        root
        / "mqtt_qualification_per_repeat.csv"
    )

    if len(aggregate) != 3:
        raise ValueError(
            "expected exactly 3 MQTT profile aggregates"
        )

    if len(repeats) != 15:
        raise ValueError(
            "expected exactly 15 MQTT qualification repeats"
        )

    profiles = {
        row.get("profile")
        for row in aggregate
    }

    if profiles != {"C0", "C1", "C2"}:
        raise ValueError(
            f"unexpected MQTT aggregate profiles: {profiles}"
        )

    return {
        "status": "available",
        "scope": (
            "MQTT Vehicle-1 sequential qualification"
        ),
        "authoritative_notice": (
            "Derived dashboard data only. "
            "Scientific CSV/log evidence remains authoritative."
        ),
        "final_cross_protocol_interleaved_campaign": (
            manifest.get(
                "final_cross_protocol_interleaved_campaign",
                False,
            )
        ),
        "analysis_repository_head": (
            manifest.get(
                "analysis_repository_head"
            )
        ),
        "selected_run_count": (
            manifest.get(
                "selected_run_count"
            )
        ),
        "profiles": aggregate,
        "comparison_vs_c0": comparison,
        "repeat_count": len(repeats),
    }


def load_mqtt_qualification_repeats() -> dict:
    root = mqtt_qualification_root()

    repeats = _read_csv(
        root
        / "mqtt_qualification_per_repeat.csv"
    )

    if len(repeats) != 15:
        raise ValueError(
            "expected exactly 15 MQTT qualification repeats"
        )

    return {
        "scope": (
            "MQTT Vehicle-1 sequential qualification"
        ),
        "count": len(repeats),
        "runs": repeats,
    }


def mqtt_qualification_status() -> dict:
    root = mqtt_qualification_root()

    required = [
        "analysis_manifest.json",
        "mqtt_qualification_per_repeat.csv",
        "mqtt_qualification_profile_aggregate.csv",
        "mqtt_qualification_profile_comparison.csv",
        "MQTT_QUALIFICATION_KPI_SUMMARY.md",
    ]

    files = {
        name: (root / name).is_file()
        for name in required
    }

    available = all(files.values())

    return {
        "status": (
            "available"
            if available
            else "unavailable"
        ),
        "scope": (
            "MQTT Vehicle-1 sequential qualification"
        ),
        "results_root": str(root),
        "files": files,
        "final_cross_protocol_interleaved_campaign": False,
    }
