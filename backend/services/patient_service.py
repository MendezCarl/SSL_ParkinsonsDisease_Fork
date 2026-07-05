from __future__ import annotations

from typing import Any, Dict

from patient_manager import (
    async_add_patient_doctor_note,
    async_add_patient_lab_result,
    async_create_patient,
    async_delete_patient_record,
    async_filter_patients,
    async_get_all_patients_info,
    async_get_patient_info,
    async_import_patients_csv_text,
    async_search_patients,
    async_update_patient_info,
)


async def create_patient(*args, **kwargs) -> Dict[str, Any]:
    return await async_create_patient(*args, **kwargs)


async def get_patient(patient_id: str) -> Dict[str, Any]:
    return await async_get_patient_info(patient_id)


async def list_patients(skip: int, limit: int) -> Dict[str, Any]:
    return await async_get_all_patients_info(skip, limit)


async def update_patient(patient_id: str, updated_data) -> Dict[str, Any]:
    return await async_update_patient_info(patient_id, updated_data)


async def add_lab_result(patient_id: str, lab_result) -> Dict[str, Any]:
    return await async_add_patient_lab_result(patient_id, lab_result)


async def add_doctor_note(patient_id: str, doctor_note) -> Dict[str, Any]:
    return await async_add_patient_doctor_note(patient_id, doctor_note)


async def delete_patient(patient_id: str) -> Dict[str, Any]:
    return await async_delete_patient_record(patient_id)


async def search_patients(query: str) -> Dict[str, Any]:
    return await async_search_patients(query)


async def filter_patients(criteria: Dict[str, Any]) -> Dict[str, Any]:
    return await async_filter_patients(criteria)


async def import_patients_csv_text(csv_text: str) -> Dict[str, Any]:
    return await async_import_patients_csv_text(csv_text)
