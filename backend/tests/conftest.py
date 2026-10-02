import sys
from pathlib import Path

# Mirror the sys.path insertion from app.main so bare legacy imports resolve
# regardless of import order during test collection.
legacy_path = Path(__file__).resolve().parent.parent / "app" / "legacy"
if str(legacy_path) not in sys.path:
    sys.path.insert(0, str(legacy_path))
