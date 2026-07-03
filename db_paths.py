"""
Shared locations for JARVIS's SQLite databases.

Both databases live in data/:
- data/jarvis.db       — user-facing memory + dispatch registry
- data/jarvis_data.db  — intelligence-layer metrics (tracking, learning,
                         A/B testing, template evolution)

Older versions kept jarvis_data.db in the repo root; it is moved into
data/ on first access so existing metrics are preserved.
"""

from pathlib import Path

ROOT_DIR = Path(__file__).parent
DATA_DIR = ROOT_DIR / "data"


def intelligence_db_path() -> Path:
    """Return the intelligence-layer DB path, migrating a legacy root-level file."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = DATA_DIR / "jarvis_data.db"
    legacy = ROOT_DIR / "jarvis_data.db"
    if legacy.exists() and not path.exists():
        legacy.rename(path)
    return path
