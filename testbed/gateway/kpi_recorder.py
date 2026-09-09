import csv
from datetime import datetime, timezone
from pathlib import Path


TESTBED_DIR = Path(__file__).resolve().parents[1]
RESULTS_DIR = TESTBED_DIR / "results"
KPI_PATH = RESULTS_DIR / "kpi_stream.csv"

FIELDNAMES = [
    "timestamp",
    "protocol",
    "security_level",
    "net_profile",
    "condition",
    "repeat_index",
    "serial_number",
    "header_id",
    "latency_ms",
    "verdict",
]


def write_kpi(
    payload: dict,
    latency_ms: float,
    verdict: str,
    protocol: str = "MQTT",
    security_level: str = "C0",
    net_profile: str = "NET-ideal",
    condition: str = "normal",
    repeat_index: int = 1,
) -> None:
    """Append one testbed measurement to the KPI CSV file."""

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    file_exists = KPI_PATH.exists()

    row = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "protocol": protocol,
        "security_level": security_level,
        "net_profile": net_profile,
        "condition": condition,
        "repeat_index": repeat_index,
        "serial_number": payload.get("serialNumber", "unknown"),
        "header_id": payload.get("headerId", ""),
        "latency_ms": round(latency_ms, 3),
        "verdict": verdict,
    }

    with KPI_PATH.open("a", newline="", encoding="utf-8") as kpi_file:
        writer = csv.DictWriter(kpi_file, fieldnames=FIELDNAMES)

        if not file_exists:
            writer.writeheader()

        writer.writerow(row)