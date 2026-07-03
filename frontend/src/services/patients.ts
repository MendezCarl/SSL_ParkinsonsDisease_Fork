import type { Patient } from '@/types/patient';
import { apiClient } from '@/services/client';
import {
  type BackendDoctorNoteEntry,
  type BackendLabResultEntry,
  type BackendPatient,
  type BackendPatientCreate,
  type BackendPatientMutationResult,
  type BackendPatientUpdate,
  convertBackendToFrontend,
  convertFrontendToBackend,
  normalizeBirthDate,
  type PatientFormInput,
  type PatientUpdateInput,
} from '@/services/patient-mappers';
import type { ServiceResponse } from '@/services/service-response';

export async function getPatients(skip: number = 0, limit: number = 100): Promise<ServiceResponse<Patient[]>> {
  const response = await apiClient.request<{ patients: BackendPatient[]; total: number }>(`/patients/?skip=${skip}&limit=${limit}`);
  if (response.success && response.data) {
    return { success: true, data: response.data.patients.map(convertBackendToFrontend) };
  }
  return { success: false, error: response.error };
}

export async function getPatient(patientId: string): Promise<ServiceResponse<Patient>> {
  const response = await apiClient.request<{ patient: BackendPatient } | BackendPatient>(`/patients/${patientId}`);
  if (response.success && response.data) {
    const patientData = 'patient' in response.data ? response.data.patient : response.data;
    return { success: true, data: convertBackendToFrontend(patientData) };
  }
  return { success: false, error: response.error };
}

export async function createPatient(patientData: PatientFormInput): Promise<ServiceResponse<Patient>> {
  const backendData: BackendPatientCreate = convertFrontendToBackend(patientData);
  const response = await apiClient.request<BackendPatientMutationResult>('/patients/', {
    method: 'POST',
    body: JSON.stringify(backendData),
  });
  if (response.success && response.data) {
    return getPatient(response.data.patient_id);
  }
  return { success: false, error: response.error };
}

export async function updatePatient(patientId: string, updateData: PatientUpdateInput): Promise<ServiceResponse<Patient>> {
  const backendData: BackendPatientUpdate = {};

  if (updateData.firstName || updateData.lastName) {
    backendData.name = `${updateData.firstName || ''} ${updateData.lastName || ''}`.trim();
  }

  if (updateData.birthDate !== undefined) {
    const normalized = normalizeBirthDate(updateData.birthDate);
    backendData.birthDate = normalized || updateData.birthDate;
  }

  if (updateData.height) {
    const heightStr = updateData.height.replace(/[^\d.]/g, '');
    backendData.height = heightStr || '0';
  }
  if (updateData.weight) {
    const weightStr = updateData.weight.replace(/[^\d.]/g, '');
    backendData.weight = weightStr || '0';
  }
  if (updateData.severity) {
    backendData.severity = updateData.severity;
  }

  const response = await apiClient.request<BackendPatientMutationResult>(`/patients/${patientId}`, {
    method: 'PUT',
    body: JSON.stringify(backendData),
  });

  if (response.success && response.data) {
    return getPatient(response.data.patient_id);
  }
  return { success: false, error: response.error };
}

export async function addPatientLabResult(patientId: string, entry: BackendLabResultEntry): Promise<ServiceResponse<BackendPatientMutationResult>> {
  return apiClient.request<BackendPatientMutationResult>(`/patients/${patientId}/lab-results`, {
    method: 'POST',
    body: JSON.stringify(entry),
  });
}

export async function addPatientDoctorNote(patientId: string, entry: BackendDoctorNoteEntry): Promise<ServiceResponse<BackendPatientMutationResult>> {
  return apiClient.request<BackendPatientMutationResult>(`/patients/${patientId}/doctor-notes`, {
    method: 'POST',
    body: JSON.stringify(entry),
  });
}

export async function deletePatient(patientId: string): Promise<ServiceResponse<boolean>> {
  return apiClient.request<boolean>(`/patients/${patientId}`, { method: 'DELETE' });
}

export async function searchPatients(query: string): Promise<ServiceResponse<Patient[]>> {
  const response = await apiClient.request<{ patients: BackendPatient[]; count: number }>(`/patients/search/${encodeURIComponent(query)}`);
  if (response.success && response.data) {
    return { success: true, data: response.data.patients.map(convertBackendToFrontend) };
  }
  return { success: false, error: response.error };
}

export async function filterPatients(criteria: { minAge?: number; maxAge?: number; severity?: string }): Promise<ServiceResponse<Patient[]>> {
  const backendCriteria: Record<string, unknown> = {};
  if (criteria.minAge !== undefined) backendCriteria.min_age = criteria.minAge;
  if (criteria.maxAge !== undefined) backendCriteria.max_age = criteria.maxAge;
  if (criteria.severity) backendCriteria.severity = criteria.severity;

  const response = await apiClient.request<{ patients: BackendPatient[]; count: number }>('/patients/filter/', {
    method: 'POST',
    body: JSON.stringify(backendCriteria),
  });
  if (response.success && response.data) {
    return { success: true, data: response.data.patients.map(convertBackendToFrontend) };
  }
  return { success: false, error: response.error };
}
