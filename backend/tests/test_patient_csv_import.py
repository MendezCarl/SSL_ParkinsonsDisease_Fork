from __future__ import annotations

from pathlib import Path
import sys

import pytest


# Ensure backend imports work whether pytest is run from repo root or backend dir.
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import patient_manager


def test_import_patients_csv_text_normalizes_and_defaults(monkeypatch):
    captured: list[dict] = []

    def fake_create_patient(**kwargs):
        captured.append(kwargs)
        return {"success": True, "patient_id": "patient-1"}

    monkeypatch.setattr(patient_manager, "create_patient", fake_create_patient)

    result = patient_manager.import_patients_csv_text(
        "Full Name,DOB,Stage,Lab Results,Doctor Notes\n"
        "Jane Smith,12/31/1980,3,Baseline labs clear,Mild tremor noted\n"
    )

    assert result == {
        "success": True,
        "success_count": 1,
        "failure_count": 0,
        "imported_patient_ids": ["patient-1"],
        "errors": [],
    }

    assert len(captured) == 1
    created = captured[0]
    assert created["name"] == "Jane Smith"
    assert created["birthDate"] == "1980-12-31"
    assert created["severity"] == "Stage 3"
    assert created["height"] == "170 cm"
    assert created["weight"] == "70 kg"
    assert len(created["lab_results_history"]) == 1
    assert created["lab_results_history"][0].results == "Baseline labs clear"
    assert len(created["doctors_notes_history"]) == 1
    assert created["doctors_notes_history"][0].note == "Mild tremor noted"


def test_import_patients_csv_text_collects_partial_failures(monkeypatch):
    def fake_create_patient(**kwargs):
        if kwargs["birthDate"] == "not-a-date":
            return {"success": False, "errors": {"birthDate": "birthDate must be YYYY-MM-DD"}}
        return {"success": True, "patient_id": f"ok-{kwargs['name']}"}

    monkeypatch.setattr(patient_manager, "create_patient", fake_create_patient)

    result = patient_manager.import_patients_csv_text(
        "firstName,lastName,birthDate,severity\n"
        "Jane,Smith,1980-05-12,Stage 2\n"
        "Bad,Date,not-a-date,Stage 2\n"
    )

    assert result["success"] is True
    assert result["success_count"] == 1
    assert result["failure_count"] == 1
    assert result["imported_patient_ids"] == ["ok-Jane Smith"]
    assert result["errors"] == [
        {
            "row": 3,
            "errors": {"birthDate": "birthDate must be YYYY-MM-DD"},
            "error": None,
            "raw": {
                "firstName": "Bad",
                "lastName": "Date",
                "birthDate": "not-a-date",
                "severity": "Stage 2",
            },
        }
    ]


def test_import_patients_csv_text_rejects_empty_csv():
    with pytest.raises(ValueError, match="CSV file is empty"):
        patient_manager.import_patients_csv_text("   \n")
