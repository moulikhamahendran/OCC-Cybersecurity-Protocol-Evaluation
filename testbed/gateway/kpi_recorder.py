import csv
import json
import os
import threading
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


TESTBED_DIR = Path(__file__).resolve().parents[1]
RESULTS_DIR = TESTBED_DIR / "results"
KPI_PATH = RESULTS_DIR / "kpi_stream.csv"

# Automated runs receive RUN_ID from the experiment runner.
# Manually started gateways receive their own unique ID.
RUN_ID = os.getenv("RUN_ID") or (
    "manual_"
    + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    + "_"
    + uuid4().hex
)

CSV_FIELDS = [
    "timestamp",
    "run_id",
    "protocol",
    "security_level",
    "net_profile",
    "condition",
    "repeat_index",
    "serial_number",
    "header_id",
    "latency_ms",
    "jitter_ms",
    "throughput_messages_per_second",
    "throughput_kbps",
    "lost_messages",
    "loss_percent",
    "verdict",
]

WINDOW_SECONDS = 1.0

_stream_states: dict[tuple[Any, ...], dict[str, Any]] = {}
_file_prepared = False
_lock = threading.Lock()


def _prepare_kpi_file() -> None:
    global _file_prepared

    if _file_prepared:
        return

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    if KPI_PATH.exists() and KPI_PATH.stat().st_size > 0:
        with KPI_PATH.open(
            "r",
            newline="",
            encoding="utf-8",
        ) as existing_file:
            reader = csv.reader(existing_file)
            existing_header = next(reader, [])

        if existing_header != CSV_FIELDS:
            archive_timestamp = datetime.now(
                timezone.utc
            ).strftime("%Y%m%dT%H%M%S%fZ")

            archive_path = RESULTS_DIR / (
                f"kpi_stream_legacy_{archive_timestamp}_"
                f"{uuid4().hex}.csv"
            )

            KPI_PATH.rename(archive_path)

            print(
                f"Previous KPI file archived as "
                f"{archive_path.name}"
            )

    if not KPI_PATH.exists() or KPI_PATH.stat().st_size == 0:
        with KPI_PATH.open(
            "w",
            newline="",
            encoding="utf-8",
        ) as kpi_file:
            writer = csv.DictWriter(
                kpi_file,
                fieldnames=CSV_FIELDS,
            )
            writer.writeheader()

    _file_prepared = True


def _calculate_metrics(
    key: tuple[Any, ...],
    header_id: int | None,
    latency_ms: float,
    payload_bytes: int,
) -> dict[str, float | int]:
    now = time.monotonic()

    state = _stream_states.setdefault(
        key,
        {
            "previous_latency_ms": None,
            "previous_header_id": None,
            "received_messages": 0,
            "lost_messages": 0,
            "recent_messages": deque(),
        },
    )

    previous_latency = state["previous_latency_ms"]

    if previous_latency is None:
        jitter_ms = 0.0
    else:
        jitter_ms = abs(latency_ms - previous_latency)

    state["previous_latency_ms"] = latency_ms
    state["received_messages"] += 1

    previous_header_id = state["previous_header_id"]

    # Provisional sequence-gap estimate, not measured network loss.
    # This will be replaced by sent-versus-received accounting.
    if header_id is not None:
        if (
            previous_header_id is not None
            and header_id > previous_header_id + 1
        ):
            gap = header_id - previous_header_id - 1

            if gap <= 1000:
                state["lost_messages"] += gap

        if (
            previous_header_id is None
            or header_id > previous_header_id
        ):
            state["previous_header_id"] = header_id

    received_messages = state["received_messages"]
    lost_messages = state["lost_messages"]
    expected_messages = received_messages + lost_messages

    loss_percent = (
        lost_messages / expected_messages * 100.0
        if expected_messages > 0
        else 0.0
    )

    recent_messages = state["recent_messages"]
    recent_messages.append((now, payload_bytes))

    window_start = now - WINDOW_SECONDS

    while (
        recent_messages
        and recent_messages[0][0] < window_start
    ):
        recent_messages.popleft()

    throughput_messages_per_second = (
        len(recent_messages) / WINDOW_SECONDS
    )

    bytes_in_window = sum(
        message_size
        for _, message_size in recent_messages
    )

    # JSON payload throughput only; excludes protocol overhead.
    throughput_kbps = (
        bytes_in_window * 8 / 1000.0 / WINDOW_SECONDS
    )

    return {
        "jitter_ms": round(jitter_ms, 3),
        "throughput_messages_per_second": round(
            throughput_messages_per_second, 3
        ),
        "throughput_kbps": round(throughput_kbps, 3),
        "lost_messages": lost_messages,
        "loss_percent": round(loss_percent, 3),
    }


def write_kpi(
    payload: dict,
    latency_ms: float,
    verdict: str,
    security_level: str,
    condition: str = "normal",
) -> dict[str, float | int]:
    protocol = os.getenv("PROTOCOL", "MQTT")
    net_profile = os.getenv("NET_PROFILE", "NET-ideal")
    repeat_index = int(os.getenv("REPEAT_INDEX", "1"))

    serial_number = str(
        payload.get(
            "serialNumber",
            payload.get("vehicle_id", "unknown"),
        )
    )

    raw_header_id = payload.get(
        "headerId",
        payload.get("sequence"),
    )

    try:
        header_id = (
            int(raw_header_id)
            if raw_header_id is not None
            else None
        )
    except (TypeError, ValueError):
        header_id = None

    payload_bytes = len(
        json.dumps(
            payload,
            separators=(",", ":"),
        ).encode("utf-8")
    )

    key = (
        RUN_ID,
        protocol,
        security_level,
        net_profile,
        condition,
        repeat_index,
        serial_number,
    )

    with _lock:
        _prepare_kpi_file()

        metrics = _calculate_metrics(
            key=key,
            header_id=header_id,
            latency_ms=latency_ms,
            payload_bytes=payload_bytes,
        )

        row = {
            "timestamp": datetime.now(
                timezone.utc
            ).isoformat(),
            "run_id": RUN_ID,
            "protocol": protocol,
            "security_level": security_level,
            "net_profile": net_profile,
            "condition": condition,
            "repeat_index": repeat_index,
            "serial_number": serial_number,
            "header_id": header_id if header_id is not None else "",
            "latency_ms": round(latency_ms, 3),
            "jitter_ms": metrics["jitter_ms"],
            "throughput_messages_per_second": metrics[
                "throughput_messages_per_second"
            ],
            "throughput_kbps": metrics["throughput_kbps"],
            "lost_messages": metrics["lost_messages"],
            "loss_percent": metrics["loss_percent"],
            "verdict": verdict,
        }

        with KPI_PATH.open(
            "a",
            newline="",
            encoding="utf-8",
        ) as kpi_file:
            writer = csv.DictWriter(
                kpi_file,
                fieldnames=CSV_FIELDS,
            )
            writer.writerow(row)

    return metrics


def reset_kpi_state() -> None:
    with _lock:
        _stream_states.clear()