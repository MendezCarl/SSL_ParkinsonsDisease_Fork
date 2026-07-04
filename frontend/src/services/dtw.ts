import { getStoredAuthToken } from '@/auth/auth-session';
import type { ServiceResponse } from '@/services/service-response';

const API_BASE =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? '/api';

export type DtwSessionMeta = {
  session_id: string;
  created_utc: string;
  model?: 'hands' | 'pose';
  live_len?: number;
  ref_len?: number;
  distance?: number;
  similarity?: number;
};

export type AxisAggResponse = {
  ok: boolean;
  axis: 'x' | 'y' | 'z';
  reduce: 'mean' | 'median' | 'pca1';
  landmarks: 'all' | number[];
  live: { x: number[]; y: number[] };
  ref: { x: number[]; y: number[] };
  path: { i: number[]; j: number[] };
  warped: { k: number[]; live: number[]; ref: number[] };
};

export type MlPrediction = {
  predicted_updrs_stage: number;
  severity: string;
  confidence: number;
  probabilities: Record<string, number>;
};

export type DtwSeriesCurve = {
  local_cost_path: { x: number[]; y: number[] };
  cumulative_progress: { x: number[]; y: number[] };
  alignment_map: { x: number[]; y: number[] };
};

export type DtwSeriesMetrics = {
  ok: boolean;
  distance_pos?: number;
  distance_amp?: number;
  distance_spd?: number;
  avg_step_pos?: number;
  similarity_overall?: number;
  similarity_pos?: number;
  similarity_amp?: number;
  similarity_spd?: number;
  distance?: number;
  avg_step_cost?: number;
  similarity?: number;
  series?: {
    position: DtwSeriesCurve;
    amplitude: DtwSeriesCurve;
    speed: DtwSeriesCurve;
  };
};

export type DtwSessionLookup = {
  testName: string;
  sessionId: string;
};

export type DtwExportPayload = {
  npz: string;
  meta: string;
};

export type DtwLabelResponse = {
  ok: boolean;
  session_id: string;
  confirmed_stage: number;
  label_source: string;
  training_copy: string;
  patient_updated: boolean;
};

type RequestOptions = Omit<RequestInit, 'headers'> & {
  headers?: HeadersInit;
  signal?: AbortSignal;
};

async function requestJSON<T>(path: string, options: RequestOptions = {}): Promise<ServiceResponse<T>> {
  try {
    const token = getStoredAuthToken();
    const response = await fetch(`${API_BASE}${path}`, {
      ...options,
      headers: {
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...options.headers,
      },
    });

    const text = await response.text();

    if (!response.ok) {
      let parsed: { detail?: string; message?: string } | null = null;
      try {
        parsed = JSON.parse(text) as { detail?: string; message?: string };
      } catch {
        parsed = null;
      }
      return {
        success: false,
        error: parsed?.detail || parsed?.message || text || `HTTP ${response.status}`,
      };
    }

    return {
      success: true,
      data: text ? (JSON.parse(text) as T) : ({} as T),
    };
  } catch (error) {
    return {
      success: false,
      error: error instanceof Error ? error.message : 'Unknown error occurred',
    };
  }
}

export function getRecordingUrl(filename: string): string {
  return `${API_BASE}/recordings/${encodeURIComponent(filename)}`;
}

export async function lookupDtwSession(
  sessionId: string,
  patientId?: string,
  signal?: AbortSignal
): Promise<ServiceResponse<DtwSessionLookup>> {
  const query = patientId
    ? `?patient_id=${encodeURIComponent(patientId)}`
    : '';
  return requestJSON<DtwSessionLookup>(
    `/dtw/sessions/lookup/${encodeURIComponent(sessionId)}${query}`,
    { signal }
  );
}

export async function listPatientVideos(patientId: string, testKey: string, signal?: AbortSignal): Promise<ServiceResponse<string[]>> {
  const response = await requestJSON<{ success: boolean; videos: string[] }>(
    `/videos/${encodeURIComponent(patientId)}/${encodeURIComponent(testKey)}`,
    { signal }
  );
  if (!response.success) {
    return { success: false, error: response.error };
  }
  return { success: true, data: response.data?.success ? response.data.videos ?? [] : [] };
}

export async function listDtwSessions(
  testKey: string,
  patientId?: string,
  signal?: AbortSignal
): Promise<ServiceResponse<DtwSessionMeta[]>> {
  const query = patientId
    ? `?patient_id=${encodeURIComponent(patientId)}`
    : '';
  return requestJSON<DtwSessionMeta[]>(
    `/dtw/sessions/${encodeURIComponent(testKey)}${query}`,
    { signal }
  );
}

export async function getDtwSeries(
  testKey: string,
  sessionId: string,
  maxPoints: number,
  signal?: AbortSignal
): Promise<ServiceResponse<DtwSeriesMetrics>> {
  return requestJSON<DtwSeriesMetrics>(
    `/dtw/sessions/${encodeURIComponent(testKey)}/${encodeURIComponent(sessionId)}/series?max_points=${maxPoints}`,
    { signal }
  );
}

export async function getDtwAxisAggregate(
  testKey: string,
  sessionId: string,
  params: {
    axis: 'x' | 'y' | 'z';
    reduce: 'mean' | 'median' | 'pca1';
    landmarks: string;
    maxPoints: number;
  },
  signal?: AbortSignal
): Promise<ServiceResponse<AxisAggResponse>> {
  const query = new URLSearchParams({
    axis: params.axis,
    reduce: params.reduce,
    landmarks: params.landmarks,
    max_points: String(params.maxPoints),
  });

  return requestJSON<AxisAggResponse>(
    `/dtw/sessions/${encodeURIComponent(testKey)}/${encodeURIComponent(sessionId)}/axis_agg?${query.toString()}`,
    { signal }
  );
}

export async function getMlPredictionFromSession(
  testKey: string,
  sessionId: string,
  signal?: AbortSignal
): Promise<ServiceResponse<MlPrediction>> {
  return requestJSON<MlPrediction>(
    `/ml/updrs/from_session/${encodeURIComponent(testKey)}/${encodeURIComponent(sessionId)}`,
    { signal }
  );
}

export async function downloadDtwSession(testKey: string, sessionId: string): Promise<ServiceResponse<DtwExportPayload>> {
  return requestJSON<DtwExportPayload>(
    `/dtw/sessions/${encodeURIComponent(testKey)}/${encodeURIComponent(sessionId)}/download`
  );
}

export async function labelDtwSession(
  testKey: string,
  sessionId: string,
  payload: { confirmed_stage: number; patient_id: string | null; notes: string | null }
): Promise<ServiceResponse<DtwLabelResponse>> {
  return requestJSON<DtwLabelResponse>(
    `/dtw/sessions/${encodeURIComponent(testKey)}/${encodeURIComponent(sessionId)}/label`,
    {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }
  );
}
