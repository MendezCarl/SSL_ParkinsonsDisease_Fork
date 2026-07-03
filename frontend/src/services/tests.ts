import type { Test } from '@/types/patient';
import { API_BASE_URL, apiClient } from '@/services/client';
import { type BackendTestEntry, convertBackendTestToFrontend } from '@/services/patient-mappers';
import type { ServiceResponse } from '@/services/service-response';

export async function getPatientTests(patientId: string): Promise<ServiceResponse<Test[]>> {
  const response = await apiClient.request<{ tests: BackendTestEntry[] } | BackendTestEntry[]>(`/patients/${patientId}/tests`);

  if (response.success && response.data) {
    const payload = response.data;
    const testsRaw = Array.isArray(payload) ? payload : payload.tests ?? [];
    const converted = testsRaw
      .filter(Boolean)
      .map((entry) => convertBackendTestToFrontend(patientId, entry as BackendTestEntry, API_BASE_URL));
    converted.sort((a, b) => b.date.getTime() - a.date.getTime());
    return { success: true, data: converted };
  }

  return { success: false, error: response.error };
}

export async function addPatientTest(patientId: string, testData: unknown): Promise<ServiceResponse<boolean>> {
  return apiClient.request<boolean>(`/patients/${patientId}/tests`, {
    method: 'POST',
    body: JSON.stringify(testData),
    headers: { 'Content-Type': 'application/json' },
  });
}
