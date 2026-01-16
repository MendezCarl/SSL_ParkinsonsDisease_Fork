import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { ArrowUpDown, CalendarClock, FileText, Loader2, Plus, Search, Stethoscope, User, UserPlus } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { useToast } from '@/hooks/use-toast';
import { Patient, DoctorNoteEntry } from '@/types/patient';
import apiService, { normalizeBirthDate } from '@/services/api';
import { useApiStatus } from '@/hooks/use-api-status';
import { getSeverityColor, calculateAge } from '@/lib/utils';

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
  const [searchTerm, setSearchTerm] = useState('');
  const [patients, setPatients] = useState<Patient[]>([]);
  const [loading, setLoading] = useState(true);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const { toast } = useToast();
  const { isConnected, isChecking } = useApiStatus();
  const [sortField, setSortField] = useState<SortField>('lastName');
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('asc');

  // Quick add form state
  const [quickFormData, setQuickFormData] = useState({
    firstName: '',
    lastName: '',
    recordNumber: '',
    birthDate: '',
    severity: '' as Patient['severity'],
  });

  // Fetch patients on component mount
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
              <p className="text-muted-foreground mt-1">Parkinson's Disease Monitoring System</p>
              {!isChecking && (
                <div className="flex items-center mt-2">
                  <div className={`w-2 h-2 rounded-full mr-2 ${isConnected ? 'bg-green-500' : 'bg-red-500'}`} />
                  <span className="text-xs text-muted-foreground">
                    {isConnected ? 'Connected to backend' : 'Backend disconnected'}
                  </span>
                </div>
              )}
            </div>
            <div className="flex items-center space-x-3">
              {/* Quick Add Modal */}
              <Dialog open={isModalOpen} onOpenChange={setIsModalOpen}>
                <DialogTrigger asChild>
                  <Button variant="outline" className="border-primary text-primary hover:bg-primary hover:text-primary-foreground">
                    <UserPlus className="mr-2 h-4 w-4" />
                    Quick Add
                  </Button>
                </DialogTrigger>
                <DialogContent className="sm:max-w-md">
                  <DialogHeader>
                    <DialogTitle>Quick Add Patient</DialogTitle>
                  </DialogHeader>
                  <form onSubmit={handleQuickSubmit} className="space-y-4">
                    <div className="grid grid-cols-2 gap-4">
                      <div className="space-y-2">
                        <Label htmlFor="quick-firstName">First Name *</Label>
                        <Input
                          id="quick-firstName"
                          placeholder="John"
                          value={quickFormData.firstName}
                          onChange={(e) => handleQuickFormChange('firstName', e.target.value)}
                          required
                        />
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="quick-lastName">Last Name *</Label>
                        <Input
                          id="quick-lastName"
                          placeholder="Smith"
                          value={quickFormData.lastName}
                          onChange={(e) => handleQuickFormChange('lastName', e.target.value)}
                          required
                        />
                      </div>
                    </div>
                    
                    <div className="grid grid-cols-2 gap-4">
                      <div className="space-y-2">
                        <Label htmlFor="quick-recordNumber">Record Number *</Label>
                        <Input
                          id="quick-recordNumber"
                          placeholder="P004"
                          value={quickFormData.recordNumber}
                          onChange={(e) => handleQuickFormChange('recordNumber', e.target.value)}
                          required
                        />
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="quick-birthDate">Date of Birth *</Label>
                        <Input
                          id="quick-birthDate"
                          type="date"
                          value={quickFormData.birthDate}
                          onChange={(e) => handleQuickFormChange('birthDate', e.target.value)}
                          required
                        />
                      </div>
                    </div>

                    <div className="space-y-2">
                      <Label htmlFor="quick-severity">Parkinson's Severity *</Label>
                      <Select value={quickFormData.severity} onValueChange={(value) => handleQuickFormChange('severity', value)}>
                        <SelectTrigger>
                          <SelectValue placeholder="Select severity level" />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="Stage 1">Stage 1</SelectItem>
                          <SelectItem value="Stage 2">Stage 2</SelectItem>
                          <SelectItem value="Stage 3">Stage 3</SelectItem>
                          <SelectItem value="Stage 4">Stage 4</SelectItem>
                          <SelectItem value="Stage 5">Stage 5</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>

                    <div className="flex justify-end space-x-3 pt-4">
                      <Button type="button" variant="outline" onClick={() => setIsModalOpen(false)}>
                        Cancel
                      </Button>
                      <Button type="submit" className="bg-primary hover:bg-gradient-primary-hover">
                        <UserPlus className="mr-2 h-4 w-4" />
                        Add Patient
                      </Button>
                    </div>
                  </form>
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
              className="pl-10"
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