import { useState, useEffect, useMemo, useRef, useCallback } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Upload, ArrowUpDown, CalendarClock, CheckSquare, FileText, Loader2, Plus, Search, Square, Stethoscope, Trash2, User, UserPlus } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { useToast } from '@/hooks/use-toast';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { Patient, DoctorNoteEntry } from '@/types/patient';
import { createPatient, deletePatient, getPatients } from '@/services/patients';
import { normalizeBirthDate } from '@/services/patient-mappers';
import { useApiStatus } from '@/hooks/use-api-status';
import { getSeverityColor, calculateAge } from '@/lib/utils';
import { useAuth } from '@/auth/auth-context';
import {
  PatientCard,
  PatientCsvImportDialog,
  PatientListControls,
  PatientQuickAddDialog,
} from '@/components/patient-list/PatientListSections';

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

type CsvPatientDraft = {
  firstName: string;
  lastName: string;
  birthDate: string;
  height: string;
  weight: string;
  labResults: string;
  doctorNotes: string;
  severity: string;
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
  const [isQuickAddOpen, setIsQuickAddOpen] = useState(false);
  const [selectionMode, setSelectionMode] = useState(false);
  const [selectedPatientIds, setSelectedPatientIds] = useState<string[]>([]);
  const [deletingPatients, setDeletingPatients] = useState(false);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);

  const [quickFormData, setQuickFormData] = useState({
    firstName: '',
    lastName: '',
    birthDate: '',
    severity: '' as Patient['severity'],
  });

  const fetchPatients = useCallback(async () => {
    setLoading(true);
    try {
      const response = await getPatients();
      if (response.success && response.data) {
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
  }, [toast]);

  useEffect(() => {
    void fetchPatients();
  }, [fetchPatients]);

  const handleCsvUploadClick = () => {
    if(csvFileInputRef.current){
      csvFileInputRef.current.value = "";
      csvFileInputRef.current.click();
    }
  };

  const toggleSelectionMode = () => {
    setSelectionMode((prev) => {
      if (prev) {
        setSelectedPatientIds([]);
      }
      return !prev;
    });
  };

  const togglePatientSelection = (patientId: string) => {
    setSelectedPatientIds((prev) =>
      prev.includes(patientId)
        ? prev.filter((id) => id !== patientId)
        : [...prev, patientId]
    );
  };

  const handleDeleteSelected = async () => {
    if (selectedPatientIds.length === 0) {
      toast({
        title: 'No Patients Selected',
        description: 'Select at least one patient to delete.',
        variant: 'destructive',
      });
      return;
    }

    setDeleteDialogOpen(true);
  };

  const confirmDeleteSelected = async () => {
    setDeleteDialogOpen(false);

    setDeletingPatients(true);
    const failedIds: string[] = [];
    let successCount = 0;

    for (const patientId of selectedPatientIds) {
      try {
        const response = await deletePatient(patientId);
        if (response.success) {
          successCount += 1;
        } else {
          failedIds.push(patientId);
        }
      } catch {
        failedIds.push(patientId);
      }
    }

    const deletedIds = selectedPatientIds.filter((id) => !failedIds.includes(id));
    if (deletedIds.length > 0) {
      setPatients((prev) => prev.filter((patient) => !deletedIds.includes(patient.id)));
    }

    setSelectedPatientIds(failedIds);
    if (failedIds.length === 0) {
      setSelectionMode(false);
    }

    toast({
      title: failedIds.length === 0 ? 'Patients Deleted' : 'Delete Completed With Issues',
      description:
        failedIds.length === 0
          ? `Deleted ${successCount} patient${successCount === 1 ? '' : 's'}.`
          : `Deleted ${successCount} patient${successCount === 1 ? '' : 's'}. ${failedIds.length} failed.`,
      variant: failedIds.length === 0 ? 'default' : 'destructive',
    });

    setDeletingPatients(false);
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
    const m = s.match(/^(\d{1,2})[/-](\d{1,2})[/-](\d{4})$/);
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
      const toCreate: CsvPatientDraft[] = [];
      for (const row of rows) {
        const cols = parseCSVLine(row);
        if (cols.every(c => c === '')) continue;

        const item: CsvPatientDraft = {
          firstName: '',
          lastName: '',
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
          const response = await createPatient(p);
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
    if (!quickFormData.firstName || !quickFormData.lastName || !quickFormData.birthDate || !quickFormData.severity) {
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
      const response = await createPatient(newPatientData);
      
      if (response.success && response.data) {
        setPatients(prev => [...prev, response.data]);
        setIsQuickAddOpen(false);
        setQuickFormData({
          firstName: '',
          lastName: '',
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
                    {isConnected ? 'Backend reachable' : 'Backend unavailable'}
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
                <PatientCsvImportDialog
                  isOpen={isModalOpen}
                  onOpenChange={(open) => {
                    setIsModalOpen(open);
                    if (!open) {
                      setCsvFile(null);
                    }
                  }}
                  csvFile={csvFile}
                  csvUploading={csvUploading}
                  csvFileInputRef={csvFileInputRef}
                  onUploadClick={handleCsvUploadClick}
                  onFileChange={handleCsvFileChange}
                  onProcess={processCsvFile}
                />

                <Button
                  type="button"
                  variant="outline"
                  onClick={toggleSelectionMode}
                  className="border-primary text-primary hover:bg-primary hover:text-primary-foreground"
                >
                  {selectionMode ? (
                    <>
                      <Square className="mr-2 h-4 w-4" />
                      Cancel Select
                    </>
                  ) : (
                    <>
                      <CheckSquare className="mr-2 h-4 w-4" />
                      Select
                    </>
                  )}
                </Button>

                {selectionMode ? (
                  <Button
                    type="button"
                    onClick={handleDeleteSelected}
                    disabled={selectedPatientIds.length === 0 || deletingPatients}
                    className="bg-destructive hover:bg-destructive/90 text-destructive-foreground"
                  >
                    {deletingPatients ? (
                      <>
                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                        Deleting...
                      </>
                    ) : (
                      <>
                        <Trash2 className="mr-2 h-4 w-4" />
                        Delete Patients{selectedPatientIds.length > 0 ? ` (${selectedPatientIds.length})` : ''}
                      </>
                    )}
                  </Button>
                ) : (
                  <PatientQuickAddDialog
                    isOpen={isQuickAddOpen}
                    onOpenChange={setIsQuickAddOpen}
                    formData={quickFormData}
                    onFieldChange={handleQuickFormChange}
                    onSubmit={handleQuickSubmit}
                  />
                )}
                <Link to="/patients/new">
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
        <PatientListControls
          searchTerm={searchTerm}
          onSearchTermChange={setSearchTerm}
          sortField={sortField}
          sortOptions={SORT_OPTIONS}
          onSortFieldChange={handleSortFieldChange}
          sortDirection={sortDirection}
          onToggleSortDirection={toggleSortDirection}
        />

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
              const isSelected = selectedPatientIds.includes(patient.id);
              return (
                <PatientCard
                  key={patient.id}
                  patient={patient}
                  selectionMode={selectionMode}
                  isSelected={isSelected}
                  onSelect={() => togglePatientSelection(patient.id)}
                  lastVisit={lastVisit}
                  primaryPhysician={primaryPhysician}
                  noteToDisplay={noteToDisplay}
                  trimmedNote={trimmedNote}
                  latestNoteDate={latestNoteDate}
                />
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
            <Link to="/patients/new">
              <Button>
                <Plus className="mr-2 h-4 w-4" />
                Add First Patient
              </Button>
            </Link>
          </div>
        )}

        <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Delete selected patients?</AlertDialogTitle>
              <AlertDialogDescription>
                Delete {selectedPatientIds.length} selected patient{selectedPatientIds.length === 1 ? '' : 's'}.
                This cannot be undone.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel disabled={deletingPatients}>Cancel</AlertDialogCancel>
              <AlertDialogAction
                onClick={(event) => {
                  event.preventDefault();
                  void confirmDeleteSelected();
                }}
                disabled={deletingPatients}
                className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              >
                {deletingPatients ? 'Deleting...' : 'Delete Patients'}
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </div>
    </div>
  );
};

export default PatientList;
