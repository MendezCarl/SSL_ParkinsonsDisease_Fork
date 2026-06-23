import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams, Link } from "react-router-dom";
import {
  ArrowLeft,
  Plus,
  Calendar,
  FileText,
  Activity,
  Edit,
  Play,
  User,
  Stethoscope,
  TrendingUp,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import {
  Patient,
  Test,
  LabResultEntry,
  DoctorNoteEntry,
  TestIndicator,
} from "@/types/patient";
import { getSeverityColor, calculateAge } from "@/lib/utils";
import apiService from "@/services/api";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
} from "@/components/ui/select";
import { Label } from "@/components/ui/label";
import { useToast } from "@/hooks/use-toast";

const indicatorBadgeClasses: Record<TestIndicator["color"], string> = {
  success: "bg-success text-success-foreground",
  warning: "bg-warning text-warning-foreground",
  destructive: "bg-destructive text-destructive-foreground",
  muted: "bg-muted text-muted-foreground",
};

const testTypeStyles: Record<
  Test["type"],
  { container: string; badge: string }
> = {
  "stand-and-sit": {
    container: "border-l-4 border-l-emerald-500/80 bg-emerald-50/40",
    badge: "border border-emerald-200 bg-emerald-100 text-emerald-700",
  },
  "finger-tapping": {
    container: "border-l-4 border-l-sky-500/80 bg-sky-50/40",
    badge: "border border-sky-200 bg-sky-100 text-sky-700",
  },
  "fist-open-close": {
    container: "border-l-4 border-l-amber-500/80 bg-amber-50/40",
    badge: "border border-amber-200 bg-amber-100 text-amber-700",
  },
};

// ---------- Date helpers ----------
const isValidDate = (d: unknown): d is Date =>
  d instanceof Date && !Number.isNaN(d.getTime());
const toISO = (v: unknown): string => {
  const d = v instanceof Date ? v : new Date(v as any);
  return isValidDate(d) ? d.toISOString() : new Date().toISOString();
};

const PatientDetails = () => {
  const { id } = useParams<{ id: string }>();
  const [patient, setPatient] = useState<Patient | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tests, setTests] = useState<Test[]>([]); // Placeholder – replace with real API if available
  const [testsLoading, setTestsLoading] = useState(true);
  const [testSearch, setTestSearch] = useState("");
  const [isEditOpen, setIsEditOpen] = useState(false);
  const [editData, setEditData] = useState<Partial<Patient>>({});
  const [isLabResultModalOpen, setIsLabResultModalOpen] = useState(false);
  const [isDoctorNoteModalOpen, setIsDoctorNoteModalOpen] = useState(false);
  const [newLabResult, setNewLabResult] = useState("");
  const [newDoctorNote, setNewDoctorNote] = useState("");
  const { toast } = useToast();

  const sortedTests = useMemo(
    () => [...tests].sort((a, b) => b.date.getTime() - a.date.getTime()),
    [tests]
  );

  const filteredTests = useMemo(() => {
    const query = testSearch.trim().toLowerCase();
    if (!query) return sortedTests;
    return sortedTests.filter((test) => {
      const haystack = [
        test.name,
        test.type,
        test.indicator?.label,
        test.recordingFile,
        test.recordingUrl,
      ]
        .filter(Boolean)
        .map((value) => String(value).toLowerCase());
      return haystack.some((value) => value.includes(query));
    });
  }, [sortedTests, testSearch]);

  const openForEdit = useCallback(() => {
    if (!patient) return;
    setEditData({
      firstName: patient.firstName ?? "",
      lastName: patient.lastName ?? "",
      birthDate: patient.birthDate ?? "",
      height: patient.height ?? "",
      weight: patient.weight ?? "",
      labResults: patient.labResults ?? "",
      doctorNotes: patient.doctorNotes ?? "",
      severity: (patient.severity as Patient["severity"]) ?? "Stage 1",
    });
    setIsEditOpen(true);
  }, [patient]);

  const handleEditSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!patient) return;
    const updated: Patient = { ...patient, ...editData } as Patient;
    setPatient(updated);
    setIsEditOpen(false);
  };

  // --- Send ONE lab result per submit (optimistic UI + rollback) ---
  const handleAddLabResult = async () => {
    if (!patient || !newLabResult.trim()) return;

    const resultText = newLabResult.trim();
    const entryId = `lab_${Date.now()}`;

    const newEntry: LabResultEntry = {
      id: entryId,
      date: new Date(),
      results: resultText,
      addedBy: "Current User", // In a real app, this would come from auth context
    };

    const prev = patient;
    const updated = {
      ...patient,
      labResults: resultText,
      labResultsHistory: [...(patient.labResultsHistory ?? []), newEntry],
    };

    // optimistic UI
    setPatient(updated);
    setNewLabResult("");
    setIsLabResultModalOpen(false);

    try {
      const response = await apiService.addPatientLabResult(patient.id, {
        id: entryId,
        date: toISO(newEntry.date),
        added_by: newEntry.addedBy ?? "Unknown",
        results: resultText,
      });
      if (!response.success) throw new Error(response.error || 'Failed to save lab result');
      toast({
        title: "Lab Result Added",
        description: "Recorded successfully.",
      });
    } catch (e) {
      console.error("Error saving lab result:", e);
      // rollback
      setPatient(prev);
      toast({
        title: "Error",
        description: "Failed to save lab result.",
        variant: "destructive",
      });
    }
  };

  // --- OPTIONAL: Send ONE doctor note per submit (same pattern) ---
  const handleAddDoctorNote = async () => {
    if (!patient || !newDoctorNote.trim()) return;

    const noteText = newDoctorNote.trim();
    const entryId = `note_${Date.now()}`;

    const newEntry: DoctorNoteEntry = {
      id: entryId,
      date: new Date(),
      note: noteText,
      addedBy: "Current User",
    };

    const prev = patient;
    const updated = {
      ...patient,
      doctorNotes: noteText,
      doctorNotesHistory: [...(patient.doctorNotesHistory ?? []), newEntry],
    };

    // optimistic UI
    setPatient(updated);
    setNewDoctorNote("");
    setIsDoctorNoteModalOpen(false);

    try {
      const response = await apiService.addPatientDoctorNote(patient.id, {
        id: entryId,
        date: toISO(newEntry.date),
        note: noteText,
        added_by: newEntry.addedBy ?? null,
      });
      if (!response.success) throw new Error(response.error || 'Failed to save doctor note');
      toast({ title: "Note Added", description: "Recorded successfully." });
    } catch (e) {
      console.error("Error saving doctor note:", e);
      // rollback
      setPatient(prev);
      toast({
        title: "Error",
        description: "Couldn't save doctor's note.",
        variant: "destructive",
      });
    }
  };

  useEffect(() => {
    const fetchPatient = async () => {
      if (!id) {
        setError("Patient ID is missing");
        setLoading(false);
        return;
      }

      try {
        const response = await apiService.getPatient(id);
        if (!response.success || !response.data) {
          throw new Error(response.error || 'Failed to fetch patient');
        }

        setPatient(response.data);

        setTests([]);
      } catch (err: any) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };

    fetchPatient();
  }, [id]);

  useEffect(() => {
    if (!id) return;

    let cancelled = false;
    const fetchTests = async () => {
      setTestsLoading(true);
      setTests([]);
      try {
        const response = await apiService.getPatientTests(id);
        if (cancelled) return;
        if (response.success && response.data) {
          setTests(response.data);
        } else {
          setTests([]);
        }
      } catch (err) {
        if (!cancelled) {
          console.error("Error fetching test history:", err);
          setTests([]);
        }
      } finally {
        if (!cancelled) {
          setTestsLoading(false);
        }
      }
    };

    fetchTests();

    return () => {
      cancelled = true;
    };
  }, [id]);

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <p className="text-muted-foreground">Loading patient data...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <p className="text-destructive">{error}</p>
      </div>
    );
  }

  if (!patient) {
    return null;
  }

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <div className="border-b bg-card shadow-card">
        <div className="container mx-auto px-6 py-6">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-4">
              <Link to="/">
                <Button variant="outline" size="sm">
                  <ArrowLeft className="mr-2 h-4 w-4" />
                  Back to Patients
                </Button>
              </Link>
              <div>
                <h1 className="text-3xl font-bold text-foreground">
                  {patient.firstName} {patient.lastName}
                </h1>
                <p className="text-muted-foreground mt-1">
                  Record: {patient.recordNumber || "N/A"}
                </p>
              </div>
            </div>
            <div className="flex items-center space-x-3">
              <Button variant="outline" onClick={openForEdit}>
                <Edit className="mr-2 h-4 w-4" />
                Edit Patient
              </Button>
              <Link to={`/patients/${id}/timeline`}>
                <Button variant="outline">
                  <TrendingUp className="mr-2 h-4 w-4" />
                  View Timeline
                </Button>
              </Link>
              <Link to={`/patient/${id}/test-selection`}>
                <Button className="bg-primary hover:bg-primary-hover">
                  <Plus className="mr-2 h-4 w-4" />
                  New Test
                </Button>
              </Link>
            </div>
          </div>
        </div>
      </div>

      {/* Patient Information */}
      <div className="container mx-auto px-6 py-8">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          <div className="lg:col-span-2 space-y-6">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center justify-between">
                  Patient Information
                  <Badge className={getSeverityColor(patient.severity)}>
                    {patient.severity}
                  </Badge>
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <div>
                    <p className="text-sm font-medium text-muted-foreground">
                      Date of Birth
                    </p>
                    <p className="text-lg font-semibold">
                      {patient.birthDate || "N/A"}
                      {patient.birthDate && (
                        <span className="text-sm text-muted-foreground ml-2">
                          (Age: {calculateAge(patient.birthDate)} years)
                        </span>
                      )}
                    </p>
                    <p className="text-xs text-muted-foreground/70">
                      YYYY-MM-DD format
                    </p>
                  </div>
                  <div>
                    <p className="text-sm font-medium text-muted-foreground">
                      Height
                    </p>
                    <p className="text-lg font-semibold">{patient.height}</p>
                  </div>
                  <div>
                    <p className="text-sm font-medium text-muted-foreground">
                      Weight
                    </p>
                    <p className="text-lg font-semibold">{patient.weight}</p>
                  </div>
                  <div>
                    <p className="text-sm font-medium text-muted-foreground">
                      Severity
                    </p>
                    <p className="text-lg font-semibold">{patient.severity}</p>
                  </div>
                </div>

                <Separator />

                <div>
                  <div className="flex items-center justify-between mb-4">
                    <p className="text-sm font-medium text-muted-foreground">
                      Lab Results History
                    </p>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => setIsLabResultModalOpen(true)}
                    >
                      <Plus className="mr-2 h-4 w-4" />
                      Add Lab Result
                    </Button>
                  </div>
                  <div className="space-y-3">
                    {patient.labResultsHistory &&
                    patient.labResultsHistory.length > 0 ? (
                      patient.labResultsHistory
                        .sort((a, b) => a.date.getTime() - b.date.getTime())
                        .map((entry) => (
                          <div
                            key={entry.id}
                            className="border rounded-lg p-4 bg-card"
                          >
                            <div className="flex items-start justify-between mb-2">
                              <div className="flex items-center text-sm text-muted-foreground">
                                <Stethoscope className="mr-2 h-4 w-4" />
                                <span>{entry.date.toLocaleDateString()}</span>
                                {entry.addedBy && (
                                  <>
                                    <span className="mx-2">•</span>
                                    <span>by {entry.addedBy}</span>
                                  </>
                                )}
                              </div>
                              <span className="text-xs text-muted-foreground">
                                {entry.date.toLocaleTimeString()}
                              </span>
                            </div>
                            <p className="text-sm">{entry.results}</p>
                          </div>
                        ))
                    ) : (
                      <p className="text-sm text-muted-foreground italic">
                        No lab results recorded
                      </p>
                    )}
                  </div>
                </div>

                <Separator />

                <div>
                  <div className="flex items-center justify-between mb-4">
                    <p className="text-sm font-medium text-muted-foreground">
                      Doctor's Notes History
                    </p>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => setIsDoctorNoteModalOpen(true)}
                    >
                      <Plus className="mr-2 h-4 w-4" />
                      Add Note
                    </Button>
                  </div>
                  <div className="space-y-3">
                    {patient.doctorNotesHistory &&
                    patient.doctorNotesHistory.length > 0 ? (
                      patient.doctorNotesHistory
                        .sort((a, b) => a.date.getTime() - b.date.getTime())
                        .map((entry) => (
                          <div
                            key={entry.id}
                            className="border rounded-lg p-4 bg-muted/50"
                          >
                            <div className="flex items-start justify-between mb-2">
                              <div className="flex items-center text-sm text-muted-foreground">
                                <User className="mr-2 h-4 w-4" />
                                <span>{entry.date.toLocaleDateString()}</span>
                                {entry.addedBy && (
                                  <>
                                    <span className="mx-2">•</span>
                                    <span>by {entry.addedBy}</span>
                                  </>
                                )}
                              </div>
                              <span className="text-xs text-muted-foreground">
                                {entry.date.toLocaleTimeString()}
                              </span>
                            </div>
                            <p className="text-sm">{entry.note}</p>
                          </div>
                        ))
                    ) : (
                      <p className="text-sm text-muted-foreground italic">
                        No doctor's notes recorded
                      </p>
                    )}
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Test History (placeholder for now) */}
          <div className="space-y-6">
            <Card>
              <CardHeader>
                <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
                  <CardTitle className="flex items-center">
                    <Activity className="mr-2 h-5 w-5" />
                    Test History
                  </CardTitle>
                  <div className="w-full lg:w-72">
                    <Input
                      placeholder="Search tests by name or type..."
                      value={testSearch}
                      onChange={(event) => setTestSearch(event.target.value)}
                      className="h-9"
                    />
                  </div>
                </div>
              </CardHeader>
              <CardContent>
                <div className="space-y-4 max-h-[35rem] overflow-y-auto pr-1">
                  {testsLoading ? (
                    <div className="text-center py-8 text-sm text-muted-foreground">
                      Loading test history...
                    </div>
                  ) : filteredTests.length > 0 ? (
                    filteredTests.map((test) => {
                      const badgeVariant = test.indicator
                        ? indicatorBadgeClasses[test.indicator.color]
                        : indicatorBadgeClasses.muted;
                      const typeStyle = testTypeStyles[test.type];
                      const metaPieces: string[] = [];
                      if (
                        typeof test.frameCount === "number" &&
                        Number.isFinite(test.frameCount)
                      ) {
                        metaPieces.push(`${test.frameCount} frames`);
                      }
                      if (
                        typeof test.fps === "number" &&
                        Number.isFinite(test.fps)
                      ) {
                        metaPieces.push(`${test.fps.toFixed(1)} fps`);
                      }
                      if (
                        typeof test.similarity === "number" &&
                        Number.isFinite(test.similarity)
                      ) {
                        metaPieces.push(
                          `Similarity ${(test.similarity * 100).toFixed(1)}%`
                        );
                      }

                      return (
                        <div
                          key={test.id}
                          className={`border rounded-lg p-4 transition-colors ${typeStyle.container}`}
                        >
                          <div className="flex items-start justify-between gap-3">
                            <div className="space-y-1">
                              <div className="flex items-center gap-2">
                                <h4 className="font-medium text-sm">
                                  {test.name}
                                </h4>
                                <Badge
                                  variant="outline"
                                  className={`uppercase tracking-wide text-[10px] ${typeStyle.badge}`}
                                >
                                  {test.type.replace(/-/g, " ")}
                                </Badge>
                              </div>
                              <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                                <span className="inline-flex items-center gap-1">
                                  <Calendar className="h-3 w-3" />
                                  {test.date
                                    ? test.date.toLocaleString()
                                    : "Unknown date"}
                                </span>
                                {metaPieces.map((piece) => (
                                  <span
                                    key={piece}
                                    className="inline-flex items-center gap-1"
                                  >
                                    <span className="opacity-50">•</span>
                                    {piece}
                                  </span>
                                ))}
                              </div>
                            </div>
                            <Badge className={badgeVariant} variant="secondary">
                              {/* {test.indicator?.label ?? test.status} */}
                            </Badge>
                          </div>
                          <div className="mt-3 flex flex-wrap gap-2">
                            {test.summaryAvailable && (
                              <Link
                                to={`/patient/${id}/video-summary/${encodeURIComponent(
                                  test.id
                                )}`}
                              >
                                <Button
                                  size="sm"
                                  variant="outline"
                                  className="w-full sm:w-auto"
                                >
                                  <Play className="mr-2 h-3 w-3" />
                                  View Results
                                </Button>
                              </Link>
                            )}
                            {test.videoUrl && (
                              <a
                                href={test.videoUrl}
                                target="_blank"
                                rel="noreferrer"
                              >
                                <Button
                                  size="sm"
                                  variant="ghost"
                                  className="w-full sm:w-auto"
                                >
                                  Open Recording
                                </Button>
                              </a>
                            )}
                          </div>
                        </div>
                      );
                    })
                  ) : tests.length > 0 ? (
                    <div className="text-center py-8">
                      <FileText className="mx-auto h-8 w-8 text-muted-foreground mb-2" />
                      <p className="text-sm text-muted-foreground">
                        No tests match "{testSearch}"
                      </p>
                    </div>
                  ) : (
                    <div className="text-center py-8">
                      <FileText className="mx-auto h-8 w-8 text-muted-foreground mb-2" />
                      <p className="text-sm text-muted-foreground">
                        No tests recorded yet
                      </p>
                      <Link to={`/patient/${id}/test-selection`}>
                        <Button size="sm" className="mt-3">
                          <Plus className="mr-2 h-3 w-3" />
                          Create First Test
                        </Button>
                      </Link>
                    </div>
                  )}
                </div>
              </CardContent>
            </Card>
          </div>
        </div>
      </div>

      {/* Edit Patient pop up*/}
      <Dialog open={isEditOpen} onOpenChange={setIsEditOpen}>
        <DialogContent aria-describedby={undefined}>
          <DialogHeader>
            <DialogTitle className="mb-4 text-lg font-semibold">
              Edit Patient Details
            </DialogTitle>
          </DialogHeader>
          <form onSubmit={handleEditSubmit} className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <Label htmlFor="firstName">First Name</Label>
                <Input
                  id="firstName"
                  value={editData.firstName ?? ""}
                  onChange={(e) =>
                    setEditData((d) => ({ ...d, firstName: e.target.value }))
                  }
                />
              </div>
              <div>
                <Label htmlFor="lastName">Last Name</Label>
                <Input
                  id="lastName"
                  value={editData.lastName ?? ""}
                  onChange={(e) =>
                    setEditData((d) => ({ ...d, lastName: e.target.value }))
                  }
                />
              </div>
              <div>
                <Label htmlFor="birthDate">Birthdate</Label>
                <Input
                  id="birthDate"
                  type="date"
                  value={editData.birthDate ?? ""}
                  onChange={(e) =>
                    setEditData((d) => ({ ...d, birthDate: e.target.value }))
                  }
                />
              </div>
              <div>
                <Label htmlFor="severity">Severity</Label>
                <Select
                  value={editData.severity ?? "Stage 1"}
                  onValueChange={(v) =>
                    setEditData((d) => ({
                      ...d,
                      severity: v as Patient["severity"],
                    }))
                  }
                >
                  <SelectTrigger id="severity">
                    <SelectValue placeholder="Select severity" />
                  </SelectTrigger>
                  <SelectContent position="popper" className="z-[60]">
                    <SelectItem value="Stage 1">Stage 1</SelectItem>
                    <SelectItem value="Stage 2">Stage 2</SelectItem>
                    <SelectItem value="Stage 3">Stage 3</SelectItem>
                    <SelectItem value="Stage 4">Stage 4</SelectItem>
                    <SelectItem value="Stage 5">Stage 5</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label htmlFor="height">Height</Label>
                <Input
                  id="height"
                  placeholder="e.g., 170 cm"
                  value={editData.height ?? ""}
                  onChange={(e) =>
                    setEditData((d) => ({ ...d, height: e.target.value }))
                  }
                />
              </div>
              <div>
                <Label htmlFor="weight">Weight</Label>
                <Input
                  id="weight"
                  placeholder="e.g., 70 kg"
                  value={editData.weight ?? ""}
                  onChange={(e) =>
                    setEditData((d) => ({ ...d, weight: e.target.value }))
                  }
                />
              </div>
            </div>

            <div>
              <Label htmlFor="labResults">Lab Results</Label>
              <Textarea
                id="labResults"
                rows={3}
                value={editData.labResults ?? ""}
                onChange={(e) =>
                  setEditData((d) => ({ ...d, labResults: e.target.value }))
                }
              />
            </div>

            <div>
              <Label htmlFor="doctorNotes">Doctor Notes</Label>
              <Textarea
                id="doctorNotes"
                rows={4}
                value={editData.doctorNotes ?? ""}
                onChange={(e) =>
                  setEditData((d) => ({ ...d, doctorNotes: e.target.value }))
                }
              />
            </div>

            <div className="flex justify-end gap-2 pt-2">
              <Button
                type="button"
                variant="outline"
                onClick={() => setIsEditOpen(false)}
              >
                Cancel
              </Button>
              <Button type="submit">Save</Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>

      {/* Lab Result Modal */}
      <Dialog
        open={isLabResultModalOpen}
        onOpenChange={setIsLabResultModalOpen}
      >
        <DialogContent aria-describedby={undefined} className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Add Lab Result</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label htmlFor="labResult">Lab Results</Label>
              <Textarea
                id="labResult"
                placeholder="Enter lab results (e.g., CBC: Normal, Dopamine markers: 120 ng/mL...)"
                value={newLabResult}
                onChange={(e) => setNewLabResult(e.target.value)}
                rows={4}
              />
            </div>
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setIsLabResultModalOpen(false)}
            >
              Cancel
            </Button>
            <Button
              onClick={handleAddLabResult}
              disabled={!newLabResult.trim()}
            >
              Add Result
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Doctor Note Modal */}
      <Dialog
        open={isDoctorNoteModalOpen}
        onOpenChange={setIsDoctorNoteModalOpen}
      >
        <DialogContent aria-describedby={undefined} className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Add Doctor's Note</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label htmlFor="doctorNote">Doctor's Note</Label>
              <Textarea
                id="doctorNote"
                placeholder="Enter doctor's notes or observations..."
                value={newDoctorNote}
                onChange={(e) => setNewDoctorNote(e.target.value)}
                rows={4}
              />
            </div>
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setIsDoctorNoteModalOpen(false)}
            >
              Cancel
            </Button>
            <Button
              onClick={handleAddDoctorNote}
              disabled={!newDoctorNote.trim()}
            >
              Add Note
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default PatientDetails;
