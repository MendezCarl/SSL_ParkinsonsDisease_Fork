from __future__ import annotations

import json
from pathlib import Path
import sys


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services.dtw_migration_service import dtw_migration_service


def main() -> None:
    report = dtw_migration_service.migrate_historical_data(write_changes=True)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
