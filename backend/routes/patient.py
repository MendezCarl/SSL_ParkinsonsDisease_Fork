from fastapi import APIRouter, Depends, Query, HTTPException

from typing import List, Optional, Dict, Any, Union
from pydantic import BaseModel, Field, field_validator
import json, re
from datetime import datetime, date
from pydantic import ConfigDict  # v2

from patient_manager import (
    async_create_patient, async_get_patient_info,
    async_update_patient_info, async_delete_patient_record,
    async_get_all_patients_info, async_search_patients,
    async_filter_patients, async_add_patient_lab_result,
    async_add_patient_doctor_note,
)

from routes.contracts import (
    PatientCreate, PatientUpdate, LabResultIn, DoctorNoteIn,
    PatientResponse, PatientsListResponse,
    PatientSearchResponse, FilterCriteria,
    PatientMutationResponse,
)

_num = re.compile(r"(\d+\.?\d*)")
# Accept low/medium/high OR Stage 1..5


router = APIRouter(prefix="/patients")


@router.post("/", response_model=PatientMutationResponse)
async def create_patient(patient: PatientCreate):
    result = await async_create_patient(
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
    return await async_get_all_patients_info(skip, limit)

@router.get("/{patient_id}", response_model=PatientResponse)
async def get_patient(patient_id: str):
    result = await async_get_patient_info(patient_id)
    if not result.get("success"):
        raise HTTPException(status_code=404, detail="Patient not found")
    return result["patient"]

@router.put("/{patient_id}", response_model=PatientMutationResponse)
async def update_patient(patient_id: str, patient_update: PatientUpdate):
    result = await async_update_patient_info(patient_id, patient_update)
    if not result.get("success"):
        if "errors" in result:
            raise HTTPException(status_code=400, detail=result["errors"])
        raise HTTPException(status_code=404, detail=result.get("error", "Failed to update patient"))
    return result


@router.post("/{patient_id}/lab-results", response_model=PatientMutationResponse)
async def add_lab_result(patient_id: str, lab_result: LabResultIn):
    result = await async_add_patient_lab_result(patient_id, lab_result)
    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("error", "Failed to add lab result"))
    return result


@router.post("/{patient_id}/doctor-notes", response_model=PatientMutationResponse)
async def add_doctor_note(patient_id: str, doctor_note: DoctorNoteIn):
    result = await async_add_patient_doctor_note(patient_id, doctor_note)
    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("error", "Failed to add doctor note"))
    return result

@router.delete("/{patient_id}", response_model=Dict)
async def delete_patient(patient_id: str):
    result = await async_delete_patient_record(patient_id)

    if not result.get("success", False):
        raise HTTPException(status_code=404, detail="Patient not found")

    return result

@router.get("/search/{query}", response_model=PatientSearchResponse)
async def search_patients_endpoint(query: str):
    return await async_search_patients(query)

@router.post("/filter/", response_model=PatientSearchResponse)
async def filter_patients_endpoint(criteria: FilterCriteria):
    return await async_filter_patients(criteria.dict(exclude_none=True))
