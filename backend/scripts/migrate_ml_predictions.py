from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from repo.sql_models import Base, MLPrediction
from storage_paths import APP_DB_PATH


DEFAULT_DB_URL = os.getenv("DB_URL", f"sqlite:///{APP_DB_PATH.as_posix()}")


def migrate_ml_predictions(database_url: str | None = None) -> dict[str, object]:
    selected_database_url = database_url or DEFAULT_DB_URL
    engine = create_engine(selected_database_url, future=True)
    existed_before = inspect(engine).has_table(MLPrediction.__tablename__)

    Base.metadata.tables[MLPrediction.__tablename__].create(bind=engine, checkfirst=True)
    for index in MLPrediction.__table__.indexes:
        index.create(bind=engine, checkfirst=True)

    existing_indexes = {index["name"] for index in inspect(engine).get_indexes(MLPrediction.__tablename__)}
    expected_indexes = {index.name for index in MLPrediction.__table__.indexes}
    missing_indexes = sorted(expected_indexes - existing_indexes)

    return {
        "database_url": selected_database_url,
        "table": MLPrediction.__tablename__,
        "created": not existed_before,
        "missing_indexes": missing_indexes,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Create the ml_predictions table if it is missing.")
    parser.add_argument(
        "--database-url",
        default=None,
        help="SQLAlchemy database URL. Defaults to the backend application database.",
    )
    args = parser.parse_args()

    report = migrate_ml_predictions(args.database_url)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
