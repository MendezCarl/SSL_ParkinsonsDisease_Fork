from typing import List, Optional, Dict, Any, Union
from pydantic import BaseModel, Field, field_validator
import json, re
from datetime import datetime, date
from pydantic import ConfigDict  # v2


_num = re.compile(r"(\d+\.?\d*)")

class LabResultIn(BaseModel):
    id: Optional[str] = None
    date: Optional[datetime] = None
    results: Optional[str] = None
    added_by: Optional[str] = None


class DoctorNoteIn(BaseModel):
    id: Optional[str] = None
    date: Optional[datetime] = None
    note: str = ""
    added_by: Optional[str] = None


class LabResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    lab_id: str = Field(serialization_alias="id")  # ORM attr; frontend sees "id"
    date: Optional[datetime] = Field(None, validation_alias="result_date", serialization_alias="date")
    results: Optional[str] = None
    added_by: Optional[str] = None


class DoctorNoteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    note_id: str = Field(serialization_alias="id")
    date: Optional[datetime] = Field(None, validation_alias="note_date", serialization_alias="date")
    note: str = ""
    added_by: Optional[str] = None

class PatientCreate(BaseModel):
    name: str
    age: int
    birthDate: date
    height: Optional[Union[float, str]] = None
    weight: Optional[Union[float, str]] = None
    lab_results_history: List[LabResultIn] = Field(default_factory=list)
    doctors_notes_history: List[DoctorNoteIn] = Field(default_factory=list)
    severity: str

    @field_validator("height", "weight", mode="before")
    @classmethod
    def _to_float(cls, v):
        if v is None:
            return None
        if isinstance(v, (int, float)):
            return float(v)
        m = _num.search(str(v))
        return float(m.group(1)) if m else None
    
    

class PatientUpdate(BaseModel):
    name: Optional[str] = None
    birthDate: Optional[date] = None
    height: Optional[Union[float, str]] = None
    weight: Optional[Union[float, str]] = None
    severity: Optional[str] = None

    @field_validator("height", "weight", mode="before")
    @classmethod
    def _to_float(cls, v):
        if v is None:
            return None
        if isinstance(v, (int, float)):
            return float(v)
        m = _num.search(str(v))
        return float(m.group(1)) if m else None



class PatientResponse(BaseModel):
    patient_id: str
    name: str
    birthDate: datetime
    height: str
    weight: str
    severity: str
    latest_lab_result: Optional[LabResultOut] = None
    latest_doctor_note: Optional[DoctorNoteOut] = None  # <-- singular
    lab_results_history: List[LabResultOut] = []
    doctors_notes_history: List[DoctorNoteOut] = []


class PatientsListResponse(BaseModel):
    success: bool
    patients: List[PatientResponse]
    total: int
    skip: int
    limit: int

class PatientSearchResponse(BaseModel):
    success: bool
    patients: List[PatientResponse]
    count: int

class FilterCriteria(BaseModel):
    # Keep age filters if you want; you’ll compute DOB cutoffs server-side
    min_age: Optional[int] = None
    max_age: Optional[int] = None
    severity: Optional[str] 


class PatientMutationResponse(BaseModel):
    success: bool
    patient_id: str
