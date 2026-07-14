from __future__ import annotations

from datetime import date
from pathlib import Path
import sys

# Ensure backend imports work whether pytest is run from repo root or backend dir.
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from patient_manager import SessionLocal, _gen_patient_id, _get_default_owner_user_id
from repo.patient_repository import PatientRepository
from repo.sql_models import Patient


def test_update_only_applies_allowlisted_fields():
    with SessionLocal() as session:
        prepo = PatientRepository(session)
        owner_user_id = _get_default_owner_user_id(session)
        patient_id = _gen_patient_id("RepoTest")

        patient = Patient(
            patient_id=patient_id,
            record_number="REC-TEST-0001",
            user_id=owner_user_id,
            name="Repo Test",
            dob=date(1970, 1, 1),
            height=170,
            weight=70,
            severity="Stage 1",
        )
        prepo.add(patient)

        try:
            other_user_id = owner_user_id + 999
            updated = prepo.update(
                patient_id,
                {
                    "name": "Repo Test Updated",
                    "severity": "Stage 3",
                    "patient_id": "attacker-controlled-id",
                    "record_number": "REC-HACKED",
                    "user_id": other_user_id,
                },
            )

            assert updated is not None
            assert updated.name == "Repo Test Updated"
            assert updated.severity == "Stage 3"
            # Identity/ownership fields must never be settable via update().
            assert updated.patient_id == patient_id
            assert updated.record_number == "REC-TEST-0001"
            assert updated.user_id == owner_user_id
        finally:
            prepo.delete(patient_id)


def test_update_returns_none_for_unknown_patient():
    with SessionLocal() as session:
        prepo = PatientRepository(session)
        assert prepo.update("does-not-exist", {"name": "x"}) is None
