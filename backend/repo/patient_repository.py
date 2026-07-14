# repo/patient_repository.py
from __future__ import annotations
from typing import Optional, List, Dict, Any, Tuple
from datetime import date, datetime, timedelta

from sqlalchemy import func, select, and_, desc, or_
from sqlalchemy.orm import Session

from repo.sql_models import Patient, LabResult, DoctorNote

# Optional: align with your existing schema types if you have them
# from schema.patient_schema import PatientSearchResponse, FilterCriteria
# To avoid tight coupling here, we’ll type these as Dict/list where needed.


class PatientRepository:
    # Mass-assignment guard: only these columns may be patched via update().
    # patient_id/record_number/user_id are identity/ownership fields and must
    # never be settable from an arbitrary update payload.
    _UPDATABLE_FIELDS = {"name", "dob", "height", "weight", "severity"}

    def __init__(self, session: Session) -> None:
        self.session = session

    # ---------------- Patient CRUD ----------------
    def get(self, patient_id: str) -> Optional[Patient]:
        return self.session.get(Patient, patient_id)

    def add(self, patient: Patient) -> Patient:
        self.session.add(patient)
        self.session.commit()
        return patient

    def update(self, patient_id: str, update_data: Dict[str, Any]) -> Optional[Patient]:
        patient = self.get(patient_id)
        if patient is None:
            return None
        for key, value in update_data.items():
            if key in self._UPDATABLE_FIELDS:
                setattr(patient, key, value)
        self.session.commit()
        return patient

    def delete(self, patient_id: str) -> bool:
        patient = self.get(patient_id)
        if patient is None:
            return False
        self.session.delete(patient)
        self.session.commit()
        return True

    def list(self, skip: int = 0, limit: int = 100) -> List[Patient]:
        return (
            self.session.query(Patient)
            .order_by(Patient.name.asc().nulls_last())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def count(self) -> int:
        return self.session.query(Patient).count()

    #----------------- Add Lab Results & Doctor Notes ----------------
    def add_lab_result(
        self,
        lab_id: str,
        patient_id: str,
        result_date: date | None,
        results: str | None,
        added_by:str | None,
    ) -> LabResult:
        lr = LabResult(
            lab_id=lab_id,
            patient_id=patient_id,
            result_date=result_date,
            results=results,
            added_by=added_by
        )
        self.session.add(lr)
        self.session.commit()
        self.session.refresh(lr)
        return lr
    
    def list_lab_results(self, patient_id: str) -> List[LabResult]:
        return (
            self.session.query(LabResult)
            .filter(LabResult.patient_id == patient_id)
            .order_by(LabResult.result_date.asc().nulls_last())
            .all()
        )
    
    def add_doctor_note(
        self,
        note_id: str,
        patient_id: str,
        note_date: Optional[date],
        note: Optional[str],
        added_by: Optional[str],
    ) -> DoctorNote:
        doc_note = DoctorNote(
            note_id=note_id,
            patient_id=patient_id,
            note_date=note_date,
            note=note,
            added_by=added_by,
        )
        self.session.add(doc_note)
        self.session.commit()
        return doc_note
    
    def list_doctor_notes(self, patient_id: str) -> List[DoctorNote]:
        return (
            self.session.query(DoctorNote)
            .filter(DoctorNote.patient_id == patient_id)
            .order_by(DoctorNote.note_date.asc().nulls_last())
            .all()
        )

    # ---------------- Search & Filter ----------------
    def search_by_name(self, query_str: str) -> List[Patient]:
        like = f"%{query_str}%"
        return (
            self.session.query(Patient)
            .filter(
                or_(
                    Patient.name.ilike(like),
                    Patient.record_number.ilike(like),
                )
            )
            .order_by(Patient.name.asc())
            .all()
        )

    def filter_patients(
        self,
        name: Optional[str] = None,
        min_age: Optional[int] = None,
        max_age: Optional[int] = None,
        severity: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Patient]:
        q = self.session.query(Patient)

        if name:
            q = q.filter(Patient.name.ilike(f"%{name}%"))

        # Age filters based on dob
        today = date.today()
        if min_age is not None:
            cutoff = today - timedelta(days=int(min_age * 365.25))
            q = q.filter(Patient.dob <= cutoff)
        if max_age is not None:
            cutoff = today - timedelta(days=int(max_age * 365.25))
            q = q.filter(Patient.dob >= cutoff)

        if severity:
            q = q.filter(Patient.severity == severity)

        return (
            q.order_by(Patient.name.asc().nulls_last())
            .offset(skip)
            .limit(limit)
            .all()
        )
