export interface LabResultEntry {
  id: string;
  date: Date;
  results: string;
  addedBy?: string;
}

export interface DoctorNoteEntry {
  id: string;
  date: Date;
  note: string;
  addedBy?: string;
}

export interface Patient {
  id: string;
  firstName: string;
  lastName: string;
  recordNumber: string;
  birthDate: string;
  height: string;
  weight: string;
  labResults: string; // Keep for backward compatibility
  doctorNotes: string; // Keep for backward compatibility
  labResultsHistory: LabResultEntry[];
  doctorNotesHistory: DoctorNoteEntry[];
  severity: 'Stage 1' | 'Stage 2' | 'Stage 3' | 'Stage 4' | 'Stage 5';
  lastVisit?: Date | null;
  primaryPhysician?: string | null;
  createdAt: Date;
  updatedAt: Date;
}

export interface TestIndicator {
  color: 'success' | 'warning' | 'destructive' | 'muted';
  label: string;
  description: string;
}

export interface PersistedDtwAnalysis {
  session_id?: string | null;
  distance_pos?: number | null;
  distance_amp?: number | null;
  distance_spd?: number | null;
  avg_step_pos?: number | null;
  avg_step_cost?: number | null;
  similarity_overall?: number | null;
  similarity_pos?: number | null;
  similarity_amp?: number | null;
  similarity_spd?: number | null;
  distance?: number | null;
  similarity?: number | null;
}

export interface PersistedMlPrediction {
  predicted_updrs_stage: number;
  probabilities: Record<string, number>;
  severity: string;
  severity_stage: number;
  prediction: string;
  confidence: number;
  model_version?: string | null;
  preprocessing_version?: string | null;
  generated_at?: string | null;
}

export interface PersistedAnomalyChunk {
  start: string;
  end: string;
  confidence: number;
}

export interface PersistedAnomalyReport {
  chunks: PersistedAnomalyChunk[];
  model_version?: string | null;
  generated_at?: string | null;
}

export interface TestAnalysisSnapshot {
  dtwMetrics?: PersistedDtwAnalysis | null;
  mlPrediction?: PersistedMlPrediction | null;
  anomalyReport?: PersistedAnomalyReport | null;
}

export interface Test {
  id: string;
  patientId: string;
  name: string;
  type: 'stand-and-sit' | 'finger-tapping' | 'fist-open-close' | 'unknown';
  date: Date;
  status: 'completed' | 'in-progress' | 'pending';
  videoUrl?: string;
  recordingUrl?: string;
  recordingFile?: string;
  summaryAvailable?: boolean;
  frameCount?: number | null;
  fps?: number | null;
  similarity?: number | null;
  distance?: number | null;
  dtwSessionId?: string | null;
  indicator?: TestIndicator;
  analysis?: TestAnalysisSnapshot | null;
  results?: TestResults;
}

export interface TestResults {
  duration: number;
  score: number;
  keypoints: Keypoint[];
  analysis: string;
}

export interface Keypoint {
  x: number;
  y: number;
  confidence: number;
  timestamp: number;
}

export const AVAILABLE_TESTS = [
  { id: 'stand-and-sit', name: 'Stand and Sit Test', description: 'Measures motor function through standing and sitting movements' },
  { id: 'finger-tapping', name: 'Finger Tapping Test', description: 'Measures rapid finger tapping for motor speed and coordination' },
  { id: 'fist-open-close', name: 'Fist Open and Close Test', description: 'Assesses hand opening and closing cycles for bradykinesia' }
] as const;
