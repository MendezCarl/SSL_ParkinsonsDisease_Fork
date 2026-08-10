import { AVAILABLE_TESTS, Patient, Test, TestIndicator, LabResultEntry, DoctorNoteEntry, TestAnalysisSnapshot } from '@/types/patient';

type TestType = Test['type'];
type TestStatus = Test['status'];

const TEST_METADATA: Record<TestType, { name: string; description: string }> = AVAILABLE_TESTS.reduce(
  (acc, test) => {
    acc[test.id] = { name: test.name, description: test.description };
    return acc;
  },
  {
    'stand-and-sit': { name: 'Stand and Sit Test', description: 'Measures sit-to-stand motor function' },
    'finger-tapping': { name: 'Finger Tapping Test', description: 'Measures rapid finger dexterity' },
    'fist-open-close': { name: 'Fist Open and Close Test', description: 'Assesses hand opening and closing cycles' },
    unknown: { name: 'Unsupported Test', description: 'Backend returned an unsupported test type.' },
  } as Record<TestType, { name: string; description: string }>,
);

const STATUS_INDICATORS: Record<TestStatus, TestIndicator> = {
  completed: {
    color: 'success',
    label: 'Completed',
    description: 'Recording captured successfully.',
  },
  'in-progress': {
    color: 'warning',
    label: 'In Progress',
    description: 'Recording underway. Metrics may still be processing.',
  },
  pending: {
    color: 'muted',
    label: 'Pending',
    description: 'Test scheduled but no recording available yet.',
  },
};

const KNOWN_TEST_TYPES: readonly TestType[] = ['stand-and-sit', 'finger-tapping', 'fist-open-close'] as const;

const toIsoStamp = (value?: string | null): string => {
  if (!value) return 'unknown-date';
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? 'unknown-date' : parsed.toISOString();
};

const slug = (value?: string | null): string => {
  const normalized = (value || '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
  return normalized || 'empty';
};

const buildStableEntryId = (
  kind: 'lab' | 'note',
  patientId: string,
  dateValue: string | undefined,
  contentValue: string | undefined,
  addedBy?: string,
): string => {
  return `${kind}_${slug(patientId)}_${slug(toIsoStamp(dateValue))}_${slug(contentValue).slice(0, 24)}_${slug(addedBy).slice(0, 16)}`;
};

export interface BackendLabResultEntry {
  id?: string;
  date: string;
  results: string;
  added_by?: string;
}

export interface BackendDoctorNoteEntry {
  id?: string;
  date: string;
  note: string;
  added_by?: string;
}

export interface BackendPatient {
  patient_id: string;
  recordNumber?: string;
  name: string;
  birthDate: string;
  age?: number;
  height?: number | string | null;
  weight?: number | string | null;
  severity: string;
  lab_results_history?: BackendLabResultEntry[];
  doctors_notes_history?: BackendDoctorNoteEntry[];
  latest_lab_result?: BackendLabResultEntry | null;
  latest_doctor_note?: BackendDoctorNoteEntry | null;
}

type IndicatorColor = TestIndicator['color'];

interface BackendTestIndicator {
  color?: string | null;
  label?: string | null;
  description?: string | null;
}

interface BackendDtwMetrics {
  distance?: number | string | null;
  avg_step_cost?: number | string | null;
  similarity?: number | string | null;
  session_id?: string | null;
  artifacts_dir?: string | null;
  artifacts?: { dir?: string | null } | null;
}

interface BackendStoredDtwAnalysis {
  session_id?: string | null;
  distance_pos?: number | string | null;
  distance_amp?: number | string | null;
  distance_spd?: number | string | null;
  avg_step_pos?: number | string | null;
  avg_step_cost?: number | string | null;
  similarity_overall?: number | string | null;
  similarity_pos?: number | string | null;
  similarity_amp?: number | string | null;
  similarity_spd?: number | string | null;
  distance?: number | string | null;
  similarity?: number | string | null;
}

interface BackendStoredMlPrediction {
  predicted_updrs_stage?: number | null;
  probabilities?: Record<string, number> | null;
  severity?: string | null;
  severity_stage?: number | null;
  prediction?: string | null;
  confidence?: number | null;
  model_version?: string | null;
  preprocessing_version?: string | null;
  generated_at?: string | null;
}

interface BackendStoredAnomalyPrediction {
  prediction_id?: number | string | null;
  test_result_id?: number | string | null;
  predicted_label?: string | null;
  anomaly_probability?: number | string | null;
  anomaly_score?: number | string | null;
  probability?: number | string | null;
  score?: number | string | null;
  video_model?: string | null;
  anomaly_model?: string | null;
  classifier_model?: string | null;
  model_version?: string | null;
  created_at?: string | null;
  generated_at?: string | null;
  persisted?: boolean | null;
  review_windows?: {
    start_sec?: number | string | null;
    end_sec?: number | string | null;
    predicted_label?: string | null;
    anomaly_probability?: number | string | null;
    anomaly_score?: number | string | null;
  }[] | null;
}

interface BackendAnalysisSnapshot {
  dtw_metrics?: BackendStoredDtwAnalysis | null;
  ml_prediction?: BackendStoredMlPrediction | null;
  anomaly_prediction?: BackendStoredAnomalyPrediction | null;
}

export interface BackendTestEntry {
  id?: string | null;
  test_id?: string | null;
  test_name?: string | null;
  display_name?: string | null;
  name?: string | null;
  date?: string | null;
  status?: string | null;
  recording_file?: string | null;
  recording_url?: string | null;
  summary_available?: boolean | null;
  frame_count?: number | string | null;
  fps?: number | string | null;
  dtw?: BackendDtwMetrics | null;
  analysis?: BackendAnalysisSnapshot | null;
  indicator?: BackendTestIndicator | null;
  patient_id?: string | null;
  model?: string | null;
}

export interface BackendPatientCreate {
  name: string;
  age?: number;
  birthDate: string;
  height: string;
  weight: string;
  severity: string;
  lab_results_history?: BackendLabResultEntry[];
  doctors_notes_history?: BackendDoctorNoteEntry[];
}

export interface BackendPatientUpdate {
  name?: string;
  birthDate?: string;
  height?: string;
  weight?: string;
  severity?: string;
}

export interface BackendPatientMutationResult {
  success: boolean;
  patient_id: string;
}

export interface HealthStatus {
  status?: string;
  [key: string]: unknown;
}

export interface UploadVideoResponse {
  success?: boolean;
  filename?: string;
  path?: string;
  patient_id?: string;
  test_name?: string;
  session_id?: string;
  [key: string]: unknown;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
}

export interface BackendSeverityPrediction {
  predicted_updrs_stage: number;
  probabilities: Record<string, number>;
  severity: string;
  severity_stage: number;
  prediction: string;
  confidence: number;
  lstm_output: number[];
  logits: number[];
  n_windows: number;
  window_size: number;
  stride: number;
  model_version: string;
  preprocessing_version: string;
  checkpoint_path: string;
  attention_weights?: number[] | null;
  patient_id: string;
  patient_updated: boolean;
}

export interface PatientFormInput {
  firstName: string;
  lastName: string;
  recordNumber?: string;
  birthDate: string;
  height: string;
  weight: string;
  labResults: string;
  doctorNotes: string;
  severity: Patient['severity'];
  createdAt?: Date;
  updatedAt?: Date;
}

export type PatientUpdateInput = Partial<Pick<Patient, 'firstName' | 'lastName' | 'birthDate' | 'height' | 'weight' | 'severity'>>;

export type AuthTokenPayload = {
  accessToken: string;
  tokenType: string;
};

const normalizeTestKey = (value?: string | null): string => {
  if (!value) return '';
  return value.trim().toLowerCase().replace(/[_\s]+/g, '-');
};

const resolveTestType = (value?: string | null): TestType => {
  const normalized = normalizeTestKey(value);
  if ((KNOWN_TEST_TYPES as readonly string[]).includes(normalized as TestType)) {
    return normalized as TestType;
  }
  if (normalized === 'finger-taping') {
    return 'finger-tapping';
  }
  return 'unknown';
};

const resolveTestStatus = (value?: string | null, hasRecording: boolean = false): TestStatus => {
  const normalized = (value || '').trim().toLowerCase();
  if (normalized === 'completed' || normalized === 'in-progress' || normalized === 'pending') {
    return normalized as TestStatus;
  }
  return hasRecording ? 'completed' : 'pending';
};

const toDate = (value?: string | null): Date => {
  if (!value) return new Date();
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? new Date() : parsed;
};

const isIndicatorColor = (value: string): value is IndicatorColor => {
  return ['success', 'warning', 'destructive', 'muted'].includes(value);
};

const normalizeIndicator = (status: TestStatus, indicator?: BackendTestIndicator | null): TestIndicator => {
  const base = { ...STATUS_INDICATORS[status] };
  if (!indicator) return base;
  if (indicator.color && typeof indicator.color === 'string' && isIndicatorColor(indicator.color)) base.color = indicator.color;
  if (indicator.label && typeof indicator.label === 'string') base.label = indicator.label;
  if (indicator.description && typeof indicator.description === 'string') base.description = indicator.description;
  return base;
};

const resolveRecordingPaths = (recordingUrl?: string | null, recordingFile?: string | null, apiBaseUrl: string = '/api') => {
  let absolute: string | undefined;
  let relative: string | undefined;

  if (recordingUrl) {
    if (recordingUrl.startsWith('http://') || recordingUrl.startsWith('https://')) {
      absolute = recordingUrl;
    } else {
      relative = recordingUrl.startsWith('/') ? recordingUrl : `/${recordingUrl}`;
      absolute = `${apiBaseUrl}${relative}`;
    }
  } else if (recordingFile) {
    const sanitized = recordingFile.replace(/^\/+/, '');
    relative = `/recordings/${sanitized}`;
    absolute = `${apiBaseUrl}${relative}`;
  }

  return { relative, absolute };
};

const parseNumber = (value: number | string | null | undefined): number | null => {
  if (value === null || value === undefined) return null;
  if (typeof value === 'number') return Number.isFinite(value) ? value : null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
};

const parseInteger = (value: number | string | null | undefined): number | null => {
  const parsed = parseNumber(value);
  return parsed === null ? null : Math.trunc(parsed);
};

const parseStoredAnalysis = (analysis?: BackendAnalysisSnapshot | null): TestAnalysisSnapshot | null => {
  if (!analysis) return null;

  const dtwMetrics = analysis.dtw_metrics
    ? {
        session_id: analysis.dtw_metrics.session_id ?? null,
        distance_pos: parseNumber(analysis.dtw_metrics.distance_pos),
        distance_amp: parseNumber(analysis.dtw_metrics.distance_amp),
        distance_spd: parseNumber(analysis.dtw_metrics.distance_spd),
        avg_step_pos: parseNumber(analysis.dtw_metrics.avg_step_pos),
        avg_step_cost: parseNumber(analysis.dtw_metrics.avg_step_cost),
        similarity_overall: parseNumber(analysis.dtw_metrics.similarity_overall),
        similarity_pos: parseNumber(analysis.dtw_metrics.similarity_pos),
        similarity_amp: parseNumber(analysis.dtw_metrics.similarity_amp),
        similarity_spd: parseNumber(analysis.dtw_metrics.similarity_spd),
        distance: parseNumber(analysis.dtw_metrics.distance),
        similarity: parseNumber(analysis.dtw_metrics.similarity),
      }
    : null;

  const rawPrediction = analysis.ml_prediction;
  const mlPrediction = rawPrediction && rawPrediction.predicted_updrs_stage != null && rawPrediction.severity && rawPrediction.prediction
    ? {
        predicted_updrs_stage: rawPrediction.predicted_updrs_stage,
        probabilities: rawPrediction.probabilities ?? {},
        severity: rawPrediction.severity,
        severity_stage: rawPrediction.severity_stage ?? rawPrediction.predicted_updrs_stage + 1,
        prediction: rawPrediction.prediction,
        confidence: rawPrediction.confidence ?? 0,
        model_version: rawPrediction.model_version ?? null,
        preprocessing_version: rawPrediction.preprocessing_version ?? null,
        generated_at: rawPrediction.generated_at ?? null,
      }
    : null;

  const rawAnomalyPrediction = analysis.anomaly_prediction;
  const reviewWindows = rawAnomalyPrediction?.review_windows
    ?.map((window) => ({
      start_sec: parseNumber(window.start_sec),
      end_sec: parseNumber(window.end_sec),
      predicted_label: window.predicted_label ?? '',
      anomaly_probability: parseNumber(window.anomaly_probability),
      anomaly_score: parseNumber(window.anomaly_score),
    }))
    .filter((window): window is {
      start_sec: number;
      end_sec: number;
      predicted_label: string;
      anomaly_probability: number | null;
      anomaly_score: number | null;
    } => window.start_sec !== null && window.end_sec !== null && Boolean(window.predicted_label)) ?? [];
  const anomalyPrediction = rawAnomalyPrediction?.predicted_label
    ? {
        prediction_id: parseInteger(rawAnomalyPrediction.prediction_id),
        test_result_id: parseInteger(rawAnomalyPrediction.test_result_id),
        predicted_label: rawAnomalyPrediction.predicted_label,
        anomaly_probability: parseNumber(rawAnomalyPrediction.anomaly_probability ?? rawAnomalyPrediction.probability),
        anomaly_score: parseNumber(rawAnomalyPrediction.anomaly_score ?? rawAnomalyPrediction.score),
        video_model: rawAnomalyPrediction.video_model ?? null,
        anomaly_model: rawAnomalyPrediction.anomaly_model ?? rawAnomalyPrediction.classifier_model ?? null,
        classifier_model: rawAnomalyPrediction.classifier_model ?? rawAnomalyPrediction.anomaly_model ?? null,
        model_version: rawAnomalyPrediction.model_version ?? null,
        created_at: rawAnomalyPrediction.created_at ?? null,
        generated_at: rawAnomalyPrediction.generated_at ?? null,
        persisted: rawAnomalyPrediction.persisted ?? null,
        review_windows: reviewWindows,
      }
    : null;

  if (!dtwMetrics && !mlPrediction && !anomalyPrediction) return null;
  return { dtwMetrics, mlPrediction, anomalyPrediction };
};

export const convertBackendTestToFrontend = (patientId: string, entry: BackendTestEntry, apiBaseUrl: string = '/api'): Test => {
  const testType = resolveTestType(entry.test_name || entry.name || entry.display_name);
  if (testType === 'unknown') {
    console.warn('Unsupported backend test type received', {
      patientId,
      rawType: entry.test_name || entry.name || entry.display_name || null,
      entry,
    });
  }
  const metadata = TEST_METADATA[testType];
  const recordingPaths = resolveRecordingPaths(entry.recording_url, entry.recording_file, apiBaseUrl);
  const hasRecording = Boolean(recordingPaths.absolute);
  const status = resolveTestStatus(entry.status, hasRecording);
  const indicator = normalizeIndicator(status, entry.indicator);
  const testDate = toDate(entry.date);

  const dtwMetrics = entry.dtw || null;
  const analysis = parseStoredAnalysis(entry.analysis);
  const similarity = dtwMetrics ? parseNumber(dtwMetrics.similarity) : analysis?.dtwMetrics?.similarity ?? analysis?.dtwMetrics?.similarity_overall ?? null;
  const distance = dtwMetrics ? parseNumber(dtwMetrics.distance) : analysis?.dtwMetrics?.distance ?? analysis?.dtwMetrics?.distance_pos ?? null;
  const rawId = entry.test_id || entry.id || entry.recording_file || `${testType}-${testDate.getTime()}`;
  const sanitizedId = String(rawId).replace(/\s+/g, '-');
  const dtwSessionId =
    (dtwMetrics && typeof dtwMetrics.session_id === 'string' ? dtwMetrics.session_id : null) ??
    analysis?.dtwMetrics?.session_id ??
    ((dtwMetrics || analysis) && entry.test_id ? String(entry.test_id) : null) ??
    null;

  return {
    id: sanitizedId,
    patientId,
    name: entry.display_name || entry.name || metadata?.name || 'Motor Test',
    type: testType,
    date: testDate,
    status,
    videoUrl: recordingPaths.absolute,
    recordingUrl: recordingPaths.absolute ?? recordingPaths.relative,
    recordingFile: entry.recording_file || undefined,
    summaryAvailable: entry.summary_available ?? hasRecording,
    frameCount: parseNumber(entry.frame_count),
    fps: parseNumber(entry.fps),
    similarity,
    distance,
    dtwSessionId,
    indicator,
    analysis,
    results: undefined,
  };
};

export const convertBackendToFrontend = (backendPatient: BackendPatient): Patient => {
  const name = backendPatient.name || '';
  const nameParts = name.split(' ');
  const firstName = nameParts[0] || '';
  const lastName = nameParts.slice(1).join(' ') || '';
  const doctorNotesHistoryRaw = backendPatient.doctors_notes_history || [];
  const labResultsHistoryRaw = backendPatient.lab_results_history || [];

  const doctorNotesHistory = doctorNotesHistoryRaw.map(entry => ({
    id: entry.id || buildStableEntryId('note', backendPatient.patient_id, entry.date, entry.note, entry.added_by),
    date: new Date(entry.date),
    note: entry.note,
    addedBy: entry.added_by || 'Unknown',
  }));

  const labResultsHistory = labResultsHistoryRaw.map(entry => ({
    id: entry.id || buildStableEntryId('lab', backendPatient.patient_id, entry.date, entry.results, entry.added_by),
    date: new Date(entry.date),
    results: entry.results,
    addedBy: entry.added_by || 'Unknown',
  }));

  const latestDoctorNoteBackend = backendPatient.latest_doctor_note || doctorNotesHistoryRaw.slice().sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime())[0];
  const latestLabResultBackend = backendPatient.latest_lab_result || labResultsHistoryRaw.slice().sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime())[0];

  const latestDoctorNote = latestDoctorNoteBackend
    ? {
        id: latestDoctorNoteBackend.id || buildStableEntryId('note', backendPatient.patient_id, latestDoctorNoteBackend.date, latestDoctorNoteBackend.note, latestDoctorNoteBackend.added_by),
        date: new Date(latestDoctorNoteBackend.date),
        note: latestDoctorNoteBackend.note,
        addedBy: latestDoctorNoteBackend.added_by || 'Unknown',
      }
    : undefined;

  const latestLabResult = latestLabResultBackend
    ? {
        id: latestLabResultBackend.id || buildStableEntryId('lab', backendPatient.patient_id, latestLabResultBackend.date, latestLabResultBackend.results, latestLabResultBackend.added_by),
        date: new Date(latestLabResultBackend.date),
        results: latestLabResultBackend.results,
        addedBy: latestLabResultBackend.added_by || 'Unknown',
      }
    : undefined;

  const lastVisit = latestDoctorNote?.date ?? null;
  const primaryPhysician = latestDoctorNote?.addedBy?.trim() || null;

  return {
    id: backendPatient.patient_id || '',
    firstName,
    lastName,
    recordNumber: backendPatient.recordNumber || backendPatient.patient_id || '',
    birthDate: backendPatient.birthDate || '',
    height: `${backendPatient.height || 0} cm`,
    weight: `${backendPatient.weight || 0} kg`,
    labResults: latestLabResult?.results || '',
    doctorNotes: latestDoctorNote?.note || '',
    labResultsHistory,
    doctorNotesHistory,
    severity: mapSeverity(backendPatient.severity || 'Stage 1'),
    lastVisit,
    primaryPhysician,
    createdAt: lastVisit ?? new Date(),
    updatedAt: lastVisit ?? new Date(),
  };
};

export const convertFrontendToBackend = (frontendPatient: PatientFormInput): BackendPatientCreate => {
  const fullName = `${frontendPatient.firstName || ''} ${frontendPatient.lastName || ''}`.trim();
  const heightStr = (frontendPatient.height || '').replace(/[^\d.]/g, '');
  const weightStr = (frontendPatient.weight || '').replace(/[^\d.]/g, '');

  const ensureISODate = (value: unknown): string => {
    if (value instanceof Date) return value.toISOString();
    const parsed = new Date(value as string);
    return Number.isNaN(parsed.getTime()) ? new Date().toISOString() : parsed.toISOString();
  };

  const labResultsHistory: BackendLabResultEntry[] = ((frontendPatient as Patient).labResultsHistory || []).map((entry: LabResultEntry) => ({
    id: entry.id,
    date: ensureISODate(entry.date),
    results: entry.results,
    added_by: entry.addedBy,
  }));

  const doctorNotesHistory: BackendDoctorNoteEntry[] = ((frontendPatient as Patient).doctorNotesHistory || []).map((entry: DoctorNoteEntry) => ({
    id: entry.id,
    date: ensureISODate(entry.date),
    note: entry.note,
    added_by: entry.addedBy,
  }));

  const trimmedLabResults = (frontendPatient.labResults || '').trim();
  if (trimmedLabResults && labResultsHistory.length === 0) {
    labResultsHistory.push({
      id: `lab_${Date.now()}`,
      date: new Date().toISOString(),
      results: trimmedLabResults,
      added_by: frontendPatient.primaryPhysician || 'Unknown',
    });
  }

  const trimmedDoctorNotes = (frontendPatient.doctorNotes || '').trim();
  if (trimmedDoctorNotes && doctorNotesHistory.length === 0) {
    doctorNotesHistory.push({
      id: `note_${Date.now()}`,
      date: new Date().toISOString(),
      note: trimmedDoctorNotes,
      added_by: frontendPatient.primaryPhysician || 'Unknown',
    });
  }

  return {
    name: fullName,
    birthDate: frontendPatient.birthDate,
    height: heightStr || '0',
    weight: weightStr || '0',
    severity: frontendPatient.severity,
    lab_results_history: labResultsHistory,
    doctors_notes_history: doctorNotesHistory,
  };
};

export const mapSeverity = (backendSeverity: string): 'Stage 1' | 'Stage 2' | 'Stage 3' | 'Stage 4' | 'Stage 5' => {
  const normalized = (backendSeverity || '').trim();
  if (normalized === 'Stage 1' || normalized === 'Stage 2' || normalized === 'Stage 3' || normalized === 'Stage 4' || normalized === 'Stage 5') {
    return normalized;
  }
  return 'Stage 1';
};
