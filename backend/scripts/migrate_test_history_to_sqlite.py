from __future__ import annotations

import argparse
import json
from pathlib import Path

from services.test_history_service import migrate_test_history_file
from storage_paths import TEST_HISTORY_PATH


def main() -> None:
    parser = argparse.ArgumentParser(description="Import legacy test_history.json rows into SQLite testresults.")
    parser.add_argument(
        "--path",
        type=Path,
        default=TEST_HISTORY_PATH,
        help="Path to the legacy test_history.json file.",
    )
    args = parser.parse_args()

    report = migrate_test_history_file(args.path)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
