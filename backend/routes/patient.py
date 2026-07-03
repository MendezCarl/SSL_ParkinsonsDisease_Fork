from fastapi import APIRouter, Query, HTTPException, UploadFile, File

from typing import List, Optional, Dict, Any, Union
from pydantic import BaseModel, Field, field_validator
import json, re
from datetime import datetime, date
from pydantic import ConfigDict  # v2

from services import patient_service

from routes.contracts import (
    PatientCreate, PatientUpdate, LabResultIn, DoctorNoteIn,
    PatientResponse, PatientsListResponse,
    PatientSearchResponse, FilterCriteria,
    PatientMutationResponse, PatientImportResponse,
)

_num = re.compile(r"(\d+\.?\d*)")
# Accept low/medium/high OR Stage 1..5


router = APIRouter(prefix="/patients")


@router.post("/", response_model=PatientMutationResponse)
async def create_patient(patient: PatientCreate):
    result = await patient_service.create_patient(
        name=patient.name,
        age=patient.age,
        birthDate=patient.birthDate,
        height=patient.height,
        weight=patient.weight,
        lab_results_history=patient.lab_results_history or "",
        doctors_notes_history=patient.doctors_notes_history or "",
        severity=patient.severity,
    )

    if not result or not result.get("success"):
        # Prefer detailed errors if present
        detail = result.get("errors") if result and result.get("errors") else result.get("error", "Failed to create patient")
        raise HTTPException(status_code=422 if isinstance(detail, dict) else 400, detail=detail)

    return result

@router.get("/", response_model=PatientsListResponse)
async def get_patients(
        skip: int = Query(0, ge=0),
        limit: int = Query(100, ge=1, le=1000)
):
    return await patient_service.list_patients(skip, limit)


@router.post("/import/csv", response_model=PatientImportResponse)
async def import_patients_csv(file: UploadFile = File(...)):
    filename = (file.filename or "").lower()
    if not filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Please upload a CSV file")

    try:
        contents = await file.read()
        csv_text = contents.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"CSV must be UTF-8 encoded: {exc}") from exc

    try:
        return await patient_service.import_patients_csv_text(csv_text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

@router.get("/{patient_id}", response_model=PatientResponse)
async def get_patient(patient_id: str):
    result = await patient_service.get_patient(patient_id)
    if not result.get("success"):
        raise HTTPException(status_code=404, detail="Patient not found")
    return result["patient"]

@router.put("/{patient_id}", response_model=PatientMutationResponse)
async def update_patient(patient_id: str, patient_update: PatientUpdate):
    result = await patient_service.update_patient(patient_id, patient_update)
    if not result.get("success"):
        if "errors" in result:
            raise HTTPException(status_code=400, detail=result["errors"])
        raise HTTPException(status_code=404, detail=result.get("error", "Failed to update patient"))
    return result


@router.post("/{patient_id}/lab-results", response_model=PatientMutationResponse)
async def add_lab_result(patient_id: str, lab_result: LabResultIn):
    result = await patient_service.add_lab_result(patient_id, lab_result)
    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("error", "Failed to add lab result"))
    return result


@router.post("/{patient_id}/doctor-notes", response_model=PatientMutationResponse)
async def add_doctor_note(patient_id: str, doctor_note: DoctorNoteIn):
    result = await patient_service.add_doctor_note(patient_id, doctor_note)
    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("error", "Failed to add doctor note"))
    return result

@router.delete("/{patient_id}", response_model=Dict)
async def delete_patient(patient_id: str):
    result = await patient_service.delete_patient(patient_id)

    if not result.get("success", False):
        raise HTTPException(status_code=404, detail="Patient not found")

    return result

@router.get("/search/{query}", response_model=PatientSearchResponse)
async def search_patients_endpoint(query: str):
    return await patient_service.search_patients(query)

@router.post("/filter/", response_model=PatientSearchResponse)
async def filter_patients_endpoint(criteria: FilterCriteria):
    return await patient_service.filter_patients(criteria.dict(exclude_none=True))
