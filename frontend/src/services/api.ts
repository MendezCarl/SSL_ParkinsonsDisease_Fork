import { AVAILABLE_TESTS, Patient, Test, TestIndicator, LabResultEntry, DoctorNoteEntry } from '@/types/patient';

const API_BASE_URL = '/api'; // routed through Vite proxy (/api → backend root); works locally and in Docker

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

export function normalizeBirthDate(value: string): string {
  if (!value) return '';
  const trimmed = value.trim();
  if (!trimmed) return '';

  const isoMatch = trimmed.match(/^(\d{4})[\/-](\d{2})[\/-](\d{2})$/);
  if (isoMatch) {
    return `${isoMatch[1]}-${isoMatch[2]}-${isoMatch[3]}`;
  }

  const parsed = new Date(trimmed);
  if (Number.isNaN(parsed.getTime())) return '';

  const year = parsed.getUTCFullYear();
  const month = String(parsed.getUTCMonth() + 1).padStart(2, '0');
  const day = String(parsed.getUTCDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

//remove later
const calculateAge = (birthDate: string): number => {
  const normalized = normalizeBirthDate(birthDate);
  if (!normalized) return 0;

  const [yearStr, monthStr, dayStr] = normalized.split('-');
  const year = Number(yearStr);
  const month = Number(monthStr);
  const day = Number(dayStr);

  if (!year || !month || !day) return 0;

  const today = new Date();
  let age = today.getFullYear() - year;
  const monthDiff = today.getMonth() + 1 - month;

  if (monthDiff < 0 || (monthDiff === 0 && today.getDate() < day)) {
    age--;
  }
  
  return Math.max(0, age);
};

// Types for backend API
interface BackendLabResultEntry {
  id?: string;
  date: string;
  results: string;
  added_by?: string;
}

interface BackendDoctorNoteEntry {
  id?: string;
  date: string;
  note: string;
  added_by?: string;
}

interface BackendPatient {
  patient_id: string;
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

interface BackendTestEntry {
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
  indicator?: BackendTestIndicator | null;
  patient_id?: string | null;
  model?: string | null;
}

interface BackendPatientCreate {
  name: string;
  age: number;
  birthDate: string;
  height: string;
  weight: string;
  severity: string;
  lab_results_history?: BackendLabResultEntry[];
  doctors_notes_history?: BackendDoctorNoteEntry[];
}

interface BackendPatientUpdate {
  name?: string;
  birthDate?: string;
  height?: string;
  weight?: string;
  severity?: string;
}

interface BackendPatientMutationResult {
  success: boolean;
  patient_id: string;
}

interface HealthStatus {
  status?: string;
  [key: string]: unknown;
}

interface UploadVideoResponse {
  filename?: string;
  disk_path?: string;
  [key: string]: unknown;
}

interface BackendSeverityPrediction {
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

interface ApiResponse<T> {
  success: boolean;
  data?: T;
  error?: string;
}

export interface PatientFormInput {
  firstName: string;
  lastName: string;
  recordNumber: string;
  birthDate: string;
  height: string;
  weight: string;
  labResults: string;
  doctorNotes: string;
  severity: Patient['severity'];
  createdAt?: Date;
  updatedAt?: Date;
}

type PatientUpdateInput = Partial<Pick<Patient, 'firstName' | 'lastName' | 'birthDate' | 'height' | 'weight' | 'severity'>>;

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
  return 'stand-and-sit';
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
  if (!indicator) {
    return base;
  }
  if (indicator.color && typeof indicator.color === 'string' && isIndicatorColor(indicator.color)) {
    base.color = indicator.color;
  }
  if (indicator.label && typeof indicator.label === 'string') {
    base.label = indicator.label;
  }
  if (indicator.description && typeof indicator.description === 'string') {
    base.description = indicator.description;
  }
  return base;
};

const resolveRecordingPaths = (recordingUrl?: string | null, recordingFile?: string | null) => {
  let absolute: string | undefined;
  let relative: string | undefined;

  if (recordingUrl) {
    if (recordingUrl.startsWith('http://') || recordingUrl.startsWith('https://')) {
      absolute = recordingUrl;
    } else {
      relative = recordingUrl.startsWith('/') ? recordingUrl : `/${recordingUrl}`;
      absolute = `${API_BASE_URL}${relative}`;
    }
  } else if (recordingFile) {
    const sanitized = recordingFile.replace(/^\/+/, '');
    relative = `/recordings/${sanitized}`;
    absolute = `${API_BASE_URL}${relative}`;
  }

  return { relative, absolute };
};

const parseNumber = (value: number | string | null | undefined): number | null => {
  if (value === null || value === undefined) return null;
  if (typeof value === 'number') {
    return Number.isFinite(value) ? value : null;
  }
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
};

const convertBackendTestToFrontend = (patientId: string, entry: BackendTestEntry): Test => {
  const testType = resolveTestType(entry.test_name || entry.name || entry.display_name);
  const metadata = TEST_METADATA[testType];
  const recordingPaths = resolveRecordingPaths(entry.recording_url, entry.recording_file);
  const hasRecording = Boolean(recordingPaths.absolute);
  const status = resolveTestStatus(entry.status, hasRecording);
  const indicator = normalizeIndicator(status, entry.indicator);
  const testDate = toDate(entry.date);

  const dtwMetrics = entry.dtw || null;
  const similarity = dtwMetrics ? parseNumber(dtwMetrics.similarity) : null;
  const distance = dtwMetrics ? parseNumber(dtwMetrics.distance) : null;

  const rawId = entry.test_id || entry.id || entry.recording_file || `${testType}-${testDate.getTime()}`;
  const sanitizedId = String(rawId).replace(/\s+/g, '-');

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
    dtwSessionId: dtwMetrics && typeof dtwMetrics.session_id === 'string' ? dtwMetrics.session_id : null,
    indicator,
    results: undefined,
  };
};

// Convert backend patient to frontend patient
const convertBackendToFrontend = (backendPatient: BackendPatient): Patient => {
  // Handle undefined or null name
  const name = backendPatient.name || '';
  const nameParts = name.split(' ');
  const firstName = nameParts[0] || '';
  const lastName = nameParts.slice(1).join(' ') || '';
  const normalizedBirthDate = normalizeBirthDate(backendPatient.birthDate);
  const doctorNotesHistoryRaw = backendPatient.doctors_notes_history || [];
  const labResultsHistoryRaw = backendPatient.lab_results_history || [];

  const doctorNotesHistory = doctorNotesHistoryRaw.map(entry => ({
    id: entry.id || `note_${Date.now()}`,
    date: new Date(entry.date),
    note: entry.note,
    addedBy: entry.added_by || 'Unknown',
  }));

  const labResultsHistory = labResultsHistoryRaw.map(entry => ({
    id: entry.id || `lab_${Date.now()}`,
    date: new Date(entry.date),
    results: entry.results,
    addedBy: entry.added_by || 'Unknown',
  }));

  const latestDoctorNoteBackend = backendPatient.latest_doctor_note || doctorNotesHistoryRaw
    .slice()
    .sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime())[0];

  const latestLabResultBackend = backendPatient.latest_lab_result || labResultsHistoryRaw
    .slice()
    .sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime())[0];

  const latestDoctorNote = latestDoctorNoteBackend
    ? {
        id: latestDoctorNoteBackend.id || `note_${Date.now()}`,
        date: new Date(latestDoctorNoteBackend.date),
        note: latestDoctorNoteBackend.note,
        addedBy: latestDoctorNoteBackend.added_by || 'Unknown',
      }
    : undefined;

  const latestLabResult = latestLabResultBackend
    ? {
        id: latestLabResultBackend.id || `lab_${Date.now()}`,
        date: new Date(latestLabResultBackend.date),
        results: latestLabResultBackend.results,
        addedBy: latestLabResultBackend.added_by || 'Unknown',
      }
    : undefined;

  const lastVisit = latestDoctorNote?.date ?? null;
  const primaryPhysician = latestDoctorNote?.addedBy?.trim() || null;

  return {
    id: backendPatient.patient_id || "",
    firstName,
    lastName,
    recordNumber: backendPatient.patient_id || '', // Using patient_id as record number
    birthDate: normalizedBirthDate || backendPatient.birthDate || '',
    height: `${backendPatient.height || 0} cm`,
    weight: `${backendPatient.weight || 0} kg`,
    labResults: latestLabResult?.results || '',
    doctorNotes: latestDoctorNote?.note || '',
    labResultsHistory,
    doctorNotesHistory,
    severity: mapSeverity(backendPatient.severity || 'low'),
    lastVisit,
    primaryPhysician,
    createdAt: lastVisit ?? new Date(), // Backend doesn't provide this, approximated from last visit
    updatedAt: lastVisit ?? new Date(), // Backend doesn't provide this, approximated from last visit
  };
};

// Convert frontend patient to backend format
const convertFrontendToBackend = (frontendPatient: PatientFormInput): BackendPatientCreate => {
  const fullName = `${frontendPatient.firstName || ''} ${frontendPatient.lastName || ''}`.trim();
  
  const heightStr = (frontendPatient.height || '').replace(/[^\d.]/g, '');
  const weightStr = (frontendPatient.weight || '').replace(/[^\d.]/g, '');
  const normalizedBirthDate = normalizeBirthDate(frontendPatient.birthDate);
  
  const ensureISODate = (value: any): string => {
    if (value instanceof Date) return value.toISOString();
    const parsed = new Date(value);
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
    age: calculateAge(normalizedBirthDate || frontendPatient.birthDate), // Use your existing function
    birthDate: normalizedBirthDate || frontendPatient.birthDate,
    height: heightStr || '0',
    weight: weightStr || '0',
    severity: mapSeverityToBackend(frontendPatient.severity),
    lab_results_history: labResultsHistory,
    doctors_notes_history: doctorNotesHistory,
  };
};

// Map severity from backend to frontend
export const mapSeverity = (backendSeverity: string): 'Stage 1' | 'Stage 2' | 'Stage 3' | 'Stage 4' | 'Stage 5' => {
  const normalized = (backendSeverity || '').trim().toLowerCase();
  const mapping: Record<string, 'Stage 1' | 'Stage 2' | 'Stage 3' | 'Stage 4' | 'Stage 5'> = {
    'stage 1': 'Stage 1',
    'stage 2': 'Stage 2',
    'stage 3': 'Stage 3',
    'stage 4': 'Stage 4',
    'stage 5': 'Stage 5',
    'low': 'Stage 1',
    'mild': 'Stage 2',
    'medium': 'Stage 3',
    'moderate': 'Stage 3',
    'high': 'Stage 4',
    'severe': 'Stage 5',
  };

  return mapping[normalized] ?? 'Stage 1';
};

// Map severity from frontend to backend
const mapSeverityToBackend = (frontendSeverity: string): string => {
  const normalized = (frontendSeverity || '').trim().toLowerCase();
  const mapping: Record<string, string> = {
    'stage 1': 'Stage 1',
    'stage 2': 'Stage 2',
    'stage 3': 'Stage 3',
    'stage 4': 'Stage 4',
    'stage 5': 'Stage 5',
    'low': 'Stage 1',
    'mild': 'Stage 2',
    'medium': 'Stage 3',
    'moderate': 'Stage 3',
    'high': 'Stage 4',
    'severe': 'Stage 5',
  };

  return mapping[normalized] ?? 'Stage 1';
};

// API service class
class ApiService {
  private baseUrl: string;

  constructor(baseUrl: string = API_BASE_URL) {
    this.baseUrl = baseUrl;
  }

  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<ApiResponse<T>> {
    try {
      const url = `${this.baseUrl}${endpoint}`;
      const isFormDataBody = options.body instanceof FormData;
      const headers: HeadersInit = isFormDataBody
        ? { ...options.headers }
        : {
            "Content-Type": "application/json",
            ...options.headers,
          };

      const response = await fetch(url, {
        headers,
        ...options,
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        console.error("API Error Response:", errorData);
        console.error("Error Response Type:", typeof errorData);
        console.error("Error Detail Type:", typeof errorData.detail);
        console.error("Full Error Object:", JSON.stringify(errorData, null, 2));

        let errorMessage = `HTTP error! status: ${response.status}`;

        if (errorData.detail) {
          if (Array.isArray(errorData.detail)) {
            // Handle validation error array
            errorMessage = errorData.detail
              .map((err: any) => {
                const field = err.loc?.join(".") || "field";
                return `${field}: ${err.msg}`;
              })
              .join(", ");
          } else if (typeof errorData.detail === "object") {
            // Handle nested error object
            errorMessage = JSON.stringify(errorData.detail);
          } else {
            errorMessage = errorData.detail;
          }
        } else if (errorData.message) {
          errorMessage = errorData.message;
        }

        throw new Error(errorMessage);
      }

      const data = await response.json();
      return { success: true, data };
    } catch (error) {
      console.error("API request failed:", error);
      return {
        success: false,
        error:
          error instanceof Error ? error.message : "Unknown error occurred",
      };
    }
  }

  // Get all patients
  async getPatients(
    skip: number = 0,
    limit: number = 100
  ): Promise<ApiResponse<Patient[]>> {
    const response = await this.request<{
      patients: BackendPatient[];
      total: number;
    }>(`/patients/?skip=${skip}&limit=${limit}`);

    if (response.success && response.data) {
      const convertedPatients = response.data.patients.map(
        convertBackendToFrontend
      );
      return { success: true, data: convertedPatients };
    }

    return { success: false, error: response.error };
  }

  // Get single patient
  async getPatient(patientId: string): Promise<ApiResponse<Patient>> {
    const response = await this.request<
      { patient: BackendPatient } | BackendPatient
    >(`/patients/${patientId}`);

    if (response.success && response.data) {
      // Handle the nested patient structure from the backend
      const patientData =
        "patient" in response.data ? response.data.patient : response.data;
      const convertedPatient = convertBackendToFrontend(patientData);
      return { success: true, data: convertedPatient };
    }

    return { success: false, error: response.error };
  }

  async getHealthStatus(): Promise<ApiResponse<HealthStatus>> {
    return this.request<HealthStatus>('/health');
  }

  // Create new patient
  async createPatient(patientData: PatientFormInput): Promise<ApiResponse<Patient>> {
    const backendData = convertFrontendToBackend(patientData);

    const response = await this.request<BackendPatientMutationResult>("/patients/", {
      method: "POST",
      body: JSON.stringify(backendData),
    });

    if (response.success && response.data) {
      return this.getPatient(response.data.patient_id);
    }

    return { success: false, error: response.error };
  }

  // Update patient
  async updatePatient(
    patientId: string,
    updateData: PatientUpdateInput
  ): Promise<ApiResponse<Patient>> {
    const backendData: BackendPatientUpdate = {};

    console.log("Update patient input data:", updateData);

    if (updateData.firstName || updateData.lastName) {
      const fullName = `${updateData.firstName || ""} ${
        updateData.lastName || ""
      }`.trim();
      backendData.name = fullName;
    }
    
    if (updateData.birthDate !== undefined) {
      const normalized = normalizeBirthDate(updateData.birthDate);
      backendData.birthDate = normalized || updateData.birthDate;
    }
    
    if (updateData.height) {
      const heightStr = updateData.height.replace(/[^\d.]/g, "");
      backendData.height = heightStr || "0";
    }
    if (updateData.weight) {
      const weightStr = updateData.weight.replace(/[^\d.]/g, "");
      backendData.weight = weightStr || "0";
    }
    if (updateData.severity) {
      const mappedSeverity = updateData.severity;
      console.log(
        "Severity mapping:",
        updateData.severity,
        "->",
        mappedSeverity
      );
      backendData.severity = mappedSeverity;
    }

          console.log('Backend update data:', backendData);
          console.log('Data types:', {
            name: typeof backendData.name,
            birthDate: typeof backendData.birthDate,
            height: typeof backendData.height,
            weight: typeof backendData.weight,
            severity: typeof backendData.severity
        });



    const response = await this.request<BackendPatientMutationResult>(
      `/patients/${patientId}`,
      {
        method: "PUT",
        body: JSON.stringify(backendData),
      }
    );

    if (response.success && response.data) {
      return this.getPatient(response.data.patient_id);
    }

    return { success: false, error: response.error };
  }

  async addPatientLabResult(
    patientId: string,
    entry: BackendLabResultEntry
  ): Promise<ApiResponse<BackendPatientMutationResult>> {
    return this.request<BackendPatientMutationResult>(`/patients/${patientId}/lab-results`, {
      method: 'POST',
      body: JSON.stringify(entry),
    });
  }

  async addPatientDoctorNote(
    patientId: string,
    entry: BackendDoctorNoteEntry
  ): Promise<ApiResponse<BackendPatientMutationResult>> {
    return this.request<BackendPatientMutationResult>(`/patients/${patientId}/doctor-notes`, {
      method: 'POST',
      body: JSON.stringify(entry),
    });
  }

  // Delete patient
  async deletePatient(patientId: string): Promise<ApiResponse<boolean>> {
    return await this.request<boolean>(`/patients/${patientId}`, {
      method: "DELETE",
    });
  }

  // Search patients
  async searchPatients(query: string): Promise<ApiResponse<any[]>> {
    const response = await this.request<{
      patients: BackendPatient[];
      count: number;
    }>(`/patients/search/${encodeURIComponent(query)}`);

    if (response.success && response.data) {
      const convertedPatients = response.data.patients.map(
        convertBackendToFrontend
      );
      return { success: true, data: convertedPatients };
    }

    return { success: false, error: response.error };
  }

  // Filter patients
  async filterPatients(criteria: {
    minAge?: number;
    maxAge?: number;
    severity?: string;
  }): Promise<ApiResponse<any[]>> {
    const backendCriteria: any = {};

    if (criteria.minAge !== undefined)
      backendCriteria.min_age = criteria.minAge;
    if (criteria.maxAge !== undefined)
      backendCriteria.max_age = criteria.maxAge;
    if (criteria.severity) backendCriteria.severity = criteria.severity;

    const response = await this.request<{
      patients: BackendPatient[];
      count: number;
    }>("/patients/filter/", {
      method: "POST",
      body: JSON.stringify(backendCriteria),
    });

    if (response.success && response.data) {
      const convertedPatients = response.data.patients.map(
        convertBackendToFrontend
      );
      return { success: true, data: convertedPatients };
    }

    return { success: false, error: response.error };
  }

  // Get test history for a patient
  async getPatientTests(patientId: string): Promise<ApiResponse<Test[]>> {
    const response = await this.request<{ tests: BackendTestEntry[] } | BackendTestEntry[]>(
      `/patients/${patientId}/tests`
    );

    if (response.success && response.data) {
      const payload = response.data;
      const testsRaw = Array.isArray(payload) ? payload : payload.tests ?? [];
      const converted = testsRaw
        .filter(Boolean)
        .map((entry) => convertBackendTestToFrontend(patientId, entry as BackendTestEntry));
      converted.sort((a, b) => b.date.getTime() - a.date.getTime());
      return { success: true, data: converted };
    }

    return { success: false, error: response.error };
  }

  // Add a test result for a patient
  async addPatientTest(
    patientId: string,
    testData: any
  ): Promise<ApiResponse<boolean>> {
    const response = await this.request<boolean>(
      `/patients/${patientId}/tests`,
      {
        method: "POST",
        body: JSON.stringify(testData),
        headers: { "Content-Type": "application/json" },
      }
    );
    return response;
  }

  async uploadVideo(formData: FormData): Promise<ApiResponse<UploadVideoResponse>> {
    return this.request<UploadVideoResponse>('/upload-video/', {
      method: 'POST',
      body: formData,
    });
  }

  async predictAndUpdateSeverity(
    patientId: string,
    sequence: number[][],
    options?: { returnAttention?: boolean; persistUpdate?: boolean }
  ): Promise<ApiResponse<BackendSeverityPrediction>> {
    const returnAttention = options?.returnAttention ?? false;
    const persistUpdate = options?.persistUpdate ?? true;
    const endpoint = `/ml/updrs/predict/patients/${encodeURIComponent(
      patientId
    )}?persist_update=${persistUpdate}`;

    return await this.request<BackendSeverityPrediction>(endpoint, {
      method: "POST",
      body: JSON.stringify({
        sequence,
        return_attention: returnAttention,
      }),
    });
  }
}

// Export singleton instance
export const apiService = new ApiService();
export default apiService;
