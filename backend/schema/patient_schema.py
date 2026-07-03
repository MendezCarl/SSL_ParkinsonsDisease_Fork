from datetime import date
from typing import List, Optional
from pydantic import BaseModel, ConfigDict

class PatientBase(BaseModel):
    name: Optional[str] = None
    dob: Optional[date] = None
    height: Optional[int] = None
    weight: Optional[int] = None

class PatientCreate(PatientBase):
    patient_id: str

class PatientUpdate(PatientBase):
    pass

class PatientResponse(PatientBase):
    patient_id: str
    # Pydantic v2 replacement for orm_mode=True
    model_config = ConfigDict(from_attributes=True)

class PatientsListResponse(BaseModel):
    success: bool = True          # <- default so you don't have to include it
    patients: List[PatientResponse]
    total: int
    skip: int
    limit: int

class PatientSearchResponse(BaseModel):
    success: bool = True
    patients: List[PatientResponse]
    count: int

class FilterCriteria(BaseModel):
    min_age: Optional[int] = None
    max_age: Optional[int] = None
    severity: Optional[str] = None
