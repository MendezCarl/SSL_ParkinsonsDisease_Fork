from __future__ import annotations

import asyncio
import os
import re
from datetime import datetime, date
from typing import Any, Dict, List, Optional, Union

import json
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, Session
from fastapi import HTTPException as HttpException
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union
import threading
import copy
from uuid import uuid4

# --- your models & repos ---
from repo.sql_models import Base, Patient, LabResult, DoctorNote  # Visit, TestResult defined there as well
from repo.patient_repository import PatientRepository
from repo.result_repository import TestResultRepository
from routes.contracts import (
    PatientCreate, PatientUpdate,
    PatientResponse, PatientsListResponse,
    PatientSearchResponse, FilterCriteria,
    LabResultOut, DoctorNoteOut, LabResultIn, DoctorNoteIn
)
from storage_paths import APP_DB_PATH, TEST_HISTORY_PATH

# ----------------- DB bootstrap -----------------
DB_URL = os.getenv("DB_URL", f"sqlite:///{APP_DB_PATH.as_posix()}")
engine = create_engine(DB_URL, future=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False, future=True)
Base.metadata.create_all(engine)

RECORD_NUMBER_PREFIX = "REC-"
RECORD_NUMBER_WIDTH = 6


def _format_record_number(sequence: int) -> str:
    return f"{RECORD_NUMBER_PREFIX}{sequence:0{RECORD_NUMBER_WIDTH}d}"


def _parse_record_number(value: str | None) -> int | None:
    if not value:
        return None
    match = re.fullmatch(rf"{re.escape(RECORD_NUMBER_PREFIX)}(\d+)", value)
    if not match:
        return None
    return int(match.group(1))


def _ensure_patient_record_number_schema() -> None:
    with engine.begin() as connection:
        inspector = inspect(connection)
        if "patients" not in inspector.get_table_names():
            return

        columns = {column["name"] for column in inspector.get_columns("patients")}
        if "record_number" not in columns:
            connection.execute(text("ALTER TABLE patients ADD COLUMN record_number VARCHAR(32)"))

        rows = connection.execute(
            text("SELECT patient_id, record_number FROM patients ORDER BY rowid")
        ).mappings().all()

        next_sequence = max((_parse_record_number(row["record_number"]) or 0) for row in rows) + 1 if rows else 1

        for row in rows:
            if row["record_number"]:
                continue
            connection.execute(
                text("UPDATE patients SET record_number = :record_number WHERE patient_id = :patient_id"),
                {
                    "record_number": _format_record_number(next_sequence),
                    "patient_id": row["patient_id"],
                },
            )
            next_sequence += 1

        indexes = {index["name"] for index in inspect(connection).get_indexes("patients")}
        if "ix_patients_record_number_unique" not in indexes:
            connection.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS ix_patients_record_number_unique "
                    "ON patients (record_number)"
                )
            )


_ensure_patient_record_number_schema()

# ----------------- Helpers -----------------
_NUM_RE = re.compile(r"(\d+\.?\d*)")
_async_lock = asyncio.Lock()

def _parse_number(value, lo: float, hi: float) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        x = float(value)
    else:
        m = _NUM_RE.search(str(value))
        if not m:
            return None
        x = float(m.group(1))
    if not (lo <= x <= hi):
        return None
    return x

def _gen_patient_id(name: str) -> str:
    base = (name or "").lower().replace(" ", "")[:5] or "pt"
    return f"{base}{int(datetime.now().timestamp())}"


def _next_record_number(session: Session) -> str:
    existing = session.query(Patient.record_number).filter(Patient.record_number.is_not(None)).all()
    next_sequence = max((_parse_record_number(value) or 0) for (value,) in existing) + 1 if existing else 1
    return _format_record_number(next_sequence)


def _gen_entry_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"

def _validate(data: Dict[str, Any]) -> Dict[str, str]:
    errors: Dict[str, str] = {}

    if "name" in data and data["name"] is not None and not isinstance(data["name"], str):
        errors["name"] = "Name must be a string"

    if "birthDate" in data:
        bd = data["birthDate"]
        if bd:
            try:
                date.fromisoformat(str(bd))
            except Exception:
                errors["birthDate"] = "birthDate must be YYYY-MM-DD"

    if "height" in data and _parse_number(data["height"], 0, 300) is None:
        errors["height"] = "Height must be a number between 0 and 300 (cm)"

    if "weight" in data and _parse_number(data["weight"], 0, 500) is None:
        errors["weight"] = "Weight must be a number between 0 and 500 (kg)"

    if "severity" in data:
        s = str(data["severity"]).strip()
        if s.lower() in {"low", "medium", "high"} or re.fullmatch(r"Stage [1-5]", s):
            pass

_TEST_NAME_ALIASES = {
    "stand-and-sit": "stand-and-sit",
    "stand-sit": "stand-and-sit",
    "stand_to_sit": "stand-and-sit",
    "stand-and-sit-assessment": "stand-and-sit",
    "stand-and-sit-test": "stand-and-sit",
    "stand-&-sit": "stand-and-sit",
    "stand-&-sit-assessment": "stand-and-sit",
    "stand-and-sit-evaluation": "stand-and-sit",
    "finger-tapping": "finger-tapping",
    "finger_tapping": "finger-tapping",
    "finger-taping": "finger-tapping",
    "finger-tapping-test": "finger-tapping",
    "finger-tapping-assessment": "finger-tapping",
    "finger-tap": "finger-tapping",
    "fist-open-close": "fist-open-close",
    "fist_open_close": "fist-open-close",
    "fist-open-close-test": "fist-open-close",
    "fist-open-close-assessment": "fist-open-close",
    "palm-open": "fist-open-close",
    "palm_open": "fist-open-close",
}


def _normalize_test_name(value: Optional[str]) -> str:
    normalized = (value or "").strip().lower()
    if not normalized:
        return "unknown"
    normalized = normalized.replace(" ", "-").replace("_", "-").replace("&", "and")
    while "--" in normalized:
        normalized = normalized.replace("--", "-")
    return _TEST_NAME_ALIASES.get(normalized, normalized)


def normalize_severity(value: str) -> str:
    """Map various severity descriptors to a canonical Stage 1-5 label."""
    if not value:
        return "Stage 1"

    normalized = value.strip().lower()

    stage_map = {
        "stage 1": "Stage 1",
        "stage 2": "Stage 2",
        "stage 3": "Stage 3",
        "stage 4": "Stage 4",
        "stage 5": "Stage 5",
    }

    if normalized in stage_map:
        return stage_map[normalized]

    legacy_map = {
        "low": "Stage 1",
        "mild": "Stage 2",
        "medium": "Stage 3",
        "moderate": "Stage 3",
        "high": "Stage 4",
        "severe": "Stage 5",
    }

    return legacy_map.get(normalized, "Stage 1")

def _patient_to_api_dict(session: Session, p: Patient) -> PatientResponse:
    prepo = PatientRepository(session)
    labs = sorted(
        prepo.list_lab_results(p.patient_id),
        key=lambda r: (r.result_date or date.min, r.lab_id),
    )
    notes = sorted(
        prepo.list_doctor_notes(p.patient_id),
        key=lambda n: (n.note_date or date.min, n.note_id),
    )

    latest_lr = LabResultOut.model_validate(labs[-1]) if labs else None
    latest_dn = DoctorNoteOut.model_validate(notes[-1]) if notes else None

    return PatientResponse(
        patient_id=p.patient_id,
        recordNumber=p.record_number or "",
        name=p.name or "",
        birthDate=p.dob,  # or adjust type to date if you prefer
        height=str(p.height or 0),
        weight=str(p.weight or 0),
        severity=p.severity or "",
        latest_lab_result=latest_lr,
        latest_doctor_note=latest_dn,
        lab_results_history=[LabResultOut.model_validate(x) for x in labs],
        doctors_notes_history=[DoctorNoteOut.model_validate(x) for x in notes],
    )


def create_patient(
    name: str,
    age: int,
    birthDate: Union[str, date],
    height: Optional[float],
    weight: Optional[float],
    lab_results_history: Optional[List[LabResultOut]] = None,
    doctors_notes_history: Optional[List[DoctorNoteOut]] = None,
    severity: str = "",
) -> Dict[str, Any]:
    errs = _validate({
        "birthDate": birthDate,
        "height": height,
        "weight": weight,
        "severity": severity,
    })
    if errs:
        return {"success": False, "errors": errs}

    try:
        dob = birthDate if isinstance(birthDate, date) else date.fromisoformat(str(birthDate))
    except Exception:
        return {"success": False, "error": "Invalid birthDate; expected YYYY-MM-DD"}

    h = _parse_number(height, 0, 300)
    w = _parse_number(weight, 0, 500)

    # coerce lab_results to a plain string value
    patient_id = _gen_patient_id(name)

    try:
        with SessionLocal() as session:
            prepo = PatientRepository(session)
            record_number = _next_record_number(session)

            dbp = Patient(
                patient_id=patient_id,
                record_number=record_number,
                user_id=123,
                name=name,
                dob=dob,
                height=int(h) if h is not None else None,
                weight=int(w) if w is not None else None,
                severity=severity,
            )
            prepo.add(dbp)

            for lr in lab_results_history or []:
                prepo.add_lab_result(
                    lab_id=lr.id,
                    patient_id=patient_id,
                    result_date=lr.date or datetime.now(),
                    results=lr.results or "",
                    added_by=lr.added_by or "system"   
                )

            # persist all doctor notes in history (if any)
            for dn in doctors_notes_history or []:
                prepo.add_doctor_note(
                    note_id=dn.id,
                    patient_id=patient_id,
                    note_date=dn.date or datetime.now(),
                    note=dn.note or "",
                    added_by=dn.added_by or "system",
                )

            return {"success": True, "patient_id": patient_id}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_patient_info(patient_id: str) -> Dict[str, Any]:
    with SessionLocal() as session:
        prepo = PatientRepository(session)
        dbp = prepo.get(patient_id)
        if not dbp:
            return {"success": False, "error": "Patient not found"}
        return {"success": True, "patient": _patient_to_api_dict(session, dbp)}

def get_all_patients_info(skip: int = 0, limit: int = 100) -> Dict[str, Any]:
    with SessionLocal() as session:
        prepo = PatientRepository(session)
        rows = prepo.list(skip=skip, limit=limit)
        total = prepo.count()
        return {
            "success": True,
            "patients": [_patient_to_api_dict(session, r) for r in rows],
            "total": total,
            "skip": skip,
            "limit": limit,
        }
    

def _extract_lab_result_value(v: Any) -> Optional[str]:
    """Return only the textual value to persist into Visit.lab_result (Text)."""
    if v is None:
        return None
    if isinstance(v, dict):
        # Keep only the 'value' field if provided, otherwise stringify the dict
        return v.get("value", str(v))
    if isinstance(v, str):
        return v
    return str(v)

def update_patient_info(patient_id: str, updated_data: PatientUpdate) -> Dict[str, Any]:
    # Turn model into a partial dict
    data = updated_data.model_dump(exclude_unset=True)

    errs = _validate(data)  # or skip this if _validate expects full objects only
    if errs:
        return {"success": False, "errors": errs}

    with SessionLocal() as session:
        prepo = PatientRepository(session)

        dbp = prepo.get(patient_id)
        if not dbp:
            return {"success": False, "error": "Patient not found"}

        # --- Patch basic Patient columns ---
        if "name" in data:
            dbp.name = data["name"]

        if "birthDate" in data:
            dbp.dob = data["birthDate"]

        if "height" in data:
            h = _parse_number(data["height"], 0, 300)
            dbp.height = int(h) if h is not None else None

        if "weight" in data:
            w = _parse_number(data["weight"], 0, 500)
            dbp.weight = int(w) if w is not None else None

        if "severity" in data:
            dbp.severity = data["severity"]

        session.commit()
        return {"success": True, "patient_id": patient_id}


def add_patient_lab_result(patient_id: str, lab_result: LabResultIn) -> Dict[str, Any]:
    with SessionLocal() as session:
        prepo = PatientRepository(session)
        dbp = prepo.get(patient_id)
        if not dbp:
            return {"success": False, "error": "Patient not found"}

        prepo.add_lab_result(
            lab_id=lab_result.id or _gen_entry_id("lab"),
            patient_id=patient_id,
            result_date=lab_result.date or datetime.now(),
            results=lab_result.results or "",
            added_by=lab_result.added_by or "system",
        )
        return {"success": True, "patient_id": patient_id}


def add_patient_doctor_note(patient_id: str, doctor_note: DoctorNoteIn) -> Dict[str, Any]:
    with SessionLocal() as session:
        prepo = PatientRepository(session)
        dbp = prepo.get(patient_id)
        if not dbp:
            return {"success": False, "error": "Patient not found"}

        prepo.add_doctor_note(
            note_id=doctor_note.id or _gen_entry_id("note"),
            patient_id=patient_id,
            note_date=doctor_note.date or datetime.now(),
            note=doctor_note.note or "",
            added_by=doctor_note.added_by or "system",
        )
        return {"success": True, "patient_id": patient_id}

def delete_patient_record(patient_id: str) -> Dict[str, Any]:
    with SessionLocal() as session:
        prepo = PatientRepository(session)
        ok = prepo.delete(patient_id)
        return {"success": ok} if ok else {"success": False, "error": "Patient not found"}

def search_patients(query: str) -> Dict[str, Any]:
    with SessionLocal() as session:
        prepo = PatientRepository(session)
        if hasattr(prepo, "search_by_name"):
            rows = prepo.search_by_name(query)
        else:
            rows = prepo.list()
            q = query.lower()
            rows = [
                p for p in rows
                if q in (p.name or "").lower() or q in (p.record_number or "").lower()
            ]
        return {"success": True, "patients": [_patient_to_api_dict(session, r) for r in rows], "count": len(rows)}

def filter_patients(criteria: Dict[str, Any]) -> Dict[str, Any]:
    """
    Supports: name, min_age, max_age, severity (severity via latest visit.vitals_json).
    """
    with SessionLocal() as session:
        prepo = PatientRepository(session)

        # If your repo exposes a richer filter, prefer it:
        if hasattr(prepo, "filter_patients"):
            rows = prepo.filter_patients(
                name=criteria.get("name"),
                min_age=criteria.get("min_age"),
                max_age=criteria.get("max_age"),
                severity=criteria.get("severity"),
                skip=criteria.get("skip", 0),
                limit=criteria.get("limit", 100),
            )
        else:
            # Minimal fallback: list + name filter (age/severity omitted if repo lacks it)
            rows = prepo.list(skip=criteria.get("skip", 0), limit=criteria.get("limit", 100))
            if criteria.get("name"):
                q = criteria["name"].lower()
                rows = [p for p in rows if (p.name or "").lower().find(q) >= 0]



        return {"success": True, "patients": [_patient_to_api_dict(session, r) for r in rows], "count": len(rows)}

# ---------------- Async wrappers (same names) ----------------
async def async_create_patient(*args, **kwargs) -> Dict[str, Any]:
    async with _async_lock:
        return create_patient(*args, **kwargs)

async def async_get_patient_info(patient_id: str) -> Dict[str, Any]:
    async with _async_lock:
        return get_patient_info(patient_id)

async def async_get_all_patients_info(skip: int = 0, limit: int = 100) -> Dict[str, Any]:
    async with _async_lock:
        return get_all_patients_info(skip=skip, limit=limit)

async def async_update_patient_info(patient_id: str, updated_data: PatientUpdate) -> Dict[str, Any]:
    async with _async_lock:
        return update_patient_info(patient_id, updated_data)


async def async_add_patient_lab_result(patient_id: str, lab_result: LabResultIn) -> Dict[str, Any]:
    async with _async_lock:
        return add_patient_lab_result(patient_id, lab_result)


async def async_add_patient_doctor_note(patient_id: str, doctor_note: DoctorNoteIn) -> Dict[str, Any]:
    async with _async_lock:
        return add_patient_doctor_note(patient_id, doctor_note)

async def async_delete_patient_record(patient_id: str) -> Dict[str, Any]:
    async with _async_lock:
        return delete_patient_record(patient_id)

async def async_search_patients(query: str) -> Dict[str, Any]:
    async with _async_lock:
        return search_patients(query)

async def async_filter_patients(criteria: Dict[str, Any]) -> Dict[str, Any]:
    async with _async_lock:
        return filter_patients(criteria)


# =========================
# TestHistoryManager refactor -> SQL TestResultRepository
# =========================
TEST_HISTORY_FILE = str(TEST_HISTORY_PATH)

class TestHistoryManager:
    _lock = threading.Lock()

    def __init__(self, file_path: str = TEST_HISTORY_FILE):
        self.file_path = file_path
        self._load()

    def _load(self):
        if os.path.exists(self.file_path):
            with open(self.file_path, 'r') as f:
                self.data = json.load(f)
        else:
            self.data = {}

    def _save(self):
        with open(self.file_path, 'w') as f:
            json.dump(self.data, f, indent=2)

    def get_patient_tests(self, patient_id: str):
        return self.data.get(patient_id, [])

    def add_patient_test(self, patient_id: str, test_data: dict):
        with self._lock:
            self._load()
            if patient_id not in self.data:
                self.data[patient_id] = []
            self.data[patient_id].append(test_data)
            self._save()

    def get_all_tests(self):
        return self.data
