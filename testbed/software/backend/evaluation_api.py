"""Read-only inventory of existing OCC evaluation CSVs; never synthetic data."""
import csv
import os
import re
from pathlib import Path
from fastapi import APIRouter

router = APIRouter(prefix="/api/v1/evaluation", tags=["evaluation historical datasets"])
RESULTS = Path(os.getenv("OCC_RESULTS_DIR", str(Path(__file__).resolve().parents[1]/"results")))
PROTOCOLS = ("mqtt", "opcua", "dds")
PROFILES = ("C0", "C1", "C2")
PREFERRED = ("summary", "final", "network", "security", "hardware", "cross_protocol")


def classify(path):
    relative = path.relative_to(RESULTS).as_posix()
    lower = relative.lower()
    name = path.name.lower()
    if not any(x in lower for x in (*PROTOCOLS, "cross_protocol")):
        return None
    # Reject individual samples/repeats and enormous raw runs, keep comparable summaries.
    if any(x in name for x in ("samples.csv", "publisher.csv", "resources.csv", "repeat_", "repeat1", "repeat2", "repeat3")):
        return None
    if "summary" not in name and not name.startswith("mqtt_final"):
        return None
    protocol = next((p for p in PROTOCOLS if p in lower), "cross_protocol")
    match = re.search(r"(?:^|[/_.-])(c[012])(?:[/_.-]|$)", lower)
    profile = match.group(1).upper() if match else None
    if "harmonized-dos" in lower or "attack" in lower or "dos" in lower:
        condition = "attack"
    elif "delay" in lower or "jitter" in lower or "loss" in lower:
        condition = "network_impairment"
    else:
        condition = "historical_mixed_or_normal"
    return {"path": relative, "protocol": protocol, "profile_hint": profile, "condition_hint": condition}


@router.get("/summary")
def summary():
    datasets = []
    modes = {p: {c: {"datasets": 0, "rows": 0} for c in PROFILES} for p in PROTOCOLS}
    if not RESULTS.is_dir():
        return {"source_type": "historical_csv", "results_root": str(RESULTS), "error": "results directory missing", "datasets": [], "matrix": modes}
    for path in sorted(RESULTS.rglob("*.csv")):
        info = classify(path)
        if info is None:
            continue
        try:
            with path.open(newline="", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                if not reader.fieldnames:
                    continue
                columns = list(reader.fieldnames)
                count = 0
                seen_profiles = set()
                examples = []
                for row in reader:
                    count += 1
                    prof = (row.get("profile") or row.get("security_profile") or row.get("security_level") or row.get("config") or info["profile_hint"] or "").strip().upper()
                    if prof in PROFILES:
                        seen_profiles.add(prof)
                        if info["protocol"] in PROTOCOLS:
                            modes[info["protocol"]][prof]["rows"] += 1
                    if len(examples) < 2:
                        examples.append({k: str(v)[:120] for k,v in row.items() if k is not None and v is not None})
                    if count >= 10000:
                        break
                if not seen_profiles and info["profile_hint"] in PROFILES:
                    seen_profiles.add(info["profile_hint"])
                    if info["protocol"] in PROTOCOLS:
                        modes[info["protocol"]][info["profile_hint"]]["rows"] += count
                for prof in seen_profiles:
                    if info["protocol"] in PROTOCOLS:
                        modes[info["protocol"]][prof]["datasets"] += 1
                datasets.append({**info, "row_count_scanned": count, "profiles_found": sorted(seen_profiles), "columns": columns, "sample_rows": examples})
        except (OSError, UnicodeError, csv.Error) as exc:
            datasets.append({**info, "read_error": str(exc)})
    return {"source_type": "historical_csv", "results_root": str(RESULTS), "dataset_count": len(datasets), "matrix": modes, "datasets": datasets, "warning": "Historical datasets are not live readings or proof of operational profile support. Row counts are data discovery only."}
