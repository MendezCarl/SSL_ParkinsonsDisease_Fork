import { Link } from 'react-router-dom';
import { ArrowUpDown, CalendarClock, CheckSquare, FileText, Loader2, Plus, Search, Square, Stethoscope, Trash2, Upload, User } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import type { Patient } from '@/types/patient';
import { calculateAge, getSeverityColor } from '@/lib/utils';

type SortField = 'lastName' | 'severity' | 'lastVisit' | 'physician';

export function PatientCsvImportDialog({
  isOpen,
  onOpenChange,
  csvFile,
  csvUploading,
  csvFileInputRef,
  onUploadClick,
  onFileChange,
  onProcess,
}: {
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  csvFile: File | null;
  csvUploading: boolean;
  csvFileInputRef: React.RefObject<HTMLInputElement>;
  onUploadClick: () => void;
  onFileChange: (event: React.ChangeEvent<HTMLInputElement>) => void;
  onProcess: () => void;
}) {
  return (
    <Dialog open={isOpen} onOpenChange={onOpenChange}>
      <DialogTrigger asChild>
        <Button variant="outline" className="border-primary text-primary hover:bg-primary hover:text-primary-foreground">
          <Upload className="mr-2 h-4 w-4" />
          Upload Patient
        </Button>
      </DialogTrigger>
      <DialogContent className="w-full sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Upload Patients from CSV</DialogTitle>
        </DialogHeader>
        <div className="space-y-6 py-4">
          <div className="space-y-4">
            <div className="flex flex-col items-center justify-center border-2 border-dashed border-muted-foreground/25 rounded-lg p-8 hover:border-primary/50 transition-colors">
              <Upload className="h-12 w-12 text-muted-foreground mb-4" />
              <Button type="button" variant="outline" onClick={onUploadClick} className="mb-2">
                <Upload className="mr-2 h-4 w-4" />
                {csvFile ? 'Change CSV File' : 'Select CSV File'}
              </Button>
              <p className="text-sm text-muted-foreground">Upload a CSV file containing patient information</p>
              <input
                ref={csvFileInputRef}
                type="file"
                accept=".csv"
                onChange={onFileChange}
                className="hidden"
              />
            </div>

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

            <div className="bg-muted/50 rounded-lg p-4">
              <h4 className="text-sm font-semibold mb-2">CSV Format Requirements:</h4>
              <ul className="text-xs text-muted-foreground space-y-1">
                <li>• Required data: patient name and birth date columns</li>
                <li>• Accepted name headers include firstName/lastName or fullName</li>
                <li>• Severity accepts Stage 1-5, numbers 1-5, or common aliases</li>
                <li>• Birth dates can be ISO or common slash/dash date formats</li>
                <li>• Optional fields: height, weight, labResults, doctorNotes</li>
                <li>• Record numbers and import normalization are handled by the backend.</li>
              </ul>
            </div>
          </div>

          <div className="flex justify-end gap-3">
            <Button
              type="button"
              variant="outline"
              onClick={() => {
                onOpenChange(false);
              }}
            >
              Cancel
            </Button>
            <Button type="button" onClick={onProcess} disabled={!csvFile || csvUploading}>
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
  );
}

export function PatientListControls({
  searchTerm,
  onSearchTermChange,
  sortField,
  sortOptions,
  onSortFieldChange,
  sortDirection,
  onToggleSortDirection,
}: {
  searchTerm: string;
  onSearchTermChange: (value: string) => void;
  sortField: SortField;
  sortOptions: { value: SortField; label: string }[];
  onSortFieldChange: (value: SortField) => void;
  sortDirection: 'asc' | 'desc';
  onToggleSortDirection: () => void;
}) {
  return (
    <div className="mb-8 flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
      <div className="relative w-full max-w-md md:w-auto">
        <Search className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
        <Input
          placeholder="Search patients by name or record number..."
          value={searchTerm}
          onChange={(e) => onSearchTermChange(e.target.value)}
          className="pl-10 w-full md:w-[380px]"
        />
      </div>
      <div className="flex w-full flex-col gap-3 sm:w-auto sm:flex-row sm:items-center">
        <div className="flex items-center gap-2">
          <span className="text-sm text-muted-foreground">Sort by</span>
          <Select value={sortField} onValueChange={(value) => onSortFieldChange(value as SortField)}>
            <SelectTrigger className="w-[160px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {sortOptions.map((option) => (
                <SelectItem key={option.value} value={option.value}>
                  {option.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <Button variant="outline" size="sm" onClick={onToggleSortDirection} className="flex items-center gap-2 self-start sm:self-auto">
          <ArrowUpDown className="h-4 w-4" />
          {sortDirection === 'asc' ? 'Asc' : 'Desc'}
        </Button>
      </div>
    </div>
  );
}

export function PatientQuickAddDialog({
  isOpen,
  onOpenChange,
  formData,
  onFieldChange,
  onSubmit,
}: {
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  formData: {
    firstName: string;
    lastName: string;
    birthDate: string;
    severity: Patient['severity'];
  };
  onFieldChange: (field: string, value: string) => void;
  onSubmit: (event: React.FormEvent) => void;
}) {
  return (
    <Dialog open={isOpen} onOpenChange={onOpenChange}>
      <DialogTrigger asChild>
        <Button className="bg-primary hover:bg-primary-hover text-primary-foreground">
          <Plus className="mr-2 h-4 w-4" />
          Quick Add Patient
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Quick Add Patient</DialogTitle>
        </DialogHeader>
        <form onSubmit={onSubmit} className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="quick-first-name">First Name *</Label>
              <Input
                id="quick-first-name"
                value={formData.firstName}
                onChange={(e) => onFieldChange('firstName', e.target.value)}
                placeholder="Enter first name"
                required
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="quick-last-name">Last Name *</Label>
              <Input
                id="quick-last-name"
                value={formData.lastName}
                onChange={(e) => onFieldChange('lastName', e.target.value)}
                placeholder="Enter last name"
                required
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="quick-birth-date">Birthdate *</Label>
              <Input
                id="quick-birth-date"
                type="date"
                value={formData.birthDate}
                onChange={(e) => onFieldChange('birthDate', e.target.value)}
                required
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="quick-severity">Severity *</Label>
              <Select value={formData.severity} onValueChange={(value) => onFieldChange('severity', value)}>
                <SelectTrigger id="quick-severity">
                  <SelectValue placeholder="Select severity" />
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
          </div>
          <div className="text-xs text-muted-foreground">
            Record number is assigned automatically by the system.
          </div>
          <div className="flex justify-end gap-3">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit">
              <Plus className="mr-2 h-4 w-4" />
              Add Patient
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function PatientCard({
  patient,
  selectionMode,
  isSelected,
  onSelect,
  lastVisit,
  primaryPhysician,
  noteToDisplay,
  trimmedNote,
  latestNoteDate,
}: {
  patient: Patient;
  selectionMode: boolean;
  isSelected: boolean;
  onSelect: () => void;
  lastVisit: Date | null;
  primaryPhysician: string;
  noteToDisplay: string;
  trimmedNote: string;
  latestNoteDate: Date | null;
}) {
  const cardContent = (
    <Card
      className={[
        'transition-all duration-200 hover:shadow-medical hover:scale-[1.02] cursor-pointer',
        selectionMode && isSelected ? 'ring-2 ring-destructive border-destructive bg-destructive/5' : '',
      ].join(' ')}
    >
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between">
          <div className="flex items-center space-x-3">
            <div className="p-2 rounded-full bg-medical-light">
              {selectionMode ? (
                isSelected ? <CheckSquare className="h-5 w-5 text-destructive" /> : <Square className="h-5 w-5 text-medical-blue" />
              ) : (
                <User className="h-5 w-5 text-medical-blue" />
              )}
            </div>
            <div>
              <CardTitle className="text-lg">
                {patient.firstName} {patient.lastName}
              </CardTitle>
              <p className="text-sm text-muted-foreground">Record: {patient.recordNumber}</p>
            </div>
          </div>
          <Badge className={getSeverityColor(patient.severity)}>{patient.severity}</Badge>
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
                  {(latestNoteDate || patient.primaryPhysician) && (
                    <p className="text-xs text-muted-foreground/70 mt-2">
                      {latestNoteDate ? latestNoteDate.toLocaleDateString() : 'Unknown date'}
                      {patient.primaryPhysician ? ` by ${patient.primaryPhysician}` : ''}
                    </p>
                  )}
                </div>
              </div>
            </div>
          ) : (
            <div className="bg-muted/30 p-3 rounded-md border border-dashed">
              <div className="flex items-center gap-2">
                <FileText className="h-4 w-4 text-muted-foreground/50" />
                <p className="text-sm text-muted-foreground/70 italic">No doctor's notes available</p>
              </div>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );

  return selectionMode ? (
    <button type="button" onClick={onSelect} className="text-left" aria-pressed={isSelected}>
      {cardContent}
    </button>
  ) : (
    <Link to={`/patients/${patient.id}`}>{cardContent}</Link>
  );
}

export function PatientPrimaryAction({
  selectionMode,
  deletingPatients,
  selectedCount,
  onDeleteSelected,
}: {
  selectionMode: boolean;
  deletingPatients: boolean;
  selectedCount: number;
  onDeleteSelected: () => void;
}) {
  return selectionMode ? (
    <Button
      type="button"
      onClick={onDeleteSelected}
      disabled={selectedCount === 0 || deletingPatients}
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
          Delete Patients{selectedCount > 0 ? ` (${selectedCount})` : ''}
        </>
      )}
    </Button>
  ) : (
    <Link to="/patients/new">
      <Button className="bg-primary hover:bg-primary-hover text-primary-foreground">
        <Plus className="mr-2 h-4 w-4" />
        Detailed Form
      </Button>
    </Link>
  );
}
