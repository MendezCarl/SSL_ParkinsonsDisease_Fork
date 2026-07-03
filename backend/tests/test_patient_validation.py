from __future__ import annotations

from pathlib import Path
import sys


# Ensure backend imports work whether pytest is run from repo root or backend dir.
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from patient_manager import create_patient, update_patient_info
from schema.patient_contracts import PatientUpdate


def test_create_patient_invalid_birthdate_returns_validation_errors():
    result = create_patient(
        name="Jane Smith",
        age=68,
        birthDate="not-a-date",
        height=165,
        weight=61,
        severity="Stage 2",
    )

    assert result == {
        "success": False,
        "errors": {"birthDate": "birthDate must be YYYY-MM-DD"},
    }


def test_create_patient_invalid_severity_returns_validation_errors():
    result = create_patient(
        name="Jane Smith",
        age=68,
        birthDate="1958-04-12",
        height=165,
        weight=61,
        severity="Stage 6",
    )

    assert result == {
        "success": False,
        "errors": {"severity": "Severity must be low, medium, high, or Stage 1-5"},
    }


def test_update_patient_invalid_height_returns_validation_errors():
    result = update_patient_info("patient123", PatientUpdate(height=-1))

    assert result == {
        "success": False,
        "errors": {"height": "Height must be a number between 0 and 300 (cm)"},
    }


def test_update_patient_invalid_severity_returns_validation_errors():
    result = update_patient_info("patient123", PatientUpdate(severity="unsupported"))

    assert result == {
        "success": False,
        "errors": {"severity": "Severity must be low, medium, high, or Stage 1-5"},
    }
