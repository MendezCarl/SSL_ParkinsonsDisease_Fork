from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parent
DATA_DIR = BACKEND_DIR / "data"
LEGACY_DIR = BACKEND_DIR / "legacy"

DTW_RUNS_DIR = DATA_DIR / "dtw_runs"
LABELLED_TRAINING_DATA_DIR = DATA_DIR / "labelled_training_data"
RECORDINGS_DIR = DATA_DIR / "recordings"
TEMPLATES_DIR = DATA_DIR / "templates"
JSONS_DIR = DATA_DIR / "jsons"

APP_DB_PATH = DATA_DIR / "app.db"
TEST_HISTORY_PATH = DATA_DIR / "test_history.json"

LEGACY_DATA_DIR = LEGACY_DIR / "data"
LEGACY_SCRIPTS_DIR = LEGACY_DIR / "scripts"
LEGACY_CAMERA_DIR = LEGACY_DIR / "camera"


def ensure_storage_layout() -> None:
    for path in (
        DATA_DIR,
        DTW_RUNS_DIR,
        LABELLED_TRAINING_DATA_DIR,
        RECORDINGS_DIR,
        TEMPLATES_DIR,
        JSONS_DIR,
        LEGACY_DIR,
        LEGACY_DATA_DIR,
        LEGACY_SCRIPTS_DIR,
        LEGACY_CAMERA_DIR,
    ):
        path.mkdir(parents=True, exist_ok=True)


ensure_storage_layout()
