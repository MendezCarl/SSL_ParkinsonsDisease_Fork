import { apiClient } from '@/services/client';
import type { ServiceResponse } from '@/services/service-response';

export type AnomalyJobStatus = 'pending' | 'processing' | 'done' | 'failed';

export type AnomalyChunk = {
  start: string;
  end: string;
  confidence: number;
};

export type AnomalyReport = {
  chunks: AnomalyChunk[];
  model_version?: string | null;
  generated_at?: string | null;
};

export type AnomalyJobCreateResponse = {
  job_id: string;
  status: AnomalyJobStatus;
};

export type AnomalyJobStatusResponse = {
  job_id: string;
  status: AnomalyJobStatus;
  result: AnomalyReport | null;
  error: string | null;
};

export async function submitAnomalyJob(
  testKey: string,
  sessionId: string,
  patientId: string
): Promise<ServiceResponse<AnomalyJobCreateResponse>> {
  const query = new URLSearchParams({ patient_id: patientId });
  return apiClient.request<AnomalyJobCreateResponse>(
    `/ml/anomaly/sessions/${encodeURIComponent(testKey)}/${encodeURIComponent(sessionId)}?${query.toString()}`,
    { method: 'POST' }
  );
}

export async function getAnomalyJob(jobId: string): Promise<ServiceResponse<AnomalyJobStatusResponse>> {
  return apiClient.request<AnomalyJobStatusResponse>(`/ml/anomaly/jobs/${encodeURIComponent(jobId)}`);
}
