from __future__ import annotations

import json
from pathlib import Path
import sys

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

# Ensure backend imports work whether pytest is run from repo root or backend dir.
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from repo.sql_models import Base, Patient, User
import services.test_history_service as test_history_service


def _set_temp_history_db(monkeypatch, db_path: Path) -> None:
    engine = create_engine(f"sqlite:///{db_path.as_posix()}", future=True)
    event.listen(engine, "connect", lambda dbapi_conn, _: dbapi_conn.execute("PRAGMA foreign_keys = ON;"))
    Base.metadata.create_all(engine)
    session_local = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False, future=True)
    monkeypatch.setattr(test_history_service, "SessionLocal", session_local)


def _seed_patient(patient_id: str) -> None:
    with test_history_service.SessionLocal() as session:
        owner = User(
            username=f"{patient_id}@example.com",
            full_name="History Test Owner",
            email=None,
            hashed_password="test",
            location="Test",
            title="Tester",
            speciality="Test",
        )
        session.add(owner)
        session.flush()
        session.add(
            Patient(
                patient_id=patient_id,
                record_number=f"REC-{patient_id[-6:]}",
                user_id=owner.id,
                name=patient_id,
                severity="Stage 2",
            )
        )
        session.commit()


def test_migrate_test_history_file_imports_rows_without_duplicates(monkeypatch, tmp_path):
    db_path = tmp_path / "history.db"
    _set_temp_history_db(monkeypatch, db_path)
    _seed_patient("patient-1")

    history_path = tmp_path / "test_history.json"
    history_path.write_text(
        json.dumps(
            {
                "patient-1": [
                    {
                        "test_id": "session-1",
                        "test_name": "finger-tapping",
                        "date": "2026-07-04T12:00:00Z",
                        "recording_file": "patient-1_finger-tapping_session-1.mp4",
                        "frame_count": 120,
                        "fps": 30,
                        "summary_available": True,
                        "status": "completed",
                        "indicator": {"color": "success", "label": "Completed"},
                        "dtw": {
                            "session_id": "session-1",
                            "distance": 1.5,
                            "avg_step_cost": 0.2,
                            "similarity": 0.9,
                            "artifacts": {"dir": "/tmp/session-1"},
                        },
                    }
                ]
            }
        )
    )

    first_report = test_history_service.migrate_test_history_file(history_path)
    second_report = test_history_service.migrate_test_history_file(history_path)

    assert first_report == {
        "patients": 1,
        "inserted": 1,
        "updated": 0,
        "skipped_invalid": 0,
        "skipped_missing_patient": 0,
    }
    assert second_report == {
        "patients": 1,
        "inserted": 0,
        "updated": 1,
        "skipped_invalid": 0,
        "skipped_missing_patient": 0,
    }

    tests = test_history_service.get_patient_tests("patient-1")
    assert len(tests) == 1
    assert tests[0]["test_id"] == "session-1"
    assert tests[0]["dtw"]["artifacts"]["dir"] == "/tmp/session-1"
    assert tests[0]["status"] == "completed"
    assert tests[0]["indicator"]["label"] == "Completed"


def test_append_patient_test_preserves_extra_metadata(monkeypatch, tmp_path):
    db_path = tmp_path / "history.db"
    _set_temp_history_db(monkeypatch, db_path)
    _seed_patient("patient-2")

    test_history_service.append_patient_test(
        "patient-2",
        {
            "test_name": "stand-and-sit",
            "date": "2026-07-05T08:30:00Z",
            "recording_file": "patient-2_stand-and-sit.mp4",
            "summary_available": False,
            "status": "pending-review",
            "indicator": {"color": "warning", "label": "Queued"},
            "notes": {"source": "manual"},
        },
    )

    tests = test_history_service.get_patient_tests("patient-2")
    assert tests == [
        {
            "test_id": "1",
            "test_name": "stand-and-sit",
            "date": "2026-07-05T08:30:00+00:00",
            "recording_file": "patient-2_stand-and-sit.mp4",
            "frame_count": None,
            "fps": None,
            "summary_available": False,
            "dtw": None,
            "status": "pending-review",
            "indicator": {"color": "warning", "label": "Queued"},
            "notes": {"source": "manual"},
        }
    ]


def test_append_patient_test_rejects_missing_patient(monkeypatch, tmp_path):
    db_path = tmp_path / "history.db"
    _set_temp_history_db(monkeypatch, db_path)

    try:
        test_history_service.append_patient_test(
            "missing-patient",
            {
                "test_name": "finger-tapping",
                "date": "2026-07-05T08:30:00Z",
            },
        )
    except ValueError as exc:
        assert str(exc) == "Patient 'missing-patient' not found"
    else:
        raise AssertionError("Expected append_patient_test to reject missing patient ids")


def test_persist_session_analysis_merges_dtw_and_ml_snapshots(monkeypatch, tmp_path):
    db_path = tmp_path / "history.db"
    _set_temp_history_db(monkeypatch, db_path)
    _seed_patient("patient-3")

    test_history_service.append_patient_test(
        "patient-3",
        {
            "test_id": "session-merge",
            "test_name": "finger-tapping",
            "date": "2026-07-05T09:00:00Z",
            "recording_file": "patient-3_finger-tapping.mp4",
        },
    )

    assert test_history_service.persist_session_analysis(
        "session-merge",
        dtw_metrics={
            "session_id": "session-merge",
            "distance_pos": 1.25,
            "similarity_overall": 0.81,
            "similarity": 0.81,
        },
    ) is True
    assert test_history_service.persist_session_analysis(
        "session-merge",
        ml_prediction={
            "predicted_updrs_stage": 2,
            "probabilities": {"0": 0.1, "1": 0.8},
            "severity": "Stage 3",
            "severity_stage": 3,
            "prediction": "Stage 3",
            "confidence": 0.8,
        },
    ) is True

    tests = test_history_service.get_patient_tests("patient-3")
    assert tests[0]["dtw"]["session_id"] == "session-merge"
    assert tests[0]["dtw"]["distance"] == 1.25
    assert tests[0]["analysis"]["dtw_metrics"]["similarity_overall"] == 0.81
    assert tests[0]["analysis"]["ml_prediction"]["predicted_updrs_stage"] == 2
    assert tests[0]["analysis"]["ml_prediction"]["severity"] == "Stage 3"
