// frontend/src/pages/VideoSummary.tsx
import React, { useState, useEffect, useMemo, ReactNode } from "react";
import { useParams, Link } from "react-router-dom";
import {
  ArrowLeft,
  Download,
  TrendingUp,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ComposedChart,
  Area,
  Label as RechartsLabel,
  Customized,
} from "recharts";
import { Test } from "@/types/patient";
import { getPatientTests } from "@/services/tests";
import { useToast } from "@/hooks/use-toast";
import {
  DoctorLabelDialog,
  MlPredictionCard,
  PerformanceStatisticsCard,
  RecordedVideoCard,
  TestHistoryCard,
  VideoSummaryHeader,
} from "@/components/video-summary/VideoSummarySections";
import {
  type AxisAggResponse,
  downloadDtwSession,
  getDtwAxisAggregate,
  getDtwSeries,
  getMlPredictionFromSession,
  getRecordingUrl,
  labelDtwSession,
  listDtwSessions,
  listPatientVideos,
  lookupDtwSession,
  type DtwSeriesCurve,
  type DtwSeriesMetrics,
  type DtwSessionMeta,
  type MlPrediction,
} from "@/services/dtw";

/* ========================= Types ========================= */

/* ======================= Helpers ======================= */
const canonicalTests = [
  "stand-and-sit",
  "finger-tapping",
  "fist-open-close",
] as const;
type CanonicalTest = (typeof canonicalTests)[number];

const isCanonical = (t?: string | null): t is CanonicalTest =>
  !!t && (canonicalTests as readonly string[]).includes(t);

const normalizeTestKey = (t?: string | null): CanonicalTest | null => {
  const s = (t ?? "").trim().toLowerCase();
  if (s === "finger-taping") return "finger-tapping"; // typo guard
  return isCanonical(s) ? (s as CanonicalTest) : null;
};

const formatHistorySummary = (test: Test): string => {
  if (test.similarity !== null && test.similarity !== undefined) {
    return `Similarity ${(test.similarity * 100).toFixed(1)}%`;
  }
  if (test.recordingFile) {
    return `Recording ${test.recordingFile}`;
  }
  return "Backend test record";
};

const resolveDurationSeconds = (test?: Test): string => {
  if (!test) return "0s";
  if (test.results?.duration) return `${test.results.duration}s`;
  if (test.frameCount && test.fps && test.fps > 0) {
    return `${(test.frameCount / test.fps).toFixed(1)}s`;
  }
  return "0s";
};

const Explainer = ({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) => (
  <details className="text-xs bg-muted/50 rounded-md p-3">
    <summary className="cursor-pointer select-none font-medium">
      {title}
    </summary>
    <div className="pt-2 text-muted-foreground leading-relaxed">{children}</div>
  </details>
);

/* ======== Chart data helpers (robust to short arrays) ======== */
function mergeOriginal(lx: number[], ly: number[], rx: number[], ry: number[]) {
  const n = Math.max(lx?.length ?? 0, rx?.length ?? 0);
  return Array.from({ length: n }).map((_, idx) => ({
    t: idx,
    live: Number.isFinite(ly?.[idx]) ? ly[idx] : null,
    ref: Number.isFinite(ry?.[idx]) ? ry[idx] : null,
  }));
}
function makePath(i: number[], j: number[]) {
  const n = Math.min(i?.length ?? 0, j?.length ?? 0);
  return Array.from({ length: n }).map((_, idx) => ({ i: i[idx], j: j[idx] }));
}
function makeAligned(k: number[], lv: number[], rv: number[]) {
  const n = Math.min(k?.length ?? 0, lv?.length ?? 0, rv?.length ?? 0);
  return Array.from({ length: n }).map((_, i) => ({
    k: k[i],
    live: lv[i],
    ref: rv[i],
    gap: Math.abs(lv[i] - rv[i]),
  }));
}

type LocalCostSeriesData = { step: number; cost: number; cum?: number };

function makeLocalCostData(
  curve?: DtwSeriesCurve
): LocalCostSeriesData[] {
  if (!curve?.local_cost_path?.x || !curve.local_cost_path.y) return [];
  const xs = curve.local_cost_path.x;
  const ys = curve.local_cost_path.y;
  const n = Math.min(xs.length, ys.length);
  const base: LocalCostSeriesData[] = [];

  // Optional cumulative (already normalized 0–1 by backend)
  const cumX = curve.cumulative_progress?.x ?? [];
  const cumY = curve.cumulative_progress?.y ?? [];

  for (let i = 0; i < n; i++) {
    const step = xs[i];
    const cost = ys[i];
    let cum: number | undefined = undefined;
    if (i < cumX.length && i < cumY.length) {
      cum = cumY[i];
    }
    base.push({ step, cost, cum });
  }
  return base;
}


/* === Custom overlay to draw vertical connectors (|live-ref|) === */
type GapSegmentsProps = {
  data: { [k: string]: number | null }[];
  xKey: string;
  y1Key: string;
  y2Key: string;
  stroke?: string;
  strokeWidth?: number;
  opacity?: number;
  xAxisMap?: Record<string, { scale: (value: number) => number }>;
  yAxisMap?: Record<string, { scale: (value: number) => number }>;
  offset?: { left?: number; top?: number };
};
const GapSegments = (props: GapSegmentsProps) => {
  const {
    data,
    xKey,
    y1Key,
    y2Key,
    stroke = "#64748b", // slate-500
    strokeWidth = 1,
    opacity = 0.35,
    xAxisMap,
    yAxisMap,
    offset,
  } = props;

  const xAxis = Object.values(xAxisMap || {})[0];
  const yAxis = Object.values(yAxisMap || {})[0];
  if (!xAxis || !yAxis) return null;

  const xScale = xAxis.scale;
  const yScale = yAxis.scale;
  const xOff = offset?.left ?? 0;
  const yOff = offset?.top ?? 0;

  return (
    <g className="gap-segments">
      {data?.map((d, idx) => {
        const xv = d?.[xKey];
        const y1 = d?.[y1Key];
        const y2 = d?.[y2Key];
        if (xv == null || y1 == null || y2 == null) return null;

        const cx = xScale(Number(xv)) + xOff;
        const cy1 = yScale(Number(y1)) + yOff;
        const cy2 = yScale(Number(y2)) + yOff;

        return (
          <line
            key={idx}
            x1={cx}
            x2={cx}
            y1={cy1}
            y2={cy2}
            stroke={stroke}
            strokeOpacity={opacity}
            strokeWidth={strokeWidth}
          />
        );
      })}
    </g>
  );
};

/* ============ Generic “aggregate axis” DTW panels ============ */
function DtwAggregatePanels({
  testKey,
  sessionId,
  axis = "x", // 'x' | 'y' | 'z'
  reduce = "mean", // 'mean' | 'median' | 'pca1'
  landmarks = "all", // 'all' or '0,1,2'
  maxPoints = 600, // bigger by default (less downsampling when full width)
}: {
  testKey: string | null;
  sessionId: string | null;
  axis?: "x" | "y" | "z";
  reduce?: "mean" | "median" | "pca1";
  landmarks?: string;
  maxPoints?: number;
}) {
  const [data, setData] = useState<AxisAggResponse | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!testKey || !sessionId) {
      setData(null);
      setErr(null);
      return;
    }
    let aborted = false;
    (async () => {
      setLoading(true);
      setErr(null);
      const response = await getDtwAxisAggregate(
        testKey,
        sessionId,
        { axis, reduce, landmarks, maxPoints }
      );
      if (!aborted) {
        if (response.success && response.data?.ok) {
          setData(response.data as AxisAggResponse);
        } else {
          setData(null);
          setErr(response.error || "Failed to load aggregated series");
        }
        setLoading(false);
      }
    })();
    return () => {
      aborted = true;
    };
  }, [testKey, sessionId, axis, reduce, landmarks, maxPoints]);

  if (!testKey || !sessionId)
    return (
      <p className="text-sm text-muted-foreground">Select a test & session.</p>
    );
  if (loading)
    return (
      <p className="text-sm text-muted-foreground">
        Loading aggregate {axis.toUpperCase()}…
      </p>
    );
  if (err) return <p className="text-sm text-red-600">{err}</p>;
  if (!data) return <p className="text-sm text-muted-foreground">No data.</p>;

  const axisLabel = axis.toUpperCase();

  // Originals + aligned
  const orig = mergeOriginal(data.live.x, data.live.y, data.ref.x, data.ref.y);
  const path = makePath(data.path.i, data.path.j);
  const aligned = makeAligned(data.warped.k, data.warped.live, data.warped.ref);

  const xCommonProps = {
    tickCount: 7,
    interval: "preserveStartEnd" as const,
    padding: { left: 8, right: 8 },
  };
  const yCommonProps = { tickCount: 5 };

  return (
    <div className="space-y-6">
      {/* -------- Top row: Original & Shortest Path -------- */}
      <div className="grid grid-cols-12 gap-8">
        {/* Original Time Series */}
        <div className="col-span-9 h-[320px]">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart
              data={orig}
              margin={{ top: 8, right: 24, left: 0, bottom: 8 }}
            >
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="t" {...xCommonProps}>
                <RechartsLabel
                  value="Series index (time)"
                  offset={-4}
                  position="insideBottom"
                />
              </XAxis>
              <YAxis {...yCommonProps} />
              <Tooltip />
              <Legend />
              <Line
                type="monotone"
                dataKey="live"
                name={`Live ${axisLabel} (aggregated)`}
                dot={false}
                strokeWidth={1.5}
              />
              <Line
                type="monotone"
                dataKey="ref"
                name={`Reference ${axisLabel} (aggregated)`}
                dot={false}
                strokeWidth={1.5}
              />
            </LineChart>
          </ResponsiveContainer>
          <div className="text-xs text-muted-foreground mt-2">
            <b>Original {axisLabel} Motion</b> — Live vs. Reference aggregated
            across landmarks (<i>{data.reduce}</i>).
          </div>
        </div>

        {/* Shortest Path */}
        <div className="col-span-3 h-[320px]">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart
              data={path}
              margin={{ top: 8, right: 12, left: 0, bottom: 8 }}
            >
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="i" {...xCommonProps}>
                <RechartsLabel value="Live index" offset={-4} position="insideBottom" />
              </XAxis>
              <YAxis dataKey="j" {...yCommonProps}>
                <RechartsLabel
                  angle={-90}
                  value="Reference index"
                  position="insideLeft"
                  offset={10}
                />
              </YAxis>
              <Tooltip />
              <Legend />
              <Line
                type="stepAfter"
                dataKey="j"
                name="DTW shortest path"
                dot={false}
                strokeWidth={1.5}
              />
            </LineChart>
          </ResponsiveContainer>
          <div className="text-xs text-muted-foreground mt-2">
            <b>DTW Shortest Path</b> — Staircase mapping from each live point to
            its aligned reference point.
          </div>
        </div>
      </div>

      {/* -------- Bottom row: Aligned comparison (full width) -------- */}
      <div className="h-[420px]">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart
            data={aligned}
            margin={{ top: 8, right: 24, left: 0, bottom: 8 }}
          >
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="k" {...xCommonProps}>
              <RechartsLabel
                value="DTW path step"
                offset={-4}
                position="insideBottom"
              />
            </XAxis>
            <YAxis {...yCommonProps} />
            <Tooltip />
            <Legend />
            <Area
              type="monotone"
              dataKey="gap"
              name="|Live–Ref|"
              fillOpacity={0.15}
              strokeOpacity={0}
            />
            <Line
              type="monotone"
              dataKey="live"
              name="Live (aligned)"
              dot={false}
              strokeWidth={1.5}
            />
            <Line
              type="monotone"
              dataKey="ref"
              name="Reference (aligned)"
              dot={false}
              strokeWidth={1.5}
            />
            <Customized
              component={
                <GapSegments
                  data={aligned}
                  xKey="k"
                  y1Key="live"
                  y2Key="ref"
                  stroke="#64748b"
                  strokeWidth={1}
                  opacity={0.35}
                />
              }
            />
          </ComposedChart>
        </ResponsiveContainer>
        <div className="text-xs text-muted-foreground mt-2">
          <b>Aligned {axisLabel} Motion</b> — After DTW, both series share a
          common timeline. Vertical lines show paired points used by DTW;
          shorter lines and a lighter band mean closer agreement.
        </div>
      </div>
    </div>
  );
}

/* ========================= Page ========================= */
const VideoSummary = () => {
  const { id, testId } = useParams<{ id: string; testId: string }>();
  const { toast } = useToast();

  // tests & videos
  const [selectedHistoryFilter, setSelectedHistoryFilter] = useState("all");
  const [testHistory, setTestHistory] = useState<Test[]>([]);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [videoList, setVideoList] = useState<string[]>([]);
  const [selectedVideo, setSelectedVideo] = useState<string | null>(null);

  // DTW REST
  const [testKey, setTestKey] = useState<CanonicalTest | null>(null);
  const [sessions, setSessions] = useState<DtwSessionMeta[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [routeResolved, setRouteResolved] = useState<boolean>(false);
  const [errMsg, setErrMsg] = useState<string | null>(null);
  const [maxPoints, setMaxPoints] = useState<number>(600);
  const [axis, setAxis] = useState<"x" | "y">("x");

  // KPI metrics
  const [metrics, setMetrics] = useState<DtwSeriesMetrics | null>(null);
  const [metricsLoading, setMetricsLoading] = useState(false);
  const [metricsErr, setMetricsErr] = useState<string | null>(null);

  // ML stage prediction
  const [mlPrediction, setMlPrediction] = useState<MlPrediction | null>(null);
  const [mlLoading, setMlLoading] = useState(false);
  const [mlErr, setMlErr] = useState<string | null>(null);

  // Doctor confirm/adjust dialog
  const [labelDialogOpen, setLabelDialogOpen] = useState(false);
  const [labelStage, setLabelStage] = useState<number>(1);
  const [labelNotes, setLabelNotes] = useState("");
  const [labelSubmitting, setLabelSubmitting] = useState(false);
  const [labelResult, setLabelResult] = useState<{ stage: number; source: string } | null>(null);

  const sortedHistory = useMemo(
    () => [...testHistory].sort((a, b) => b.date.getTime() - a.date.getTime()),
    [testHistory]
  );

  const currentTest = useMemo(
    () =>
      sortedHistory.find((test) => String(test.id) === testId) ||
      sortedHistory.find((test) => test.dtwSessionId === testId) ||
      sortedHistory.find((test) => normalizeTestKey(test.type) === testKey) ||
      sortedHistory[0],
    [sortedHistory, testId, testKey]
  );

  const filteredHistory = useMemo(
    () =>
      sortedHistory.filter(
        (test) =>
          selectedHistoryFilter === "all" || test.type === selectedHistoryFilter
      ),
    [selectedHistoryFilter, sortedHistory]
  );
  const hasUnknownHistory = useMemo(
    () => sortedHistory.some((test) => test.type === 'unknown'),
    [sortedHistory]
  );

  useEffect(() => {
    if (!id) {
      setTestHistory([]);
      setHistoryLoading(false);
      return;
    }

    let cancelled = false;
    setHistoryLoading(true);
    (async () => {
      try {
        const response = await getPatientTests(id);
        if (cancelled) return;
        setTestHistory(response.success && response.data ? response.data : []);
      } catch {
        if (!cancelled) {
          setTestHistory([]);
        }
      } finally {
        if (!cancelled) {
          setHistoryLoading(false);
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [id]);

  // Normalize selectedVideo in case backend returns "recordings/xyz.mp4"
  const normalizedVideoName =
    selectedVideo?.startsWith("recordings/")
      ? selectedVideo.split("/").slice(-1)[0]
      : selectedVideo || null;

  const videoSrc =
    normalizedVideoName != null
      ? getRecordingUrl(normalizedVideoName)
      : null;

  // Resolve route: testId may be a test type OR a session id
  useEffect(() => {
    setErrMsg(null);
    setRouteResolved(false);

    const currentTestKey = normalizeTestKey(currentTest?.type);
    if (currentTest && String(currentTest.id) === testId && currentTestKey) {
      setTestKey(currentTestKey);
      setSessionId(currentTest.dtwSessionId ?? null);
      setRouteResolved(true);
      return;
    }

    if (currentTest?.dtwSessionId && testId === currentTest.dtwSessionId && currentTestKey) {
      setTestKey(currentTestKey);
      setSessionId(currentTest.dtwSessionId);
      setRouteResolved(true);
      return;
    }

    const norm = normalizeTestKey(testId);
    if (norm) {
      setTestKey(norm);
      setSessionId(currentTest?.dtwSessionId ?? null);
      setRouteResolved(true);
      return;
    }
    if (!testId) {
      setTestKey(currentTestKey);
      setSessionId(currentTest?.dtwSessionId ?? null);
      setRouteResolved(true);
      return;
    }

    const ctrl = new AbortController();
    (async () => {
      const response = await lookupDtwSession(testId, id, ctrl.signal);
      if (response.success && response.data) {
        const key = normalizeTestKey(response.data.testName);
        if (!key) {
          setErrMsg(
            `Unknown DTW test '${response.data.testName}' for session '${response.data.sessionId}'`
          );
          setTestKey(null);
          setSessionId(null);
        } else {
          setTestKey(key);
          setSessionId(response.data.sessionId);
        }
      } else {
        setErrMsg(response.error || "Failed to resolve session from URL");
        setTestKey(null);
        setSessionId(null);
      }
      setRouteResolved(true);
    })();

    return () => ctrl.abort();
  }, [currentTest, currentTest?.dtwSessionId, currentTest?.type, testId]);

  // Videos list
  useEffect(() => {
    if (!routeResolved || !id || !testKey) return;
    const ctrl = new AbortController();
    (async () => {
      const response = await listPatientVideos(id, testKey, ctrl.signal);
      if (response.success) {
        const videos = response.data ?? [];
        if (videos.length > 0) {
          setVideoList(videos);
          setSelectedVideo(videos[0]);
        } else if (currentTest?.recordingFile) {
          // Fallback: use current test's recording file directly
          setVideoList([currentTest.recordingFile]);
          setSelectedVideo(currentTest.recordingFile);
        } else {
          setVideoList([]);
          setSelectedVideo(null);
        }
      } else {
        console.error("Error fetching videos:", response.error);
        if (currentTest?.recordingFile) {
          setVideoList([currentTest.recordingFile]);
          setSelectedVideo(currentTest.recordingFile);
        } else {
          setVideoList([]);
          setSelectedVideo(null);
        }
      }
    })();
    return () => ctrl.abort();
  }, [routeResolved, id, testKey, currentTest?.recordingFile]);

  // List DTW sessions
  useEffect(() => {
    if (!routeResolved || !testKey || !id) return;
    const ctrl = new AbortController();
    (async () => {
      const response = await listDtwSessions(testKey, id, ctrl.signal);
      if (response.success && response.data) {
        setSessions(response.data);
        setSessionId((prev) => prev ?? response.data?.[0]?.session_id ?? null);
      } else {
        setSessions([]);
        setSessionId(null);
        setErrMsg(response.error || "No DTW sessions found for this test.");
      }
    })();
    return () => ctrl.abort();
  }, [routeResolved, testKey, id]);

  // Fetch KPI metrics (distance, avg step cost, similarity) from /series
  useEffect(() => {
    if (!testKey || !sessionId) {
      setMetrics(null);
      setMetricsErr(null);
      return;
    }
    const ctrl = new AbortController();
    (async () => {
      setMetricsLoading(true);
      setMetricsErr(null);
      const response = await getDtwSeries(testKey, sessionId, 200, ctrl.signal);
      if (response.success && response.data) {
        setMetrics(response.data as DtwSeriesMetrics);
      } else {
        setMetrics(null);
        setMetricsErr(response.error || "Failed to load DTW metrics");
      }
      setMetricsLoading(false);
    })();
    return () => ctrl.abort();
  }, [testKey, sessionId]);

  // Fetch ML UPDRS stage prediction from saved DTW session
  useEffect(() => {
    if (!testKey || !sessionId) {
      setMlPrediction(null);
      setMlErr(null);
      return;
    }
    const ctrl = new AbortController();
    (async () => {
      setMlLoading(true);
      setMlErr(null);
      const response = await getMlPredictionFromSession(testKey, sessionId, ctrl.signal);
      if (response.success && response.data) {
        setMlPrediction(response.data);
      } else {
        setMlPrediction(null);
        setMlErr(response.error || "ML prediction unavailable");
      }
      setMlLoading(false);
    })();
    return () => ctrl.abort();
  }, [testKey, sessionId]);

  const onExport = async () => {
    if (!testKey || !sessionId) return;
    const response = await downloadDtwSession(testKey, sessionId);
    if (response.success && response.data) {
      const payload = response.data;
      const blob = new Blob([JSON.stringify(payload, null, 2)], {
        type: "application/json",
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `dtw_${testKey}_${sessionId}.json`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } else {
      console.error(response.error);
    }
  };

  return (
    <div className="min-h-screen bg-background">
      <VideoSummaryHeader patientId={id} canExport={!!testKey && !!sessionId} onExport={onExport} />

      {/* ===== Content: top grid then full-width chart ===== */}
      <div className="container mx-auto px-6 py-10 grid grid-cols-12 gap-10">
        {/* Left: Video (spans 8/12) */}
        <div className="col-span-12 xl:col-span-7">
          <RecordedVideoCard
            normalizedVideoName={normalizedVideoName}
            videoSrc={videoSrc}
            videoList={videoList}
            selectedVideo={selectedVideo}
            onSelectVideo={setSelectedVideo}
            duration={resolveDurationSeconds(currentTest)}
          />
        </div>

        {/* Right: History + Stats (spans 5/12) */}
        <div className="col-span-12 xl:col-span-5 space-y-10">
          <TestHistoryCard
            selectedHistoryFilter={selectedHistoryFilter}
            onFilterChange={setSelectedHistoryFilter}
            historyLoading={historyLoading}
            filteredHistory={filteredHistory}
            formatHistorySummary={formatHistorySummary}
            hasUnknownHistory={hasUnknownHistory}
          />

          <PerformanceStatisticsCard
            metricsLoading={metricsLoading}
            metricsErr={metricsErr}
            metrics={metrics}
            sessions={sessions}
            sessionId={sessionId}
          />
        </div>

        {/* ====== ML UPDRS Stage Prediction ====== */}
        <div className="col-span-12">
          <MlPredictionCard
            mlLoading={mlLoading}
            mlErr={mlErr}
            mlPrediction={mlPrediction}
            canConfirm={!!mlPrediction && !!testKey && !!sessionId}
            labelResult={labelResult}
            onOpenLabelDialog={() => {
              if (!mlPrediction) return;
              setLabelStage(mlPrediction.predicted_updrs_stage + 1);
              setLabelNotes("");
              setLabelDialogOpen(true);
            }}
          />
        </div>

        <DoctorLabelDialog
          open={labelDialogOpen}
          onOpenChange={setLabelDialogOpen}
          mlPrediction={mlPrediction}
          labelStage={labelStage}
          onLabelStageChange={setLabelStage}
          labelNotes={labelNotes}
          onLabelNotesChange={setLabelNotes}
          labelSubmitting={labelSubmitting}
          onConfirm={async () => {
            if (!testKey || !sessionId) return;
            setLabelSubmitting(true);
            const response = await labelDtwSession(testKey, sessionId, {
              confirmed_stage: labelStage,
              patient_id: id ?? null,
              notes: labelNotes.trim() || null,
            });
            if (response.success && response.data) {
              setLabelResult({ stage: labelStage, source: response.data.label_source });
              setLabelDialogOpen(false);
            } else {
              toast({
                title: 'Failed to Save Label',
                description: response.error ?? 'Unknown error',
                variant: 'destructive',
              });
            }
            setLabelSubmitting(false);
          }}
        />

        {/* ====== Bottom row: Full-width DTW card with KPIs ====== */}
        <div className="col-span-12">
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle className="flex items-center">
                  <TrendingUp className="mr-2 h-5 w-5" />
                  DTW Alignment Overview
                </CardTitle>
                <div className="flex flex-wrap items-center gap-3">
                  {/* Test picker */}
                  <Select
                    value={testKey ?? ""}
                    onValueChange={(v) => setTestKey(v as CanonicalTest)}
                  >
                    <SelectTrigger className="w-44">
                      <SelectValue placeholder="Select test" />
                    </SelectTrigger>
                    <SelectContent>
                      {canonicalTests.map((t) => (
                        <SelectItem key={t} value={t}>
                          {t}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  {/* Session picker */}
                  <Select
                    value={sessionId ?? ""}
                    onValueChange={(v) => setSessionId(v)}
                  >
                    <SelectTrigger className="w-64">
                      <SelectValue placeholder="Select session" />
                    </SelectTrigger>
                    <SelectContent>
                      {sessions.map((s) => (
                        <SelectItem key={s.session_id} value={s.session_id}>
                          {s.created_utc} • sim{" "}
                          {s.similarity?.toFixed(2) ?? "-"}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  {/* Axis */}
                  <Select
                    value={axis}
                    onValueChange={(v) => setAxis(v as "x" | "y")}
                  >
                    <SelectTrigger className="w-28">
                      <SelectValue placeholder="Axis" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="x">X axis</SelectItem>
                      <SelectItem value="y">Y axis</SelectItem>
                    </SelectContent>
                  </Select>
                  {/* Downsample */}
                  <Select
                    value={String(maxPoints)}
                    onValueChange={(v) => setMaxPoints(Number(v))}
                  >
                    <SelectTrigger className="w-28">
                      <SelectValue placeholder="Points" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="300">300 pts</SelectItem>
                      <SelectItem value="600">600 pts</SelectItem>
                      <SelectItem value="900">900 pts</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
            </CardHeader>

            <CardContent className="space-y-4">
              {/* KPI Strip */}
             {/* Overall KPIs */}
<div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
  <div className="p-3 rounded-md bg-muted">
    <div className="text-xs text-muted-foreground">
      Overall Similarity (0–1)
    </div>
    <div className="mt-1 text-2xl font-semibold">
      {metricsLoading
        ? "…"
        : (
            metrics?.similarity_overall ??
            metrics?.similarity ??
            sessions.find((s) => s.session_id === sessionId)?.similarity ??
            0
          ).toFixed(3)}
    </div>
  </div>
  <div className="p-3 rounded-md bg-muted">
    <div className="text-xs text-muted-foreground">
      Positional DTW Distance
    </div>
    <div className="mt-1 text-2xl font-semibold">
      {metricsLoading
        ? "…"
        : (
            metrics?.distance_pos ??
            metrics?.distance ??
            0
          ).toFixed(3)}
    </div>
  </div>
  <div className="p-3 rounded-md bg-muted">
    <div className="text-xs text-muted-foreground">
      Avg. Step Cost (Position)
    </div>
    <div className="mt-1 text-2xl font-semibold">
      {metricsLoading
        ? "…"
        : (
            metrics?.avg_step_pos ??
            metrics?.avg_step_cost ??
            0
          ).toFixed(3)}
    </div>
  </div>
</div>

{/* Per-channel similarity breakdown */}
{metrics && (
  <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mt-3">
    <div className="p-3 rounded-md bg-muted/70">
      <div className="text-xs text-muted-foreground">
        Position Similarity
      </div>
      <div className="mt-1 text-lg font-semibold">
        {(metrics.similarity_pos ?? 0).toFixed(3)}
      </div>
    </div>
    <div className="p-3 rounded-md bg-muted/70">
      <div className="text-xs text-muted-foreground">
        Amplitude Similarity
      </div>
      <div className="mt-1 text-lg font-semibold">
        {(metrics.similarity_amp ?? 0).toFixed(3)}
      </div>
    </div>
    <div className="p-3 rounded-md bg-muted/70">
      <div className="text-xs text-muted-foreground">
        Speed Similarity
      </div>
      <div className="mt-1 text-lg font-semibold">
        {(metrics.similarity_spd ?? 0).toFixed(3)}
      </div>
    </div>
  </div>
)}

              {metricsErr && (
                <div className="text-sm text-red-600">{metricsErr}</div>
              )}

              <Explainer title="How to read this section">
                Top-left shows the original aggregated motion on the selected
                axis. Top-right shows the DTW staircase mapping (live →
                reference). The large bottom chart shows both signals after DTW
                alignment; the shaded band and vertical connectors visualize
                point-to-point differences. Similarity is a monotonic transform
                of the mean per-step cost (higher ≈ better); distance is the
                total DTW cost along the path.
              </Explainer>
                  {metrics?.series && (
  <div className="mt-6 grid grid-cols-1 lg:grid-cols-3 gap-6">
    {([
      ["Position DTW (local cost)", metrics.series.position, "Position"],
      ["Amplitude DTW (local cost)", metrics.series.amplitude, "Amplitude"],
      ["Speed DTW (local cost)", metrics.series.speed, "Speed"],
    ] as const).map(([title, curve, label]) => {
      const data = makeLocalCostData(curve);
      return (
        <div key={label} className="h-[260px]">
          <h3 className="text-sm font-semibold mb-2">{title}</h3>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart
              data={data}
              margin={{ top: 8, right: 16, left: 0, bottom: 8 }}
            >
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis
                dataKey="step"
                tickCount={5}
                padding={{ left: 8, right: 8 }}
              >
                <RechartsLabel
                  value="DTW path step"
                  offset={-4}
                  position="insideBottom"
                />
              </XAxis>
              <YAxis tickCount={5} />
              <Tooltip />
              <Legend />
              <Line
                type="monotone"
                dataKey="cost"
                name="Local cost"
                dot={false}
                strokeWidth={1.5}
              />
              {/* Optional: overlay cumulative progress [0–1] on same axis */}
              <Line
                type="monotone"
                dataKey="cum"
                name="Cumulative progress"
                dot={false}
                strokeDasharray="4 4"
                strokeWidth={1}
              />
            </LineChart>
          </ResponsiveContainer>
          <div className="text-xs text-muted-foreground mt-1">
            {label} DTW: each point is the cost at one step along the
            shortest path; the dashed line shows how far along the path
            you are (0 → 1).
          </div>
        </div>
      );
    })}
  </div>
)}
              <DtwAggregatePanels
                testKey={testKey}
                sessionId={sessionId}
                axis={axis}
                reduce="mean"
                landmarks="all"
                maxPoints={maxPoints}
              />
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
};

export default VideoSummary;
