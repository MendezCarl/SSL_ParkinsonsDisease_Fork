import io
import json
import pandas as pd
from fastapi import HTTPException
from sqlalchemy.orm import Session
from datetime import datetime, date

from repo.sql_models import Patient, Visit, TestResult

class ExcelToRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def load_workbook_from_bytes(self, data: bytes) -> pd.ExcelFile:
        """
        Convert uploaded bytes into a pandas ExcelFile. Raise HTTPException if unreadable.
        """
        try:
            return pd.ExcelFile(io.BytesIO(data))
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Invalid Excel file: {exc}")

    def import_patients(self, wb: pd.ExcelFile) -> None:
        """
        Read the 'patients' sheet and upsert Patient records.
        Expected columns: patient_id, name, dob, height, weight
        """
        if "patients" not in wb.sheet_names:
            return
        df = wb.parse("patients")
        for _, row in df.iterrows():
            patient = Patient(
                patient_id=row["patient_id"],
                name=row.get("name"),
                dob=row.get("dob"),
                height=row.get("height"),
                weight=row.get("weight"),
            )
            self.session.merge(patient)
        self.session.commit()

    def import_visits(self, wb: pd.ExcelFile) -> None:
        """
        Read the 'visits' sheet and insert Visit records.
        Expected columns: visit_id, patient_id, visit_date, progression_note,
                          doctor_notes, vitals_json, status
        """
        if "visits" not in wb.sheet_names:
            return
        df = wb.parse("visits")
        for _, row in df.iterrows():
            visit_date = row["visit_date"]
            if isinstance(visit_date, str):
                visit_date = datetime.fromisoformat(visit_date)
            vitals = row.get("vitals_json")
            if isinstance(vitals, str):
                try:
                    vitals = json.loads(vitals)
                except json.JSONDecodeError:
                    vitals = None
            visit = Visit(
                visit_id=row["visit_id"],
                patient_id=row["patient_id"],
                visit_date=visit_date,
                progression_note=row.get("progression_note"),
                doctor_notes=row.get("doctor_notes"),
                vitals_json=vitals,
                status=row.get("status", "closed"),
            )
            self.session.add(visit)
        self.session.commit()

    def import_testresults(self, wb: pd.ExcelFile) -> None:
        """
        Read the 'testresults' sheet and insert TestResult records.
        Expected columns: test_id, patient_id, test_type, test_date, keypoints
        """
        if "testresults" not in wb.sheet_names:
            return
        df = wb.parse("testresults")
        for _, row in df.iterrows():
            test_date = row.get("test_date")
            if isinstance(test_date, str):
                test_date = datetime.fromisoformat(test_date).date()
            test = TestResult(
                test_id=row["test_id"],
                patient_id=row["patient_id"],
                test_type=row.get("test_type"),
                test_date=test_date,
                keypoints=row.get("keypoints"),
            )
            self.session.add(test)
        self.session.commit()

    def import_workbook(self, wb: pd.ExcelFile) -> None:
        """
        Orchestrate the import for all relevant sheets.
        """
        self.import_patients(wb)
        self.import_visits(wb)
        self.import_testresults(wb)