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
import { createPatient, deletePatient, getPatients, importPatientsCsv } from '@/services/patients';
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
    queueMicrotask(() => void fetchPatients());
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
    if (!file) {
      setCsvFile(null);
      return;
    }
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

  const processCsvFile = async () => {
    if (!csvFile) return;
    setCsvUploading(true);
    try {
      const response = await importPatientsCsv(csvFile);
      if (!response.success || !response.data) {
        toast({
          title: 'CSV Import Failed',
          description: response.error || 'Failed to import patients from CSV.',
          variant: 'destructive',
        });
        return;
      }

      const { success_count, failure_count, errors } = response.data;

      if (success_count > 0) {
        await fetchPatients();
      }

      const sampleErrors = errors
        .slice(0, 2)
        .map((entry) => {
          const fieldErrors = Object.entries(entry.errors || {})
            .map(([field, message]) => `${field}: ${message}`)
            .join(', ');
          return `row ${entry.row}${fieldErrors ? ` (${fieldErrors})` : entry.error ? ` (${entry.error})` : ''}`;
        })
        .join('; ');

      toast({
        title: failure_count > 0 ? 'CSV Import Completed With Issues' : 'CSV Import Complete',
        description: [
          `Imported ${success_count} patient${success_count === 1 ? '' : 's'}.`,
          `${failure_count} failure${failure_count === 1 ? '' : 's'}.`,
          sampleErrors ? `First issues: ${sampleErrors}.` : '',
        ]
          .filter(Boolean)
          .join(' '),
        variant: failure_count > 0 ? 'destructive' : 'default',
      });

      setCsvFile(null);
      setIsModalOpen(false);
    } catch (error) {
      console.error('Error processing CSV:', error);
      toast({
        title: "Error",
        description: "Failed to import the CSV file.",
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

    // Create new patient data
    const newPatientData = {
      firstName: quickFormData.firstName,
      lastName: quickFormData.lastName,
      birthDate: quickFormData.birthDate,
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
