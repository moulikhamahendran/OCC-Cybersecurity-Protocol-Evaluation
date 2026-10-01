from pathlib import Path
import importlib
import pkgutil
import sys

ROOT = Path(__file__).resolve().parent / "generated"
sys.path.insert(0, str(ROOT))

def find_type(name):
    for info in pkgutil.walk_packages([str(ROOT)]):
        module = importlib.import_module(info.name)
        if hasattr(module, name):
            return getattr(module, name)

    # fallback for a simple top-level generated module
    for py in ROOT.glob("*.py"):
        if py.name == "__init__.py":
            continue
        module = importlib.import_module(py.stem)
        if hasattr(module, name):
            return getattr(module, name)

    raise ImportError(
        f"Generated CycloneDDS type {name!r} not found under {ROOT}"
    )

FairV1Telemetry = find_type("FairV1Telemetry")
FairV1Echo = find_type("FairV1Echo")
