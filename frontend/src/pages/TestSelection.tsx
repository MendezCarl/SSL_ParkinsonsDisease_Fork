import { useState, useEffect, useMemo, useRef } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { ArrowLeft, Play, FileText, Activity, Video, Upload } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import { useToast } from '@/hooks/use-toast';
import { Patient, Test, AVAILABLE_TESTS, TestIndicator } from '@/types/patient';
import { getPatient } from '@/services/patients';
import { getPatientTests } from '@/services/tests';
import { uploadVideo } from '@/services/uploads';
import { getSeverityColor, calculateAge } from '@/lib/utils';
import { Input } from '@/components/ui/input';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';

const indicatorBadgeClasses: Record<TestIndicator['color'], string> = {
  success: 'bg-success text-success-foreground',
  warning: 'bg-warning text-warning-foreground',
  destructive: 'bg-destructive text-destructive-foreground',
  muted: 'bg-muted text-muted-foreground',
};

const testTypeStyles: Record<Test['type'], { container: string; badge: string }> = {
  'stand-and-sit': {
    container: 'border-l-4 border-l-emerald-500/80 bg-emerald-50/40',
    badge: 'border border-emerald-200 bg-emerald-100 text-emerald-700',
  },
  'finger-tapping': {
    container: 'border-l-4 border-l-sky-500/80 bg-sky-50/40',
    badge: 'border border-sky-200 bg-sky-100 text-sky-700',
  },
  'fist-open-close': {
    container: 'border-l-4 border-l-amber-500/80 bg-amber-50/40',
    badge: 'border border-amber-200 bg-amber-100 text-amber-700',
  },
  unknown: {
    container: 'border-l-4 border-l-slate-500/80 bg-slate-50/40',
    badge: 'border border-slate-200 bg-slate-100 text-slate-700',
  },
};

const TestSelection = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { toast } = useToast();
  const [patient, setPatient] = useState<Patient | null>(null);
  const [testHistory, setTestHistory] = useState<Test[]>([]);
  const [selectedTests, setSelectedTests] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadingPatient, setLoadingPatient] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [testSearch, setTestSearch] = useState('');
  const [isUploadModalOpen, setIsUploadModalOpen] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const sortedHistory = useMemo(
    () => [...testHistory].sort((a, b) => b.date.getTime() - a.date.getTime()),
    [testHistory]
  );
  const filteredHistory = useMemo(() => {
    const query = testSearch.trim().toLowerCase();
    if (!query) return sortedHistory;
    return sortedHistory.filter((test) => {
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
  }, [sortedHistory, testSearch]);

  useEffect(() => {
    const fetchData = async () => {
      if (!id) return;
      setLoadingPatient(true);
      try {
        const [patientRes, testsRes] = await Promise.all([
          getPatient(id),
          getPatientTests(id),
        ]);

        // patient
        if (patientRes.success && patientRes.data) {
          setPatient(patientRes.data);
        } else {
          setError(patientRes.error || 'Failed to fetch patient');
        }

        // tests
        if (testsRes.success && testsRes.data) {
          setTestHistory(testsRes.data);
        }
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : 'Failed to connect to server');
      } finally {
        setLoadingPatient(false);
      }
    };
    fetchData();
  }, [id]);

  const handleUploadClick = () => {
    if (fileInputRef.current){
      fileInputRef.current.value = "";
      fileInputRef.current.click();
    }
  }

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const allowedTypes = ['video/mp4', 'video/quicktime'];
    if (!allowedTypes.includes(file.type)){
      toast({
        title: "Invalid File Type",
        description: "please select a .mp4 or .mov video file",
      });
      return;
    }

    if (!id) {
      return;
    }

    if (selectedTests.length !== 1) {
      toast({
        title: 'Select One Test',
        description: 'Upload supports one selected test at a time.',
        variant: 'destructive',
      });
      return;
    }

    const formData = new FormData();
    formData.append('patient_id', id);
    formData.append('test_name', selectedTests[0]);
    formData.append('video', file, file.name);

    setLoading(true);
    void (async () => {
      try {
        const response = await uploadVideo(formData);
        if (!response.success || !response.data?.session_id) {
          throw new Error(response.error || 'Failed to upload video');
        }

        setIsUploadModalOpen(false);
        toast({
          title: 'Video Uploaded',
          description: 'Recording saved and added to patient history.',
        });
        navigate(`/patients/${id}/video-summary/${encodeURIComponent(response.data.session_id)}`);
      } catch (err) {
        toast({
          title: 'Upload Failed',
          description: err instanceof Error ? err.message : 'Could not upload video.',
          variant: 'destructive',
        });
      } finally {
        setLoading(false);
      }
    })();
  }



  const handleTestSelection = (testId: string) => {
    setSelectedTests(prev => 
      prev.includes(testId) 
        ? prev.filter(t => t !== testId)
        : [...prev, testId]
    );
  };

  const handleStartRecording = () => {
    if (selectedTests.length === 0) {
      toast({
        title: "No Tests Selected",
        description: "Please select at least one test to proceed.",
        variant: "destructive",
      });
      return;
    }

    const testId = `test-${Date.now()}`;
    navigate(`/patients/${id}/video-recording/${testId}`, {
    state: { selectedTests },
  });
  }

  if (loadingPatient) {
    return <div className="min-h-screen flex items-center justify-center">Loading patient data...</div>;
  }
  if (error) {
    return <div className="min-h-screen flex items-center justify-center text-destructive">{error}</div>;
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
              <Link to={`/patients/${id}`}>
                <Button variant="outline" size="sm">
                  <ArrowLeft className="mr-2 h-4 w-4" />
                  Back to Patient
                </Button>
              </Link>
              <div>
                <h1 className="text-3xl font-bold text-foreground">Test Selection</h1>
                <p className="text-muted-foreground mt-1">
                  {patient.firstName} {patient.lastName} - {patient.recordNumber}
                </p>
              </div>
            </div>
            <Badge className={getSeverityColor(patient.severity)}>
              {patient.severity}
            </Badge>
          </div>
        </div>
      </div>

      <div className="container mx-auto px-6 py-8">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          {/* Patient Summary - Left Side */}
          <div className="space-y-6">
            <Card>
              <CardHeader>
                <CardTitle>Patient Summary</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex flex-wrap gap-x-8 gap-y-3">
                  <div className="space-y-1 min-w-[140px]">
                    <p className="text-sm font-medium text-muted-foreground">Name</p>
                    <p className="font-semibold">{patient.firstName} {patient.lastName}</p>
                  </div>
                  <div className="space-y-1 min-w-[140px]">
                    <p className="text-sm font-medium text-muted-foreground">Age</p>
                    <p className="font-semibold">{calculateAge(patient.birthDate)} years</p>
                  </div>
                </div>
                <div className="flex flex-wrap items-start gap-x-8 gap-y-3">
                  <div className="space-y-1 min-w-[140px]">
                    <p className="text-sm font-medium text-muted-foreground">Record Number</p>
                    <p className="font-semibold">{patient.recordNumber}</p>
                  </div>
                  <div className="space-y-1 min-w-[140px]">
                    <p className="text-sm font-medium text-muted-foreground">Severity</p>
                    <Badge className={getSeverityColor(patient.severity)} variant="secondary">
                      {patient.severity}
                    </Badge>
                  </div>
                </div>
              <Separator />
              <div>
                <p className="text-sm font-medium text-muted-foreground mb-2">Recent Notes</p>
                <div className="bg-muted p-3 rounded-md">
                  <p className="text-sm">
                    {patient.doctorNotes || 'No recent notes'}
                  </p>
                </div>
              </div>
              </CardContent>
            </Card>
            {/* Test History */}
            <Card>
              <CardHeader>
                <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
                  <CardTitle className="flex items-center">
                    <FileText className="mr-2 h-5 w-5" />
                    Previous Tests
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
                <div className="space-y-3 max-h-[24rem] lg:max-h-[30rem] overflow-y-auto pr-1">
                  {filteredHistory.length > 0 ? (
                    filteredHistory.map((test) => {
                      const badgeVariant = test.indicator ? indicatorBadgeClasses[test.indicator.color] : indicatorBadgeClasses.muted;
                      const typeStyle = testTypeStyles[test.type] ?? {
                        container: 'border-l-4 border-l-slate-400/70 bg-muted/40',
                        badge: 'border border-slate-200 bg-muted text-muted-foreground',
                      };
                      const metaPieces: string[] = [];
                      if (typeof test.frameCount === 'number' && Number.isFinite(test.frameCount)) {
                        metaPieces.push(`${test.frameCount} frames`);
                      }
                      if (typeof test.fps === 'number' && Number.isFinite(test.fps)) {
                        metaPieces.push(`${test.fps.toFixed(1)} fps`);
                      }
                      if (typeof test.similarity === 'number' && Number.isFinite(test.similarity)) {
                        metaPieces.push(`Similarity ${(test.similarity * 100).toFixed(1)}%`);
                      }

                      return (
                        <div
                          key={test.id}
                          className={`border rounded-lg p-3 transition-colors ${typeStyle.container}`}
                        >
                          <div className="flex items-start justify-between gap-3">
                            <div className="space-y-1">
                              <div className="flex items-center gap-2">
                                <p className="font-medium text-sm">{test.name}</p>
                                <Badge
                                  variant="outline"
                                  className={`uppercase tracking-wide text-[10px] ${typeStyle.badge}`}
                                >
                                  {test.type.replace(/-/g, ' ')}
                                </Badge>
                              </div>
                              <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                                <span>{test.date ? test.date.toLocaleString() : 'Unknown date'}</span>
                                {metaPieces.map((piece) => (
                                  <span key={piece} className="inline-flex items-center gap-1">
                                    <span className="opacity-50">•</span>
                                    {piece}
                                  </span>
                                ))}
                              </div>
                            </div>
                            <Badge variant="secondary" className={badgeVariant}>
                              {test.indicator?.label ?? test.status}
                            </Badge>
                          </div>
                          <div className="mt-2 flex flex-wrap gap-2">
                            {test.summaryAvailable && (
                              <Link to={`/patients/${id}/video-summary/${encodeURIComponent(test.id)}`}>
                                <Button size="sm" variant="outline">
                                  View Results
                                </Button>
                              </Link>
                            )}
                            {test.videoUrl && (
                              <a href={test.videoUrl} target="_blank" rel="noreferrer">
                                <Button size="sm" variant="ghost">
                                  Open Recording
                                </Button>
                              </a>
                            )}
                          </div>
                        </div>
                      );
                    })
                  ) : testHistory.length > 0 ? (
                    <p className="text-sm text-muted-foreground text-center py-4">
                      No tests match "{testSearch}"
                    </p>
                  ) : (
                    <p className="text-sm text-muted-foreground text-center py-4">
                      No previous tests recorded
                    </p>
                  )}
                </div>
              </CardContent>
            </Card>
          </div>
          {/* Test Selection - Right Side */}
          <div className="lg:col-span-2 space-y-6">
            {/* Available Tests */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center">
                  <Activity className="mr-2 h-5 w-5" />
                  Select Tests to Perform
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid gap-4">
                  {AVAILABLE_TESTS.map((test) => (
                    <div
                      key={test.id}
                      className={`border rounded-lg p-4 cursor-pointer transition-all ${
                        selectedTests.includes(test.id)
                          ? 'border-primary bg-medical-light'
                          : 'border-border hover:bg-muted/50'
                      }`}
                      onClick={() => handleTestSelection(test.id)}
                    >
                      <div className="flex items-start justify-between">
                        <div className="flex-1">
                          <h3 className="font-semibold text-lg">{test.name}</h3>
                          <p className="text-sm text-muted-foreground mt-1">
                            {test.description}
                          </p>
                        </div>
                        <div className={`w-5 h-5 rounded border-2 flex items-center justify-center ${
                          selectedTests.includes(test.id)
                            ? 'border-primary bg-primary'
                            : 'border-muted-foreground'
                        }`}>
                          {selectedTests.includes(test.id) && (
                            <div className="w-2 h-2 bg-white rounded-full" />
                          )}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
            {/* Recording Options */}
            <Card>
              <CardHeader>
                <CardTitle>Recording Options</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid md:grid-cols-2 gap-4">
                  <Button
                    onClick={handleStartRecording}
                    disabled={selectedTests.length === 0 || loading}
                    className="h-24 flex-col bg-[hsl(var(--secondary))] text-black hover:bg-[hsl(var(--primary-hover))] hover:text-white"
                  >
                    <Video className="h-8 w-8 mb-2" />
                    <span className="font-semibold">{loading ? 'Starting Test...' : 'Record New Video'}</span>
                    <span className="text-xs opacity-90">Live recording with keypoints</span>
                  </Button>
                  <Button
                    variant="outline"
                    disabled={selectedTests.length === 0 || loading}
                    className="h-24 flex-col"
                    onClick={() => setIsUploadModalOpen(true)}
                  >
                    <Upload className="h-8 w-8 mb-2" />
                    <span className="font-semibold">{loading ? 'Uploading...' : 'Upload Video'}</span>
                    <span className="text-xs text-muted-foreground">Upload existing video file</span>
                  </Button>
                  {/* <input
                    ref={fileInputRef}
                    type='file'
                    accept='.mp4, .mov'
                    style={{display: 'none'}}
                    onChange={handleFileChange}
                  /> */}
                </div>
                {selectedTests.length > 0 && (
                  <div className="mt-4 p-4 bg-medical-light rounded-lg">
                    <p className="text-sm font-medium text-medical-blue mb-2">
                      Selected Tests ({selectedTests.length}):
                    </p>
                    <div className="flex flex-wrap gap-2">
                      {selectedTests.map(testId => {
                        const test = AVAILABLE_TESTS.find(t => t.id === testId);
                        return (
                          <Badge key={testId} variant="secondary" className="bg-primary text-primary-foreground">
                            {test?.name}
                          </Badge>
                        );
                      })}
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </div>
      </div>

      {/*Upload menu */}
  <Dialog open={isUploadModalOpen} onOpenChange={setIsUploadModalOpen}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Upload Video for Selected Tests</DialogTitle>
        </DialogHeader>
        <div className="grid gap-4 py-4">
          {/* Need to work on the dialog box formating for selecting tests */}
          <Button variant='outline' onClick={handleUploadClick} disabled={loading}>
            <Upload className="mr-2 h-4 w-4" />
            Select Video File
          </Button>
          <input
            ref={fileInputRef}
            type='file'
            accept='.mp4, .mov'
            style={{display: 'none'}}
            onChange={handleFileChange}
          />
        </div>
        <DialogFooter>
          <Button variant="secondary" onClick={() => setIsUploadModalOpen(false)} disabled={loading}>Cancel</Button>

        </DialogFooter>
      </DialogContent>
    </Dialog> 

    </div>
  );

};

export default TestSelection;
