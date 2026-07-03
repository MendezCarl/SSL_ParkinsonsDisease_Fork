from pydantic import BaseModel, Field
from datetime import datetime,date
from typing import Dict, List, Optional

class VisitBase(BaseModel):
    patient_id: str
    visit_date: datetime
    progression_note: Optional[str] = None
    doctor_notes: Optional[str] = None
    vitals_json: Optional[Dict] = None
    status: Optional[str] = "closed"

class VisitCreate(VisitBase):
    pass 

class VisitUpdate(BaseModel):
    progression_note: Optional[str] = None
    doctor_notes: Optional[str] = None
    vitals_json: Optional[Dict] = None
    status: Optional[str] = None

class VisitResponse(VisitBase):
    visit_id: int

    class Config:
        orm_mode = True

class VisitsListResponse(BaseModel):
    success: bool
    visits: List[VisitResponse]
    total: int
    skip: int
    limit: int

