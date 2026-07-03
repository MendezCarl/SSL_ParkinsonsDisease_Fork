import { useEffect, useState, useMemo, useCallback } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import {
  ArrowLeft,
  Activity,
  FileText,
  Stethoscope,
  Calendar,
  TrendingUp,
  TrendingDown,
  Minus,
  PlayCircle,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Patient, Test, LabResultEntry, DoctorNoteEntry } from "@/types/patient";
import { getSeverityColor, calculateAge } from "@/lib/utils";
import { getPatient } from "@/services/patients";
import { getPatientTests } from "@/services/tests";
import { useToast } from "@/hooks/use-toast";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from "recharts";

interface TimelineEvent {
  id: string;
  date: Date;
  type: "test" | "lab_result" | "doctor_note";
  title: string;
  description?: string;
  data: Test | LabResultEntry | DoctorNoteEntry;
  severity?: string;
}

type TrendPoint = {
  index: number;
  date: string;
  similarity: number;
  distance: number;
};

export default function Timeline() {
  const { patientId } = useParams<{ patientId: string }>();
  const navigate = useNavigate();
  const { toast } = useToast();
  const [patient, setPatient] = useState<Patient | null>(null);
  const [tests, setTests] = useState<Test[]>([]);
  const [loading, setLoading] = useState(true);
  const [filterType, setFilterType] = useState<"all" | "test" | "lab_result" | "doctor_note">("all");
  const [sortOrder, setSortOrder] = useState<"asc" | "desc">("desc");

  const loadData = useCallback(async () => {
    if (!patientId) return;
    
    setLoading(true);
    try {
      const [patientResponse, testsResponse] = await Promise.all([
        getPatient(patientId),
        getPatientTests(patientId),
      ]);

      if (patientResponse.success && patientResponse.data) {
        setPatient(patientResponse.data);
      } else {
        toast({
          title: "Error",
          description: patientResponse.error || "Failed to load patient data",
          variant: "destructive",
        });
      }

      if (testsResponse.success && testsResponse.data) {
        setTests(testsResponse.data);
      } else {
        toast({
          title: "Error",
          description: testsResponse.error || "Failed to load test data",
          variant: "destructive",
        });
      }
    } catch (error) {
      console.error("Error loading data:", error);
      toast({
        title: "Error",
        description: "An unexpected error occurred",
        variant: "destructive",
      });
    } finally {
      setLoading(false);
    }
  }, [patientId, toast]);

  useEffect(() => {
    if (!patientId) return;
    void loadData();
  }, [patientId, loadData]);

  // Combine all events into a timeline
  const timelineEvents = useMemo(() => {
    if (!patient) return [];

    const events: TimelineEvent[] = [];

    // Add test events
    tests.forEach((test) => {
      events.push({
        id: `test-${test.id}`,
        date: test.date,
        type: "test",
        title: test.name,
        description: `Status: ${test.status}`,
        data: test,
      });
    });

    // Add lab result events
    patient.labResultsHistory?.forEach((labResult) => {
      events.push({
        id: `lab-${labResult.id}`,
        date: labResult.date,
        type: "lab_result",
        title: "Lab Results",
        description: labResult.results,
        data: labResult,
      });
    });

    // Add doctor note events
    patient.doctorNotesHistory?.forEach((note) => {
      events.push({
        id: `note-${note.id}`,
        date: note.date,
        type: "doctor_note",
        title: "Doctor's Note",
        description: note.note,
        data: note,
      });
    });

    const filtered =
      filterType === "all" ? events : events.filter((e) => e.type === filterType);

    return filtered.sort((a, b) => {
      const diff = b.date.getTime() - a.date.getTime();
      return sortOrder === "desc" ? diff : -diff;
    });
  }, [patient, tests, filterType, sortOrder]);

  const testPerformanceTrends = useMemo(() => {
    const testsByType: Record<string, Test[]> = {};
    
    tests.forEach((test) => {
      if (!testsByType[test.type]) {
        testsByType[test.type] = [];
      }
      testsByType[test.type].push(test);
    });

    const trends: Record<string, { data: TrendPoint[]; trend: "up" | "down" | "stable" }> = {};

    Object.entries(testsByType).forEach(([type, typeTests]) => {
      const sorted = [...typeTests].sort((a, b) => a.date.getTime() - b.date.getTime());
      const chartData = sorted.map((test, index) => ({
        index: index + 1,
        date: test.date.toLocaleDateString(),
        similarity: test.similarity || 0,
        distance: test.distance || 0,
      }));

      let trend: "up" | "down" | "stable" = "stable";
      if (chartData.length >= 2) {
        const firstSimilarity = chartData[0].similarity;
        const lastSimilarity = chartData[chartData.length - 1].similarity;
        const diff = lastSimilarity - firstSimilarity;
        if (diff > 5) trend = "up";
        else if (diff < -5) trend = "down";
      }

      trends[type] = { data: chartData, trend };
    });

    return trends;
  }, [tests]);

  const getEventIcon = (type: TimelineEvent["type"]) => {
    switch (type) {
      case "test":
        return <Activity className="h-5 w-5" />;
      case "lab_result":
        return <FileText className="h-5 w-5" />;
      case "doctor_note":
        return <Stethoscope className="h-5 w-5" />;
    }
  };

  const getEventColor = (type: TimelineEvent["type"]) => {
    switch (type) {
      case "test":
        return "bg-blue-500";
      case "lab_result":
        return "bg-green-500";
      case "doctor_note":
        return "bg-purple-500";
    }
  };

  const getTrendIcon = (trend: "up" | "down" | "stable") => {
    switch (trend) {
      case "up":
        return <TrendingUp className="h-4 w-4 text-green-500" />;
      case "down":
        return <TrendingDown className="h-4 w-4 text-red-500" />;
      case "stable":
        return <Minus className="h-4 w-4 text-gray-500" />;
    }
  };

  const formatTestType = (type: string) => {
    return type
      .split("-")
      .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
      .join(" ");
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary"></div>
      </div>
    );
  }

  if (!patient) {
    return (
      <div className="container mx-auto px-4 py-8">
        <div className="text-center">
          <h2 className="text-2xl font-bold mb-4">Patient not found</h2>
          <Button asChild>
            <Link to="/patients">Back to Patients</Link>
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="container mx-auto px-4 py-8">
      {/* Header */}
      <div className="mb-6">
        <Button variant="ghost" asChild className="mb-4">
          <Link to={`/patients/${patientId}`}>
            <ArrowLeft className="mr-2 h-4 w-4" />
            Back to Patient Details
          </Link>
        </Button>

        <div className="flex justify-between items-start">
          <div>
            <h1 className="text-3xl font-bold mb-2">
              {patient.firstName} {patient.lastName}
            </h1>
            <div className="flex gap-4 text-sm text-muted-foreground">
              <span>Record: {patient.recordNumber}</span>
              <span>Age: {calculateAge(patient.birthDate)}</span>
              <Badge className={getSeverityColor(patient.severity)}>
                {patient.severity}
              </Badge>
            </div>
          </div>
        </div>
      </div>

      {/* Tabs for different views */}
      <Tabs defaultValue="timeline" className="space-y-6">
        <TabsList>
          <TabsTrigger value="timeline">Timeline</TabsTrigger>
          <TabsTrigger value="performance">Performance Trends</TabsTrigger>
          <TabsTrigger value="summary">Summary</TabsTrigger>
        </TabsList>

        {/* Timeline View */}
        <TabsContent value="timeline" className="space-y-4">
          <Card>
            <CardHeader>
              <div className="flex justify-between items-center">
                <CardTitle>Patient Timeline</CardTitle>
                <div className="flex gap-2">
                  <Select value={filterType} onValueChange={(value) => setFilterType(value as typeof filterType)}>
                    <SelectTrigger className="w-[180px]">
                      <SelectValue placeholder="Filter by type" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">All Events</SelectItem>
                      <SelectItem value="test">Tests Only</SelectItem>
                      <SelectItem value="lab_result">Lab Results Only</SelectItem>
                      <SelectItem value="doctor_note">Doctor Notes Only</SelectItem>
                    </SelectContent>
                  </Select>
                  <Select value={sortOrder} onValueChange={(value) => setSortOrder(value as typeof sortOrder)}>
                    <SelectTrigger className="w-[180px]">
                      <SelectValue placeholder="Sort order" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="desc">Newest First</SelectItem>
                      <SelectItem value="asc">Oldest First</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
            </CardHeader>
            <CardContent>
              <ScrollArea className="h-[600px] pr-4">
                {timelineEvents.length === 0 ? (
                  <div className="text-center py-8 text-muted-foreground">
                    No events found for this patient
                  </div>
                ) : (
                  <div className="relative">
                    {/* Timeline line */}
                    <div className="absolute left-[23px] top-0 bottom-0 w-0.5 bg-border" />

                    {/* Timeline events */}
                    <div className="space-y-6">
                      {timelineEvents.map((event, index) => (
                        <div key={event.id} className="relative pl-12">
                          {/* Timeline dot */}
                          <div
                            className={`absolute left-0 w-12 h-12 rounded-full ${getEventColor(
                              event.type
                            )} flex items-center justify-center text-white shadow-md`}
                          >
                            {getEventIcon(event.type)}
                          </div>

                          {/* Event card */}
                          <Card className="ml-4">
                            <CardHeader className="pb-3">
                              <div className="flex justify-between items-start">
                                <div>
                                  <CardTitle className="text-lg">{event.title}</CardTitle>
                                  <p className="text-sm text-muted-foreground mt-1">
                                    <Calendar className="inline h-3 w-3 mr-1" />
                                    {event.date.toLocaleDateString()} at{" "}
                                    {event.date.toLocaleTimeString()}
                                  </p>
                                </div>
                                <Badge
                                  variant={
                                    event.type === "test"
                                      ? "default"
                                      : event.type === "lab_result"
                                      ? "secondary"
                                      : "outline"
                                  }
                                >
                                  {event.type.replace("_", " ")}
                                </Badge>
                              </div>
                            </CardHeader>
                            <CardContent>
                              {event.type === "test" && (
                                <div className="space-y-2">
                                  <p className="text-sm">{event.description}</p>
                                  {(event.data as Test).similarity !== null && (
                                    <div className="flex gap-4 text-sm">
                                      <span>
                                        Similarity: {((event.data as Test).similarity! * 100).toFixed(1)}%
                                      </span>
                                      {(event.data as Test).distance !== null && (
                                        <span>
                                          Distance: {(event.data as Test).distance!.toFixed(2)}
                                        </span>
                                      )}
                                    </div>
                                  )}
                                  {(event.data as Test).recordingUrl && (
                                    <Button
                                      size="sm"
                                      variant="outline"
                                      onClick={() =>
                                        navigate(
                                          `/patients/${patientId}/video-summary/${(event.data as Test).id}`
                                        )
                                      }
                                    >
                                      <PlayCircle className="mr-2 h-4 w-4" />
                                      View Recording
                                    </Button>
                                  )}
                                </div>
                              )}
                              {event.type === "lab_result" && (
                                <div className="space-y-2">
                                  <p className="text-sm whitespace-pre-wrap">{event.description}</p>
                                  <p className="text-xs text-muted-foreground">
                                    Added by: {(event.data as LabResultEntry).addedBy}
                                  </p>
                                </div>
                              )}
                              {event.type === "doctor_note" && (
                                <div className="space-y-2">
                                  <p className="text-sm whitespace-pre-wrap">{event.description}</p>
                                  <p className="text-xs text-muted-foreground">
                                    Added by: {(event.data as DoctorNoteEntry).addedBy}
                                  </p>
                                </div>
                              )}
                            </CardContent>
                          </Card>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </ScrollArea>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Performance Trends View */}
        <TabsContent value="performance" className="space-y-4">
          {Object.keys(testPerformanceTrends).length === 0 ? (
            <Card>
              <CardContent className="py-8 text-center text-muted-foreground">
                No test data available for performance analysis
              </CardContent>
            </Card>
          ) : (
            Object.entries(testPerformanceTrends).map(([testType, trendData]) => (
              <Card key={testType}>
                <CardHeader>
                  <div className="flex justify-between items-center">
                    <CardTitle>{formatTestType(testType)}</CardTitle>
                    <div className="flex items-center gap-2">
                      {getTrendIcon(trendData.trend)}
                      <span className="text-sm text-muted-foreground">
                        {trendData.trend === "up"
                          ? "Improving"
                          : trendData.trend === "down"
                          ? "Declining"
                          : "Stable"}
                      </span>
                    </div>
                  </div>
                </CardHeader>
                <CardContent>
                  {trendData.data.length > 0 ? (
                    <ResponsiveContainer width="100%" height={300}>
                      <LineChart data={trendData.data}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis dataKey="date" />
                        <YAxis />
                        <Tooltip />
                        <Legend />
                        <Line
                          type="monotone"
                          dataKey="similarity"
                          stroke="#8884d8"
                          name="Similarity (%)"
                          strokeWidth={2}
                        />
                        <Line
                          type="monotone"
                          dataKey="distance"
                          stroke="#82ca9d"
                          name="Distance"
                          strokeWidth={2}
                        />
                      </LineChart>
                    </ResponsiveContainer>
                  ) : (
                    <div className="text-center py-8 text-muted-foreground">
                      No data available for this test type
                    </div>
                  )}
                </CardContent>
              </Card>
            ))
          )}
        </TabsContent>

        {/* Summary View */}
        <TabsContent value="summary" className="space-y-4">
          <div className="grid gap-4 md:grid-cols-3">
            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Total Tests</CardTitle>
                <Activity className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">{tests.length}</div>
                <p className="text-xs text-muted-foreground">
                  {tests.filter((t) => t.status === "completed").length} completed
                </p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Lab Results</CardTitle>
                <FileText className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">
                  {patient.labResultsHistory?.length || 0}
                </div>
                <p className="text-xs text-muted-foreground">
                  {patient.labResultsHistory?.[0]?.date
                    ? `Last: ${new Date(patient.labResultsHistory[0].date).toLocaleDateString()}`
                    : "No results"}
                </p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Doctor Notes</CardTitle>
                <Stethoscope className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">
                  {patient.doctorNotesHistory?.length || 0}
                </div>
                <p className="text-xs text-muted-foreground">
                  {patient.doctorNotesHistory?.[0]?.date
                    ? `Last: ${new Date(patient.doctorNotesHistory[0].date).toLocaleDateString()}`
                    : "No notes"}
                </p>
              </CardContent>
            </Card>
          </div>

          {/* Test Type Breakdown */}
          <Card>
            <CardHeader>
              <CardTitle>Test Type Breakdown</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                {[
                  'finger-tapping',
                  'stand-and-sit',
                  'fist-open-close',
                  ...(tests.some((t) => t.type === 'unknown') ? ['unknown'] : []),
                ].map((type) => {
                  const typeTests = tests.filter((t) => t.type === type);
                  const completedTests = typeTests.filter((t) => t.status === "completed");
                  const avgSimilarity =
                    completedTests.length > 0
                      ? completedTests.reduce(
                          (acc, test) => acc + (test.similarity || 0),
                          0
                        ) / completedTests.length
                      : 0;

                  return (
                    <div key={type}>
                      <div className="flex justify-between items-center mb-2">
                        <span className="font-medium">{formatTestType(type)}</span>
                        <span className="text-sm text-muted-foreground">
                          {typeTests.length} tests
                        </span>
                      </div>
                      <div className="flex items-center gap-2">
                        <div className="flex-1 bg-secondary h-2 rounded-full overflow-hidden">
                          <div
                            className="bg-primary h-full"
                            style={{ width: `${avgSimilarity * 100}%` }}
                          />
                        </div>
                        <span className="text-sm font-medium">
                          {(avgSimilarity * 100).toFixed(1)}%
                        </span>
                      </div>
                    </div>
                  );
                })}
              </div>
            </CardContent>
          </Card>

          {/* Recent Activity */}
          <Card>
            <CardHeader>
              <CardTitle>Recent Activity</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                {timelineEvents.slice(0, 5).map((event) => (
                  <div key={event.id} className="flex items-start gap-3">
                    <div
                      className={`w-8 h-8 rounded-full ${getEventColor(
                        event.type
                      )} flex items-center justify-center text-white flex-shrink-0`}
                    >
                      {getEventIcon(event.type)}
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="font-medium truncate">{event.title}</p>
                      <p className="text-sm text-muted-foreground">
                        {event.date.toLocaleDateString()}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
