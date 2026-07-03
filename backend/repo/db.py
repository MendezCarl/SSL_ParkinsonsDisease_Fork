from sqlalchemy import create_engine

from storage_paths import TEST_DB_PATH

# Database URL for SQLite (you can change this to your preferred database)
DATABASE_URL = f"sqlite:///{TEST_DB_PATH.as_posix()}"
engine = create_engine(DATABASE_URL, echo=True)
