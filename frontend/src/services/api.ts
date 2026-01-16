const API_BASE_URL = 'http://localhost:8000'; //not using docker if you are swich back to 8000

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
interface BackendPatient {
  patient_id: string;
  name: string;
  birthDate: string;
  height: number;
  weight: number;
  lab_results: Record<string, any>;
  doctors_notes: string;
  severity: string;
  lab_results_history?: Array<{
    id: string;
    date: string;
    results: string;
    added_by: string;
  }>;
  doctors_notes_history?: Array<{
    id: string;
    date: string;
    note: string;
    added_by: string;
  }>;
}

interface BackendPatientCreate {
  name: string;
  age: number;
  birthDate: string;
  height: string;
  weight: string;
  lab_results?: Record<string, any>;
  doctors_notes?: string;
  severity: string;
}

interface BackendPatientUpdate {
  name?: string;
  age?: number;
  birthDate?: string;
  height?: string;
  weight?: string;
  lab_results?: Record<string, any>;
  doctors_notes?: string;
  severity?: string;
}

interface ApiResponse<T> {
  success: boolean;
  data?: T;
  error?: string;
}

// Convert backend patient to frontend patient
const convertBackendToFrontend = (backendPatient: BackendPatient) => {
  // Handle undefined or null name
  const name = backendPatient.name || '';
  const nameParts = name.split(' ');
  const firstName = nameParts[0] || '';
  const lastName = nameParts.slice(1).join(' ') || '';
  const normalizedBirthDate = normalizeBirthDate(backendPatient.birthDate);
  const doctorNotesHistoryRaw = backendPatient.doctors_notes_history || [];
  const labResultsHistoryRaw = backendPatient.lab_results_history || [];

  const latestDoctorNote = doctorNotesHistoryRaw
    .map(entry => ({
      ...entry,
      parsedDate: new Date(entry.date)
    }))
    .sort((a, b) => (b.parsedDate?.getTime() || 0) - (a.parsedDate?.getTime() || 0))[0];

  const lastVisit = latestDoctorNote?.parsedDate ?? null;
  const primaryPhysician = latestDoctorNote?.added_by?.trim() || null;
  
  // Debug logging (commented out)
  // console.log('Converting backend patient:', backendPatient.patient_id);
  // console.log('Doctor notes history:', backendPatient.doctors_notes_history);
  // console.log('Legacy doctor notes:', backendPatient.doctors_notes);
  
  return {
    id: backendPatient.patient_id || '',
    firstName,
    lastName,
    recordNumber: backendPatient.patient_id || '', // Using patient_id as record number
  birthDate: normalizedBirthDate || backendPatient.birthDate || '',
    height: `${backendPatient.height || 0} cm`,
    weight: `${backendPatient.weight || 0} kg`,
    labResults: JSON.stringify(backendPatient.lab_results || {}),
    doctorNotes: backendPatient.doctors_notes || '',
    labResultsHistory: labResultsHistoryRaw.map(entry => ({
      id: entry.id,
      date: new Date(entry.date),
      results: entry.results,
      addedBy: entry.added_by
    })),
    doctorNotesHistory: doctorNotesHistoryRaw.map(entry => ({
      id: entry.id,
      date: new Date(entry.date),
      note: entry.note,
      addedBy: entry.added_by
    })),
    severity: mapSeverity(backendPatient.severity || 'low'),
    lastVisit,
    primaryPhysician,
    createdAt: lastVisit ?? new Date(), // Backend doesn't provide this, approximated from last visit
    updatedAt: lastVisit ?? new Date(), // Backend doesn't provide this, approximated from last visit
  };
};

// Convert frontend patient to backend format
const convertFrontendToBackend = (frontendPatient: any): BackendPatientCreate => {
  const fullName = `${frontendPatient.firstName || ''} ${frontendPatient.lastName || ''}`.trim();
  
  const heightStr = (frontendPatient.height || '').replace(/[^\d.]/g, '');
  const weightStr = (frontendPatient.weight || '').replace(/[^\d.]/g, '');
  const normalizedBirthDate = normalizeBirthDate(frontendPatient.birthDate);
  
  let parsedLabResults: Record<string, any> = {};
  if (frontendPatient.labResults) {
    try {
      parsedLabResults = JSON.parse(frontendPatient.labResults);
    } catch {
      parsedLabResults = { notes: frontendPatient.labResults };
    }
  }

  return {
    name: fullName,
    age: calculateAge(normalizedBirthDate || frontendPatient.birthDate), // Use your existing function
    birthDate: normalizedBirthDate || frontendPatient.birthDate,
    height: heightStr || '0',
    weight: weightStr || '0',
    lab_results: parsedLabResults,
    doctors_notes: frontendPatient.doctorNotes || '',
    severity: mapSeverityToBackend(frontendPatient.severity),
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
      
      const response = await fetch(url, {
        headers: {
          'Content-Type': 'application/json',
          ...options.headers,
        },
        ...options,
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        console.error('API Error Response:', errorData);
        console.error('Error Response Type:', typeof errorData);
        console.error('Error Detail Type:', typeof errorData.detail);
        console.error('Full Error Object:', JSON.stringify(errorData, null, 2));
        
        let errorMessage = `HTTP error! status: ${response.status}`;
        
        if (errorData.detail) {
          if (Array.isArray(errorData.detail)) {
            // Handle validation error array
            errorMessage = errorData.detail.map((err: any) => {
              const field = err.loc?.join('.') || 'field';
              return `${field}: ${err.msg}`;
            }).join(', ');
          } else if (typeof errorData.detail === 'object') {
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
      console.error('API request failed:', error);
      return {
        success: false,
        error: error instanceof Error ? error.message : 'Unknown error occurred',
      };
    }
  }

  // Get all patients
  async getPatients(skip: number = 0, limit: number = 100): Promise<ApiResponse<any[]>> {
    const response = await this.request<{ patients: BackendPatient[]; total: number }>(
      `/patients/?skip=${skip}&limit=${limit}`
    );

    if (response.success && response.data) {
      const convertedPatients = response.data.patients.map(convertBackendToFrontend);
      return { success: true, data: convertedPatients };
    }

    return { success: false, error: response.error };
  }

  // Get single patient
  async getPatient(patientId: string): Promise<ApiResponse<any>> {
    const response = await this.request<{ patient: BackendPatient } | BackendPatient>(`/patients/${patientId}`);

    if (response.success && response.data) {
      // Handle the nested patient structure from the backend
      const patientData = 'patient' in response.data ? response.data.patient : response.data;
      const convertedPatient = convertBackendToFrontend(patientData);
      return { success: true, data: convertedPatient };
    }

    return { success: false, error: response.error };
  }

  // Create new patient
  async createPatient(patientData: any): Promise<ApiResponse<any>> {
    const backendData = convertFrontendToBackend(patientData);
    
    const response = await this.request<BackendPatient>('/patients/', {
      method: 'POST',
      body: JSON.stringify(backendData),
    });

    if (response.success && response.data) {
      const convertedPatient = convertBackendToFrontend(response.data);
      return { success: true, data: convertedPatient };
    }

    return response;
  }

  // Update patient
  async updatePatient(patientId: string, updateData: any): Promise<ApiResponse<any>> {
    const backendData: BackendPatientUpdate = {};
    
    console.log('Update patient input data:', updateData);
    
    if (updateData.firstName || updateData.lastName) {
      const fullName = `${updateData.firstName || ''} ${updateData.lastName || ''}`.trim();
      backendData.name = fullName;
    }
    
    if (updateData.birthDate !== undefined) {
      const normalized = normalizeBirthDate(updateData.birthDate);
      backendData.birthDate = normalized || updateData.birthDate;
      backendData.age = calculateAge(normalized || updateData.birthDate); // Use your existing function
    }
    
    if (updateData.height) {
      const heightStr = updateData.height.replace(/[^\d.]/g, '');
      backendData.height = heightStr || '0';
    }
    if (updateData.weight) {
      const weightStr = updateData.weight.replace(/[^\d.]/g, '');
      backendData.weight = weightStr || '0';
    }
    if (updateData.labResults) {
      try {
        backendData.lab_results = JSON.parse(updateData.labResults);
      } catch (error) {
        console.error('Error parsing labResults:', error);
        backendData.lab_results = { notes: updateData.labResults };
      }
    }
    if (updateData.doctorNotes !== undefined) backendData.doctors_notes = updateData.doctorNotes;
    if (updateData.severity) {
      const mappedSeverity = mapSeverityToBackend(updateData.severity);
      console.log('Severity mapping:', updateData.severity, '->', mappedSeverity);
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

    const response = await this.request<BackendPatient>(`/patients/${patientId}`, {
      method: 'PUT',
      body: JSON.stringify(backendData),
    });

    if (response.success && response.data) {
      const convertedPatient = convertBackendToFrontend(response.data);
      return { success: true, data: convertedPatient };
    }

    return response;
  }

  // Delete patient
  async deletePatient(patientId: string): Promise<ApiResponse<boolean>> {
    return await this.request<boolean>(`/patients/${patientId}`, {
      method: 'DELETE',
    });
  }

  // Search patients
  async searchPatients(query: string): Promise<ApiResponse<any[]>> {
    const response = await this.request<{ patients: BackendPatient[]; count: number }>(
      `/patients/search/${encodeURIComponent(query)}`
    );

    if (response.success && response.data) {
      const convertedPatients = response.data.patients.map(convertBackendToFrontend);
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
    
    if (criteria.minAge !== undefined) backendCriteria.min_age = criteria.minAge;
    if (criteria.maxAge !== undefined) backendCriteria.max_age = criteria.maxAge;
    if (criteria.severity) backendCriteria.severity = mapSeverityToBackend(criteria.severity);

    const response = await this.request<{ patients: BackendPatient[]; count: number }>(
      '/patients/filter/',
      {
        method: 'POST',
        body: JSON.stringify(backendCriteria),
      }
    );

    if (response.success && response.data) {
      const convertedPatients = response.data.patients.map(convertBackendToFrontend);
      return { success: true, data: convertedPatients };
    }

    return { success: false, error: response.error };
  }

  // Get test history for a patient
  async getPatientTests(patientId: string): Promise<ApiResponse<any[]>> {
    const response = await this.request<{ tests: any }>(`/patients/${patientId}/tests`);
    if (response.success && response.data) {
      // Optionally, map/convert test data here
      return { success: true, data: response.data.tests };
    }
    return { success: false, error: response.error };
  }

  // Add a test result for a patient
  async addPatientTest(patientId: string, testData: any): Promise<ApiResponse<boolean>> {
    const response = await this.request<boolean>(`/patients/${patientId}/tests`, {
      method: 'POST',
      body: JSON.stringify(testData),
      headers: { 'Content-Type': 'application/json' },
    });
    return response;
  }
}

// Export singleton instance
export const apiService = new ApiService();
export default apiService;