import { useState, useEffect, useMemo, useRef } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Upload, ArrowUpDown, CalendarClock, FileText, Loader2, Plus, Search, Stethoscope, User, UserPlus } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { useToast } from '@/hooks/use-toast';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { Patient, DoctorNoteEntry } from '@/types/patient';
import apiService, { normalizeBirthDate } from '@/services/api';
import { useApiStatus } from '@/hooks/use-api-status';
import { getSeverityColor, calculateAge } from '@/lib/utils';
import { useAuth } from '@/auth/auth-context';

// Remove mock data - will be fetched from API

type SortField = 'lastName' | 'severity' | 'lastVisit' | 'physician';

const SORT_OPTIONS: { value: SortField; label: string }[] = [
  { value: 'lastName', label: 'Last name' },
  { value: 'severity', label: 'Stage' },
  { value: 'lastVisit', label: 'Last visit' },
  { value: 'physician', label: 'Physician' },
];

const stageOrder: Record<Patient['severity'], number> = {
  'Stage 1': 1,
  'Stage 2': 2,
  'Stage 3': 3,
  'Stage 4': 4,
  'Stage 5': 5,
};

const getLatestDoctorNote = (patient: Patient): DoctorNoteEntry | null => {
  if (!patient.doctorNotesHistory || patient.doctorNotesHistory.length === 0) {
    return null;
  }

  return patient.doctorNotesHistory.reduce<DoctorNoteEntry | null>((latest, entry) => {
    if (!latest) {
      return entry;
    }

    const entryDate = entry.date instanceof Date ? entry.date : new Date(entry.date);
    const latestDate = latest.date instanceof Date ? latest.date : new Date(latest.date);

    if (Number.isNaN(entryDate.getTime())) {
      return latest;
    }

    if (Number.isNaN(latestDate.getTime())) {
      return entry;
    }

    return entryDate.getTime() > latestDate.getTime() ? entry : latest;
  }, null);
};

const resolveLastVisit = (patient: Patient): Date | null => {
  const candidate = patient.lastVisit;

  if (candidate instanceof Date && !Number.isNaN(candidate.getTime())) {
    return candidate;
  }

  const latestNote = getLatestDoctorNote(patient);
  if (!latestNote) {
    return null;
  }

  const noteDate = latestNote.date instanceof Date ? latestNote.date : new Date(latestNote.date);
  return Number.isNaN(noteDate.getTime()) ? null : noteDate;
};

const resolvePrimaryPhysician = (patient: Patient): string => {
  if (patient.primaryPhysician && patient.primaryPhysician.trim()) {
    return patient.primaryPhysician.trim();
  }

  const latestNote = getLatestDoctorNote(patient);
  const inferred = latestNote?.addedBy?.trim();
  return inferred && inferred.length > 0 ? inferred : 'Unassigned';
};

const PatientList = () => {
  const navigate = useNavigate();
  const [searchTerm, setSearchTerm] = useState('');
  const [patients, setPatients] = useState<Patient[]>([]);
  const [loading, setLoading] = useState(true);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const { toast } = useToast();
  const { isConnected, isChecking } = useApiStatus();
  const { user, logout } = useAuth();

  const currentUser = useMemo(() => {
    const fullName = user?.fullName?.trim() || 'Demo Doctor';
    const [firstName, ...rest] = fullName.split(' ');
    return {
      firstName: firstName || 'Demo',
      lastName: rest.join(' ') || 'Doctor',
      profileImage: '',
    };
  }, [user]);

  const getUserInitials = () => {
    return `${currentUser.firstName[0]}${currentUser.lastName[0]}`.toUpperCase();
  };

  const handleSignOut = () => {
    logout();
    navigate('/login');
  };

  const [sortField, setSortField] = useState<SortField>('lastName');
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('asc');
  const [csvFile, setCsvFile] = useState<File | null>(null);
  const [csvUploading, setCsvUploading] = useState(false);
  const csvFileInputRef = useRef<HTMLInputElement>(null);

  const [quickFormData, setQuickFormData] = useState({
    firstName: '',
    lastName: '',
    recordNumber: '',
    birthDate: '',
    severity: '' as Patient['severity'],
  });

  useEffect(() => {
    fetchPatients();
  }, []);

  const fetchPatients = async () => {
    setLoading(true);
    try {
      const response = await apiService.getPatients();
      console.log('PatientList API Response:', response);
      if (response.success && response.data) {
        console.log('Patient data received:', response.data);
        console.log('First patient historical data:', response.data[0]?.doctorNotesHistory, response.data[0]?.labResultsHistory);
        setPatients(response.data);
      } else {
        toast({
          title: "Error",
          description: response.error || "Failed to fetch patients",
          variant: "destructive",
        });
      }
    } catch (error) {
      toast({
        title: "Error",
        description: "Failed to connect to the server",
        variant: "destructive",
      });
    } finally {
      setLoading(false);
    }
  };

  const handleCsvUploadClick = () => {
    if(csvFileInputRef.current){
      csvFileInputRef.current.value = "";
      csvFileInputRef.current.click();
    }
  };

  const handleCsvFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0] || null;
    if (!file.name.endsWith('.csv')) {
      toast({
        title: "Invalid File Type",
        description: "Please upload a valid CSV file.",
        variant: "destructive",
      });
      return;
    }
    setCsvFile(file);
  };

  const parseCSVLine = (line: string) => {
    const result: string[] = [];
    let cur = '';
    let inQuotes = false;
    for (let i = 0; i < line.length; i++) {
      const ch = line[i];
      if (ch === '"' && line[i + 1] === '"') {
        cur += '"';
        i++; // skip escape
        continue;
      }
      if (ch === '"') {
        inQuotes = !inQuotes;
        continue;
      }
      if (ch === ',' && !inQuotes) {
        result.push(cur.trim());
        cur = '';
        continue;
      }
      cur += ch;
    }
    result.push(cur.trim());
    return result;
  };

  const normalizeHeaderName = (h: string) => {
    return h
      .toLowerCase()
      .replace(/[^a-z0-9]/g, '')
      .trim();
  }

  // Parse several common date formats and return ISO yyyy-mm-dd or null
  // ISO means ISO 8601 date format
  const parseDateToISO = (val: string): string | null => {
    if (!val) return null;
    const s = val.trim();

    // If already ISO yyyy-mm-dd
    if (/^\d{4}-\d{2}-\d{2}$/.test(s)) return s;

    // Match numeric formats like dd-mm-yyyy, dd/mm/yyyy, mm/dd/yyyy
    const m = s.match(/^(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{4})$/);
    if (m) {
      const a = Number(m[1]);
      const b = Number(m[2]);
      const y = Number(m[3]);

      let day: number;
      let month: number;

      // If first component > 12 it's day
      if (a > 12) {
        day = a; month = b;
      } else if (b > 12) {
        // If second component > 12 treat first as day
        day = a; month = b;
      } else {
        // Ambiguous: use '-' as dd-mm-yyyy heuristic, '/' as mm/dd/yyyy
        if (s.includes('-')) {
          day = a; month = b;
        } else {
          month = a; day = b;
        }
      }

      if (month < 1 || month > 12 || day < 1 || day > 31) return null;
      const mm = String(month).padStart(2, '0');
      const dd = String(day).padStart(2, '0');
      return `${y}-${mm}-${dd}`;
    }

    const d = new Date(s);
    if (!isNaN(d.getTime())) return d.toISOString().slice(0, 10);
    return null;
  };

  const headerToKey = (h:string) => {
    const n = normalizeHeaderName(h);

    if (['firstname', 'first', 'givenname', 'given'].includes(n)) return 'firstName';
    if (['lastname', 'last', 'surname', 'familyname'].includes(n)) return 'lastName';
    if (['fullname', 'name', 'fullName', 'fullname'].includes(n.toLowerCase())) return 'fullName';
    if (['birthdate', 'dob', 'dateofbirth', 'birth'].includes(n)) return 'birthDate';
    if (['height', 'ht'].includes(n)) return 'height';
    if (['weight', 'wt'].includes(n)) return 'weight';
    if (['recordnumber', 'recordno', 'record', 'id', 'patientid'].includes(n)) return 'recordNumber';
    if (['severity', 'stage', 'parkinsonseverity'].includes(n)) return 'severity';
    if (['labresults', 'lab_result', 'labs', 'lab'].includes(n)) return 'labResults';
    if (['doctornotes', 'doctornote', 'notes', 'note'].includes(n)) return 'doctorNotes';
    return n; // fallback: keep original normalized header
  }

  const normalizeSeverity = (val: string | undefined | null) => {
    if (!val) return '';
    const v = val.trim();
    const num = parseInt(v, 10);

    if (!isNaN(num) && num >= 1 && num <= 5) return `Stage ${num}`;

    const m = v.match(/([sS]tage)[_\-\s]?([1-5])/);
    if (m) return `Stage ${m[2]}`;

    const m2 = v.match(/^[Ss]tage\s*[1-5]$/);

    if (m2) return v.startsWith('Stage') ? v : `Stage ${v.replace(/\D/g, '')}`;

    const low = ['mild', 'low', 'stage1', 'stage_1'];
    const med = ['moderate', 'medium', 'stage3', 'stage_3'];
    const high = ['severe', 'high', 'stage5', 'stage_5'];
    const lower = v.toLowerCase();
    if (low.includes(lower)) return 'Stage 1';
    if (med.includes(lower)) return 'Stage 3';
    if (high.includes(lower)) return 'Stage 5';
    return v;
  };

  const processCsvFile = async () => {
    if (!csvFile) return;
    setCsvUploading(true);
    try {
      const text = await csvFile.text();
      const lines = text.split(/\r?\n/).filter(l => l.trim().length > 0);
      if (lines.length < 2) {
        toast({
          title: 'Empty CSV',
          description: 'CSV must contain a header and at least one data row.',
          variant: 'destructive',
        });
        setCsvUploading(false);
        return;
      }

      const rawHeader = parseCSVLine(lines[0]);
      const headerMap: Record<number, string> = {};
      rawHeader.forEach((h, idx) => {
        headerMap[idx] = headerToKey(h);
      });

      const rows = lines.slice(1);
      const toCreate: any[] = [];
      for (const row of rows) {
        const cols = parseCSVLine(row);
        if (cols.every(c => c === '')) continue;

        const item: any = {
          firstName: '',
          lastName: '',
          recordNumber: '',
          birthDate: '',
          height: '',
          weight: '',
          labResults: '{}',
          doctorNotes: '',
          severity: '',
        };

        for (let i = 0; i < cols.length; i++) {
          const key = headerMap[i];
          const val = cols[i] ?? '';
          if (!key) continue;
          switch (key) {
            case 'firstName':
              item.firstName = val;
              break;
            case 'lastName':
              item.lastName = val;
              break;
            case 'fullName':
              {
                const parts = val.split(/\s+/);
                item.firstName = parts.shift() || '';
                item.lastName = parts.join(' ') || '';
              }
              break;
            case 'birthDate':
              {
                // try to normalize common date formats to yyyy-mm-dd
                const iso = parseDateToISO(val);
                if (iso) {
                  item.birthDate = iso;
                } else {
                  item.birthDate = val || '';
                }
              }
              break;
            case 'height':
              item.height = val;
              break;
            case 'weight':
              item.weight = val;
              break;
            case 'recordNumber':
              item.recordNumber = val;
              break;
            case 'severity':
              item.severity = normalizeSeverity(val);
              break;
            case 'labResults':
              try {
                item.labResults = JSON.stringify(JSON.parse(val));
              } catch {
                item.labResults = JSON.stringify({ notes: val });
              }
              break;
            case 'doctorNotes':
              item.doctorNotes = val;
              break;
            default:
              // unknown header, ignores it
              break;
          }
        }

        // Default values for missing fields
        if (!item.firstName && !item.lastName) {
          item.firstName = 'Unknown';
          item.lastName = 'Patient';
        }
        if (!item.recordNumber) {
          item.recordNumber = `csv-${Date.now()}-${Math.floor(Math.random() * 1000)}`;
        }
        if (!item.height) item.height = '170 cm';
        if (!item.weight) item.weight = '70 kg';
        if (!item.labResults) item.labResults = JSON.stringify({});
        if (!item.doctorNotes) item.doctorNotes = 'n/a';
        if (!item.severity) item.severity = 'Stage 1';
        if (!item.birthDate) item.birthDate = '';
        toCreate.push(item);
      }

      if (toCreate.length === 0) {
        toast({
          title: 'No valid rows',
          description: 'No valid patient rows found in CSV.',
          variant: 'destructive',
        });
        setCsvUploading(false);
        return;
      }

      let successCount = 0;
      let failCount = 0;
      for (const p of toCreate) {
        try {
          const response = await apiService.createPatient(p);
          if (response.success && response.data) {
            setPatients(prev => [...prev, response.data]);
            successCount++;
          } else {
            failCount++;
            console.error('Create patient failed response:', response);
          }
        } catch (err) {
          failCount++;
          console.error('Create patient error:', err);
        }
      }

      toast({
        title: 'CSV Upload Complete',
        description: `Imported ${successCount} patients. ${failCount} failures.`,
      });

      setCsvFile(null);
      setIsModalOpen(false);
    } catch (error) {
      console.error('Error processing CSV:', error);
      toast({
        title: "Error",
        description: "Failed to read the CSV file.",
        variant: "destructive",
      });
    } finally {
      setCsvUploading(false);
    }
  };

  const filteredPatients = patients.filter(patient =>
    `${patient.firstName} ${patient.lastName}`.toLowerCase().includes(searchTerm.toLowerCase()) ||
    patient.recordNumber.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const handleSortFieldChange = (value: SortField) => {
    setSortField(value);
    setSortDirection('asc');
  };

  const toggleSortDirection = () => {
    setSortDirection(prev => (prev === 'asc' ? 'desc' : 'asc'));
  };

  const sortedPatients = [...filteredPatients].sort((a, b) => {
    const direction = sortDirection === 'asc' ? 1 : -1;

    switch (sortField) {
      case 'lastName':
        return (
          direction *
          a.lastName.localeCompare(b.lastName, undefined, {
            sensitivity: 'base',
          })
        );
      case 'severity':
        return direction * (stageOrder[a.severity] - stageOrder[b.severity]);
      case 'lastVisit': {
        const dateA = resolveLastVisit(a);
        const dateB = resolveLastVisit(b);
        if (!dateA && !dateB) {
          return 0;
        }
        if (!dateA) {
          return 1;
        }
        if (!dateB) {
          return -1;
        }
        return direction * (dateA.getTime() - dateB.getTime());
      }
      case 'physician': {
        const physicianA = resolvePrimaryPhysician(a);
        const physicianB = resolvePrimaryPhysician(b);
        const isUnassignedA = physicianA === 'Unassigned';
        const isUnassignedB = physicianB === 'Unassigned';

        if (isUnassignedA && isUnassignedB) {
          return 0;
        }
        if (isUnassignedA) {
          return 1;
        }
        if (isUnassignedB) {
          return -1;
        }

        return (
          direction *
          physicianA.localeCompare(physicianB, undefined, {
            sensitivity: 'base',
          })
        );
      }
      default:
        return 0;
    }
  });

  const handleQuickFormChange = (field: string, value: string) => {
    if (field === 'birthDate') {
      const normalized = normalizeBirthDate(value);
      setQuickFormData(prev => ({ ...prev, [field]: normalized || value }));
      return;
    }
    setQuickFormData(prev => ({ ...prev, [field]: value }));
  };

  const handleQuickSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    // Validate required fields
    if (!quickFormData.firstName || !quickFormData.lastName || !quickFormData.recordNumber || !quickFormData.birthDate || !quickFormData.severity) {
      toast({
        title: "Validation Error",
        description: "Please fill in all required fields.",
        variant: "destructive",
      });
      return;
    }

    const normalizedBirthDate = normalizeBirthDate(quickFormData.birthDate);
    if (!normalizedBirthDate) {
      toast({
        title: "Invalid Birthdate",
        description: "Enter a valid date (e.g., 1980-05-12).",
        variant: "destructive",
      });
      return;
    }

    // Create new patient data
    const newPatientData = {
      firstName: quickFormData.firstName,
      lastName: quickFormData.lastName,
      recordNumber: quickFormData.recordNumber,
      birthDate: normalizedBirthDate,
      height: '170 cm', // Default values for quick add
      weight: '70 kg',
      labResults: '{}',
      doctorNotes: '',
      severity: quickFormData.severity,
      createdAt: new Date(),
      updatedAt: new Date(),
    };

    try {
      console.log('Creating patient with data:', newPatientData);
      const response = await apiService.createPatient(newPatientData);
      console.log('API response:', response);
      
      if (response.success && response.data) {
        setPatients(prev => [...prev, response.data]);
        setIsModalOpen(false);
        setQuickFormData({
          firstName: '',
          lastName: '',
          recordNumber: '',
          birthDate: '',
          severity: '' as Patient['severity'],
        });

        toast({
          title: "Patient Added",
          description: `${newPatientData.firstName} ${newPatientData.lastName} has been added successfully.`,
        });
      } else {
        toast({
          title: "Error",
          description: response.error || "Failed to add patient",
          variant: "destructive",
        });
      }
    } catch (error) {
      console.error('Error creating patient:', error);
      toast({
        title: "Error",
        description: "Failed to connect to the server",
        variant: "destructive",
      });
    }
  };

  

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <div className="border-b bg-card shadow-card">
        <div className="container mx-auto px-6 py-6">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-3xl font-bold text-foreground">Patient Management</h1>
              <p className="text-muted-foreground mt-1">Parkinson's Artificial Intelligence Diagnosis Tool</p>
              {!isChecking && (
                <div className="flex items-center mt-2">
                  <div className={`w-2 h-2 rounded-full mr-2 ${isConnected ? 'bg-green-500' : 'bg-red-500'}`} />
                  <span className="text-xs text-muted-foreground">
                    {isConnected ? 'Connected to backend' : 'Backend disconnected'}
                  </span>
                </div>
              )}
            </div>
            <div className="flex flex-col items-end space-y-3">
              {/* Profile Avatar */}
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <button
                    type="button"
                    className="group relative"
                    aria-label="Open profile menu"
                  >
                    <Avatar className="h-10 w-10 cursor-pointer ring-2 ring-transparent hover:ring-primary transition-all">
                      <AvatarImage src={currentUser.profileImage} alt="Profile" />
                      <AvatarFallback className="bg-primary text-primary-foreground text-sm">
                        {getUserInitials()}
                      </AvatarFallback>
                    </Avatar>
                    <div className="absolute -bottom-8 right-0 bg-popover text-popover-foreground text-xs px-2 py-1 rounded shadow-md opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap pointer-events-none">
                      Account Menu
                    </div>
                  </button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="w-48">
                  <DropdownMenuLabel>{currentUser.firstName} {currentUser.lastName}</DropdownMenuLabel>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem onClick={() => navigate('/profile')}>
                    Profile
                  </DropdownMenuItem>
                  <DropdownMenuItem onClick={handleSignOut}>
                    Sign out
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>

              {/* Action Buttons */}
              <div className="flex items-center space-x-3">
                {/* Upload Modal */}
                <Dialog open={isModalOpen} onOpenChange={setIsModalOpen}>
                  <DialogTrigger asChild>
                    <Button variant="outline" className="border-primary text-primary hover:bg-primary hover:text-primary-foreground">
                      <UserPlus className="mr-2 h-4 w-4" />
                      Upload Patient
                    </Button>
                  </DialogTrigger>
                  <DialogContent className="w-full sm:max-w-2xl">
                    <DialogHeader>
                      <DialogTitle>Upload Patients from CSV</DialogTitle>
                    </DialogHeader>
                    <div className="space-y-6 py-4">
                      {/* File Upload Section */}
                      <div className="space-y-4">
                        <div className="flex flex-col items-center justify-center border-2 border-dashed border-muted-foreground/25 rounded-lg p-8 hover:border-primary/50 transition-colors">
                          <Upload className="h-12 w-12 text-muted-foreground mb-4" />
                          <Button 
                            type="button"
                            variant="outline" 
                            onClick={handleCsvUploadClick}
                            className="mb-2"
                          >
                            <Upload className="mr-2 h-4 w-4" />
                            {csvFile ? 'Change CSV File' : 'Select CSV File'}
                          </Button>
                          <p className="text-sm text-muted-foreground">
                            Upload a CSV file containing patient information
                          </p>
                          <input 
                            ref={csvFileInputRef}
                            type="file"
                            accept=".csv"
                            onChange={handleCsvFileChange}
                            className="hidden"
                          />
                        </div>

                        {/* File Selected Message */}
                        {csvFile && (
                          <div className="bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg p-4">
                            <div className="flex items-center gap-2">
                              <div className="h-2 w-2 rounded-full bg-green-500" />
                              <p className="text-sm font-medium text-green-900 dark:text-green-100">
                                File uploaded: <span className="font-semibold">{csvFile.name}</span>
                              </p>
                            </div>
                            <p className="text-xs text-green-700 dark:text-green-300 mt-1 ml-4">
                              Size: {(csvFile.size / 1024).toFixed(2)} KB
                            </p>
                          </div>
                        )}

                        {/* CSV Format Info */}
                        <div className="bg-muted/50 rounded-lg p-4">
                          <h4 className="text-sm font-semibold mb-2">CSV Format Requirements:</h4>
                          <ul className="text-xs text-muted-foreground space-y-1">
                            <li>• Headers: firstName, lastName, birthDate, recordNumber, severity</li>
                            <li>• Severity: Use "Stage 1" through "Stage 5" or numbers 1-5</li>
                            <li>• Birth Date: Use YYYY-MM-DD format (e.g., 1980-05-12)</li>
                            <li>• Optional fields: height, weight, labResults, doctorNotes</li>
                          </ul>
                        </div>
                      </div>

                      {/* Action Buttons */}
                      <div className="flex justify-end gap-3">
                        <Button
                          type="button"
                          variant="outline"
                          onClick={() => {
                            setIsModalOpen(false);
                            setCsvFile(null);
                          }}
                        >
                          Cancel
                        </Button>
                        <Button
                          type="button"
                          onClick={processCsvFile}
                          disabled={!csvFile || csvUploading}
                        >
                          {csvUploading ? (
                            <>
                              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                              Uploading...
                            </>
                          ) : (
                            <>
                              <Upload className="mr-2 h-4 w-4" />
                              Import Patients
                            </>
                          )}
                        </Button>
                      </div>
                    </div>
                  </DialogContent>
                </Dialog>

                {/* Full Form Link */}
                <Link to="/patient-form">
                  <Button className="bg-primary hover:bg-primary-hover text-primary-foreground">
                    <Plus className="mr-2 h-4 w-4" />
                    Detailed Form
                  </Button>
                </Link>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Search and Content */}
      <div className="container mx-auto px-6 py-8">
        {/* Search & Sort */}
        <div className="mb-8 flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div className="relative w-full max-w-md md:w-auto">
            <Search className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Search patients by name or record number..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="pl-10 w-full md:w-[380px]"
            />
          </div>
          <div className="flex w-full flex-col gap-3 sm:w-auto sm:flex-row sm:items-center">
            <div className="flex items-center gap-2">
              <span className="text-sm text-muted-foreground">Sort by</span>
              <Select
                value={sortField}
                onValueChange={(value) => handleSortFieldChange(value as SortField)}
              >
                <SelectTrigger className="w-[160px]">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {SORT_OPTIONS.map((option) => (
                    <SelectItem key={option.value} value={option.value}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={toggleSortDirection}
              className="flex items-center gap-2 self-start sm:self-auto"
            >
              <ArrowUpDown className="h-4 w-4" />
              {sortDirection === 'asc' ? 'Asc' : 'Desc'}
            </Button>
          </div>
        </div>

        {/* Patient Cards */}
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="h-8 w-8 animate-spin text-primary" />
            <span className="ml-2 text-muted-foreground">Loading patients...</span>
          </div>
        ) : (
          <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
            {sortedPatients.map((patient) => {
              const lastVisit = resolveLastVisit(patient);
              const primaryPhysician = resolvePrimaryPhysician(patient);
              const latestNote = getLatestDoctorNote(patient);
              const noteToDisplay = latestNote?.note || patient.doctorNotes;
              const trimmedNote = noteToDisplay && noteToDisplay.length > 80
                ? `${noteToDisplay.substring(0, 80)}...`
                : noteToDisplay ?? '';
              const latestNoteDate = latestNote
                ? (latestNote.date instanceof Date ? latestNote.date : new Date(latestNote.date))
                : null;

              return (
                <Link key={patient.id} to={`/patient/${patient.id}`}>
                  <Card className="hover:shadow-medical transition-all duration-200 hover:scale-[1.02] cursor-pointer">
                    <CardHeader className="pb-3">
                      <div className="flex items-start justify-between">
                        <div className="flex items-center space-x-3">
                          <div className="p-2 rounded-full bg-medical-light">
                            <User className="h-5 w-5 text-medical-blue" />
                          </div>
                          <div>
                            <CardTitle className="text-lg">
                              {patient.firstName} {patient.lastName}
                            </CardTitle>
                            <p className="text-sm text-muted-foreground">
                              Record: {patient.recordNumber}
                            </p>
                          </div>
                        </div>
                        <Badge className={getSeverityColor(patient.severity)}>
                          {patient.severity}
                        </Badge>
                      </div>
                    </CardHeader>
                    <CardContent>
                      <div className="space-y-3">
                        <div className="flex items-center text-sm text-muted-foreground">
                          <FileText className="mr-2 h-4 w-4" />
                          Age: {patient.birthDate ? `${calculateAge(patient.birthDate) ?? 'Unknown'} years` : 'N/A'}
                        </div>
                        <div className="flex items-center text-sm text-muted-foreground">
                          <CalendarClock className="mr-2 h-4 w-4" />
                          Last visit: {lastVisit ? lastVisit.toLocaleDateString() : 'N/A'}
                        </div>
                        <div className="flex items-center text-sm text-muted-foreground">
                          <Stethoscope className="mr-2 h-4 w-4" />
                          Physician: {primaryPhysician}
                        </div>
                        {noteToDisplay ? (
                          <div className="bg-muted/50 border-l-4 border-medical-blue p-3 rounded-md">
                            <div className="flex items-start gap-2">
                              <FileText className="h-4 w-4 text-medical-blue mt-0.5 flex-shrink-0" />
                              <div className="flex-1">
                                <p className="text-sm font-medium text-foreground">Latest Note:</p>
                                <p className="text-sm text-muted-foreground mt-1">"{trimmedNote}"</p>
                                {(latestNoteDate || latestNote?.addedBy) && (
                                  <p className="text-xs text-muted-foreground/70 mt-2">
                                    {latestNoteDate ? latestNoteDate.toLocaleDateString() : 'Unknown date'}
                                    {latestNote?.addedBy ? ` by ${latestNote.addedBy}` : ''}
                                  </p>
                                )}
                              </div>
                            </div>
                          </div>
                        ) : (
                          <div className="bg-muted/30 p-3 rounded-md border border-dashed">
                            <div className="flex items-center gap-2">
                              <FileText className="h-4 w-4 text-muted-foreground/50" />
                              <p className="text-sm text-muted-foreground/70 italic">
                                No doctor's notes available
                              </p>
                            </div>
                          </div>
                        )}
                      </div>
                    </CardContent>
                  </Card>
                </Link>
              );
            })}
          </div>
        )}

        {!loading && sortedPatients.length === 0 && (
          <div className="text-center py-12">
            <User className="mx-auto h-12 w-12 text-muted-foreground mb-4" />
            <h3 className="text-lg font-medium text-foreground mb-2">No patients found</h3>
            <p className="text-muted-foreground mb-4">
              {searchTerm ? 'Try adjusting your search terms.' : 'Get started by adding your first patient.'}
            </p>
            <Link to="/patient-form">
              <Button>
                <Plus className="mr-2 h-4 w-4" />
                Add First Patient
              </Button>
            </Link>
          </div>
        )}
      </div>
    </div>
  );
};

export default PatientList;
