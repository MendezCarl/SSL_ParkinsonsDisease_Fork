import { apiClient } from '@/services/client';
import type { BackendSeverityPrediction } from '@/services/patient-mappers';
import type { ServiceResponse } from '@/services/service-response';

export async function predictAndUpdateSeverity(
  patientId: string,
  sequence: number[][],
  options?: { returnAttention?: boolean; persistUpdate?: boolean }
): Promise<ServiceResponse<BackendSeverityPrediction>> {
  const returnAttention = options?.returnAttention ?? false;
  const persistUpdate = options?.persistUpdate ?? true;
  const endpoint = `/ml/updrs/predict/patients/${encodeURIComponent(patientId)}?persist_update=${persistUpdate}`;

  return apiClient.request<BackendSeverityPrediction>(endpoint, {
    method: 'POST',
    body: JSON.stringify({
      sequence,
      return_attention: returnAttention,
    }),
  });
}
