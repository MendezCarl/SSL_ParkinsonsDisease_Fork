from __future__ import annotations

import asyncio
import csv
import os
import re
from datetime import datetime, date
from io import StringIO
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
from schema.patient_contracts import (
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
    return f"{base}{uuid4().hex[:8]}"


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
        if s and not (s.lower() in {"low", "medium", "high"} or re.fullmatch(r"Stage [1-5]", s)):
            errors["severity"] = "Severity must be low, medium, high, or Stage 1-5"

    return errors

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

    if re.fullmatch(r"[1-5]", normalized):
        return f"Stage {normalized}"

    match = re.fullmatch(r"stage[_\-\s]*([1-5])", normalized)
    if match:
        return f"Stage {match.group(1)}"

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


def _normalize_csv_header_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (value or "").lower()).strip()


def _csv_header_to_key(header: str) -> str | None:
    normalized = _normalize_csv_header_name(header)

    if normalized in {"firstname", "first", "givenname", "given"}:
        return "firstName"
    if normalized in {"lastname", "last", "surname", "familyname"}:
        return "lastName"
    if normalized in {"fullname", "name"}:
        return "fullName"
    if normalized in {"birthdate", "dob", "dateofbirth", "birth"}:
        return "birthDate"
    if normalized in {"height", "ht"}:
        return "height"
    if normalized in {"weight", "wt"}:
        return "weight"
    if normalized in {"recordnumber", "recordno", "record", "id", "patientid"}:
        return "recordNumber"
    if normalized in {"severity", "stage", "parkinsonseverity"}:
        return "severity"
    if normalized in {"labresults", "labresult", "labs", "lab"}:
        return "labResults"
    if normalized in {"doctornotes", "doctornote", "notes", "note"}:
        return "doctorNotes"
    if normalized in {"physician", "primaryphysician", "doctor", "addedby", "provider"}:
        return "addedBy"
    return None


def _parse_csv_birth_date(value: str) -> str | None:
    if not value:
        return None

    candidate = value.strip()
    if not candidate:
        return None

    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", candidate):
        return candidate

    match = re.fullmatch(r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})", candidate)
    if match:
        a = int(match.group(1))
        b = int(match.group(2))
        year = int(match.group(3))

        if a > 12:
            day, month = a, b
        elif b > 12:
            month, day = a, b
        elif "/" in candidate:
            month, day = a, b
        else:
            day, month = a, b

        if 1 <= month <= 12 and 1 <= day <= 31:
            return f"{year}-{month:02d}-{day:02d}"

    try:
        return datetime.fromisoformat(candidate).date().isoformat()
    except ValueError:
        pass

    try:
        parsed = datetime.strptime(candidate, "%b %d, %Y")
        return parsed.date().isoformat()
    except ValueError:
        return None


def _calculate_age_from_birth_date(value: str) -> int:
    try:
        dob = date.fromisoformat(value)
    except ValueError:
        return 0

    today = date.today()
    age = today.year - dob.year
    if (today.month, today.day) < (dob.month, dob.day):
        age -= 1
    return max(age, 0)


def import_patients_csv_text(csv_text: str) -> Dict[str, Any]:
    if not csv_text or not csv_text.strip():
        raise ValueError("CSV file is empty")

    reader = csv.DictReader(StringIO(csv_text))
    if not reader.fieldnames:
        raise ValueError("CSV must contain a header row")

    header_map = {
        header: _csv_header_to_key(header)
        for header in reader.fieldnames
        if header is not None
    }
    recognized_headers = {mapped for mapped in header_map.values() if mapped}
    if not recognized_headers:
        raise ValueError("CSV does not contain any recognized patient columns")

    result: Dict[str, Any] = {
        "success": True,
        "success_count": 0,
        "failure_count": 0,
        "imported_patient_ids": [],
        "errors": [],
    }

    has_data_rows = False
    for row_number, row in enumerate(reader, start=2):
        raw_row = {
            str(key).strip(): (value or "").strip()
            for key, value in row.items()
            if key is not None
        }
        if not any(raw_row.values()):
            continue

        has_data_rows = True
        normalized_row: Dict[str, str] = {
            "firstName": "",
            "lastName": "",
            "fullName": "",
            "birthDate": "",
            "height": "",
            "weight": "",
            "severity": "",
            "labResults": "",
            "doctorNotes": "",
            "addedBy": "",
        }

        for header, raw_value in raw_row.items():
            mapped_key = header_map.get(header)
            if mapped_key:
                normalized_row[mapped_key] = raw_value

        if normalized_row["fullName"] and not (normalized_row["firstName"] or normalized_row["lastName"]):
            parts = normalized_row["fullName"].split()
            normalized_row["firstName"] = parts[0] if parts else ""
            normalized_row["lastName"] = " ".join(parts[1:]) if len(parts) > 1 else ""

        birth_date = _parse_csv_birth_date(normalized_row["birthDate"]) or normalized_row["birthDate"]
        height = normalized_row["height"] or "170 cm"
        weight = normalized_row["weight"] or "70 kg"
        severity = normalize_severity(normalized_row["severity"])
        added_by = normalized_row["addedBy"] or "Unknown"
        full_name = f"{normalized_row['firstName']} {normalized_row['lastName']}".strip() or "Unknown Patient"

        lab_results_history = []
        if normalized_row["labResults"]:
            lab_results_history.append(
                LabResultIn(
                    id=_gen_entry_id("lab"),
                    date=datetime.now(),
                    results=normalized_row["labResults"],
                    added_by=added_by,
                )
            )

        doctors_notes_history = []
        if normalized_row["doctorNotes"]:
            doctors_notes_history.append(
                DoctorNoteIn(
                    id=_gen_entry_id("note"),
                    date=datetime.now(),
                    note=normalized_row["doctorNotes"],
                    added_by=added_by,
                )
            )

        create_result = create_patient(
            name=full_name,
            age=_calculate_age_from_birth_date(birth_date),
            birthDate=birth_date,
            height=height,
            weight=weight,
            lab_results_history=lab_results_history,
            doctors_notes_history=doctors_notes_history,
            severity=severity,
        )

        if create_result.get("success"):
            result["success_count"] += 1
            result["imported_patient_ids"].append(create_result["patient_id"])
            continue

        result["failure_count"] += 1
        result["errors"].append(
            {
                "row": row_number,
                "errors": create_result.get("errors") or {},
                "error": create_result.get("error"),
                "raw": raw_row,
            }
        )

    if not has_data_rows:
        raise ValueError("CSV must contain at least one data row")

    return result

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
        severity=normalize_severity(p.severity or ""),
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

    severity = normalize_severity(severity)

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
            dbp.severity = normalize_severity(data["severity"])

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


async def async_import_patients_csv_text(csv_text: str) -> Dict[str, Any]:
    async with _async_lock:
        return import_patients_csv_text(csv_text)


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
