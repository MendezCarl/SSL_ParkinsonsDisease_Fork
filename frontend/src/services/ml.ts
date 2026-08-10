import { apiClient } from '@/services/client';
import type { BackendSeverityPrediction } from '@/services/patient-mappers';
import type { ServiceResponse } from '@/services/service-response';

export interface MlModelsResponse {
  video_models: string[];
  anomaly_models: string[];
  default_video_model: string;
  default_anomaly_model: string;
}

export interface AnomalyEmbeddingRequest {
  filename: string;
  embedding: Record<string, unknown>;
  anomaly_model?: string | null;
  persist?: boolean;
  patient_id?: string | null;
  test_result_id?: number | null;
  test_name?: string | null;
  session_id?: string | null;
}

export interface VideoAnomalyRequest {
  video_path: string;
  video_model?: string | null;
  anomaly_model?: string | null;
  persist?: boolean;
  patient_id?: string | null;
  test_result_id?: number | null;
  test_name?: string | null;
  session_id?: string | null;
  review_window_seconds?: number | null;
}

export interface AnomalyReviewWindow {
  start_sec: number;
  end_sec: number;
  predicted_label: 'normal' | 'anomalous';
  anomaly_probability?: number | null;
  anomaly_score?: number | null;
}

export interface AnomalyPredictionResponse {
  filename?: string | null;
  predicted_label: 'normal' | 'anomalous';
  anomaly_probability?: number | null;
  anomaly_score?: number | null;
  anomaly_model: string;
  video_model?: string | null;
  model_version?: string | null;
  model_artifact_path?: string | null;
  prediction_id?: number | null;
  test_result_id?: number | null;
  persisted: boolean;
  review_windows?: AnomalyReviewWindow[];
}

export interface MlPredictionRecord {
  prediction_id: number;
  test_result_id: number;
  patient_id?: string | null;
  session_id?: string | null;
  test_name?: string | null;
  prediction_type: string;
  video_model?: string | null;
  classifier_model?: string | null;
  model_version?: string | null;
  model_artifact_path?: string | null;
  predicted_label: string;
  probability?: number | null;
  score?: number | null;
  input_video_path?: string | null;
  input_filename?: string | null;
  embedding_artifact_path?: string | null;
  request_json?: Record<string, unknown> | null;
  response_json?: Record<string, unknown> | null;
  error_json?: Record<string, unknown> | null;
  created_at: string;
}

export interface MlPredictionListResponse {
  predictions: MlPredictionRecord[];
}

export async function getMlModels(): Promise<ServiceResponse<MlModelsResponse>> {
  return apiClient.request<MlModelsResponse>('/ml/models');
}

export async function predictAnomalyFromEmbedding(
  payload: AnomalyEmbeddingRequest
): Promise<ServiceResponse<AnomalyPredictionResponse>> {
  return apiClient.request<AnomalyPredictionResponse>('/ml/predict-anomaly-from-embedding', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function predictAnomalyFromVideo(
  payload: VideoAnomalyRequest,
  signal?: AbortSignal
): Promise<ServiceResponse<AnomalyPredictionResponse>> {
  return apiClient.request<AnomalyPredictionResponse>('/ml/predict-anomaly-from-video', {
    method: 'POST',
    body: JSON.stringify(payload),
    signal,
  });
}

export async function getMlPredictionsForTest(
  testResultId: number,
  signal?: AbortSignal
): Promise<ServiceResponse<MlPredictionListResponse>> {
  return apiClient.request<MlPredictionListResponse>(`/ml/predictions/test/${encodeURIComponent(testResultId)}`, { signal });
}

export async function getMlPredictionsForSession(
  sessionId: string,
  signal?: AbortSignal
): Promise<ServiceResponse<MlPredictionListResponse>> {
  return apiClient.request<MlPredictionListResponse>(`/ml/predictions/session/${encodeURIComponent(sessionId)}`, { signal });
}

export async function getMlPredictionsForPatient(
  patientId: string,
  limit?: number,
  signal?: AbortSignal
): Promise<ServiceResponse<MlPredictionListResponse>> {
  const query = limit == null ? '' : `?limit=${encodeURIComponent(limit)}`;
  return apiClient.request<MlPredictionListResponse>(`/ml/predictions/patient/${encodeURIComponent(patientId)}${query}`, { signal });
}

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
