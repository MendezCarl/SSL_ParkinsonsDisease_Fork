// frontend/src/pages/VideoSummary.tsx
import React, { useState, useEffect, ReactNode } from 'react';
import { useParams, Link } from 'react-router-dom';
import { ArrowLeft, Download, Calendar, TrendingUp, FileText, BarChart3 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import {
  ResponsiveContainer,
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ComposedChart, Area, Label, Customized,
} from 'recharts';
import { Test } from '@/types/patient';

/* ========================= Types ========================= */
type DtwSessionMeta = {
  session_id: string;
  created_utc: string;
  model?: 'hands' | 'pose';
  live_len?: number;
  ref_len?: number;
  distance?: number;
  similarity?: number;
};

type AxisAggResponse = {
  ok: boolean;
  axis: 'x' | 'y' | 'z';
  reduce: 'mean' | 'median' | 'pca1';
  landmarks: 'all' | number[];
  live: { x: number[]; y: number[] };
  ref: { x: number[]; y: number[] };
  path: { i: number[]; j: number[] };
  warped: { k: number[]; live: number[]; ref: number[] };
};

type DtwSeriesMetrics = {
  ok: boolean;
  distance: number;
  avg_step_cost: number;
  similarity: number;
};

/* ===================== Mock (unchanged) ===================== */
const mockTestHistory: Test[] = [
  {
    id: 'stand-and-sit',
    patientId: '1',
    name: 'Stand and Sit Assessment',
    type: 'stand-and-sit',
    date: new Date('2024-01-20'),
    status: 'completed',
    results: { duration: 45, score: 78, keypoints: [], analysis: 'Moderate improvement in mobility' }
  },
  {
    id: 'palm-open',
    patientId: '1',
    name: 'Palm Open Evaluation',
    type: 'palm-open',
    date: new Date('2024-01-18'),
    status: 'completed',
    results: { duration: 30, score: 82, keypoints: [], analysis: 'Good hand dexterity maintained' }
  }
];

const mockStats = {
  averageScore: 77,
  improvement: '+8%',
  totalTests: 12,
  averageDuration: '42s',
  tremor: 'Mild',
  balance: 'Good',
  coordination: 'Moderate',
  mobility: 'Good'
};

/* ======================= Helpers ======================= */
const canonicalTests = ['stand-and-sit','finger-tapping','fist-open-close'] as const;
type CanonicalTest = typeof canonicalTests[number];

const isCanonical = (t?: string | null): t is CanonicalTest =>
  !!t && (canonicalTests as readonly string[]).includes(t);

const normalizeTestKey = (t?: string | null): CanonicalTest | null => {
  const s = (t ?? '').trim().toLowerCase();
  if (s === 'finger-taping') return 'finger-tapping'; // typo guard
  return isCanonical(s) ? (s as CanonicalTest) : null;
};

async function fetchJSON<T>(url: string, signal?: AbortSignal): Promise<T> {
  const res = await fetch(url, { signal });
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(text || `HTTP ${res.status}`);
  }
  return res.json();
}

const Explainer = ({ title, children }: { title: string; children: ReactNode }) => (
  <details className="text-xs bg-muted/50 rounded-md p-3">
    <summary className="cursor-pointer select-none font-medium">{title}</summary>
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

/* === Custom overlay to draw vertical connectors (|live-ref|) === */
type GapSegmentsProps = {
  data: { [k: string]: number | null }[];
  xKey: string;
  y1Key: string;
  y2Key: string;
  stroke?: string;
  strokeWidth?: number;
  opacity?: number;
};
const GapSegments: React.FC<any & GapSegmentsProps> = (props) => {
  const {
    data, xKey, y1Key, y2Key,
    stroke = '#64748b', // slate-500
    strokeWidth = 1,
    opacity = 0.35,
    xAxisMap, yAxisMap, offset,
  } = props;

  const xAxis = Object.values(xAxisMap || {})[0] as any;
  const yAxis = Object.values(yAxisMap || {})[0] as any;
  if (!xAxis || !yAxis) return null;

  const xScale = xAxis.scale;
  const yScale = yAxis.scale;
  const xOff = (offset?.left ?? 0);
  const yOff = (offset?.top ?? 0);

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
            x1={cx} x2={cx}
            y1={cy1} y2={cy2}
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
  axis = 'x',             // 'x' | 'y' | 'z'
  reduce = 'mean',        // 'mean' | 'median' | 'pca1'
  landmarks = 'all',      // 'all' or '0,1,2'
  maxPoints = 600,        // bigger by default (less downsampling when full width)
}: {
  testKey: string | null;
  sessionId: string | null;
  axis?: 'x' | 'y' | 'z';
  reduce?: 'mean' | 'median' | 'pca1';
  landmarks?: string;
  maxPoints?: number;
}) {
  const [data, setData] = useState<AxisAggResponse | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!testKey || !sessionId) { setData(null); setErr(null); return; }
    let aborted = false;
    (async () => {
      setLoading(true); setErr(null);
      try {
        const res = await fetch(
          `/api/dtw/sessions/${encodeURIComponent(testKey)}/${encodeURIComponent(sessionId)}/axis_agg` +
          `?axis=${axis}&reduce=${reduce}&landmarks=${encodeURIComponent(landmarks)}&max_points=${maxPoints}`
        );
        const json = await res.json();
        if (!aborted) {
          if (json?.ok) setData(json as AxisAggResponse);
          else {
            setData(null);
            setErr(json?.detail || 'Failed to load aggregated series');
          }
        }
      } catch (e: any) {
        if (!aborted) setErr(e?.message || 'Failed to load aggregated series');
      } finally {
        if (!aborted) setLoading(false);
      }
    })();
    return () => { aborted = true; };
  }, [testKey, sessionId, axis, reduce, landmarks, maxPoints]);

  if (!testKey || !sessionId) return <p className="text-sm text-muted-foreground">Select a test & session.</p>;
  if (loading) return <p className="text-sm text-muted-foreground">Loading aggregate {axis.toUpperCase()}…</p>;
  if (err) return <p className="text-sm text-red-600">{err}</p>;
  if (!data) return <p className="text-sm text-muted-foreground">No data.</p>;

  const axisLabel = axis.toUpperCase();

  // Originals + aligned
  const orig = mergeOriginal(data.live.x, data.live.y, data.ref.x, data.ref.y);
  const path = makePath(data.path.i, data.path.j);
  const aligned = makeAligned(data.warped.k, data.warped.live, data.warped.ref);

  const xCommonProps = { tickCount: 7, interval: 'preserveStartEnd' as const, padding: { left: 8, right: 8 } };
  const yCommonProps = { tickCount: 5 };

  return (
    <div className="space-y-6">
      {/* -------- Top row: Original & Shortest Path -------- */}
      <div className="grid grid-cols-12 gap-8">
        {/* Original Time Series */}
        <div className="col-span-9 h-[320px]">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={orig} margin={{ top: 8, right: 24, left: 0, bottom: 8 }}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="t" {...xCommonProps}>
                <Label value="Series index (time)" offset={-4} position="insideBottom" />
              </XAxis>
              <YAxis {...yCommonProps} />
              <Tooltip />
              <Legend />
              <Line type="monotone" dataKey="live" name={`Live ${axisLabel} (aggregated)`} dot={false} strokeWidth={1.5} />
              <Line type="monotone" dataKey="ref"  name={`Reference ${axisLabel} (aggregated)`}  dot={false} strokeWidth={1.5} />
            </LineChart>
          </ResponsiveContainer>
          <div className="text-xs text-muted-foreground mt-2">
            <b>Original {axisLabel} Motion</b> — Live vs. Reference aggregated across landmarks (<i>{data.reduce}</i>).
          </div>
        </div>

        {/* Shortest Path */}
        <div className="col-span-3 h-[320px]">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={path} margin={{ top: 8, right: 12, left: 0, bottom: 8 }}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="i" {...xCommonProps}>
                <Label value="Live index" offset={-4} position="insideBottom" />
              </XAxis>
              <YAxis dataKey="j" {...yCommonProps}>
                <Label angle={-90} value="Reference index" position="insideLeft" offset={10} />
              </YAxis>
              <Tooltip />
              <Legend />
              <Line type="stepAfter" dataKey="j" name="DTW shortest path" dot={false} strokeWidth={1.5} />
            </LineChart>
          </ResponsiveContainer>
          <div className="text-xs text-muted-foreground mt-2">
            <b>DTW Shortest Path</b> — Staircase mapping from each live point to its aligned reference point.
          </div>
        </div>
      </div>

      {/* -------- Bottom row: Aligned comparison (full width) -------- */}
      <div className="h-[420px]">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={aligned} margin={{ top: 8, right: 24, left: 0, bottom: 8 }}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="k" {...xCommonProps}>
              <Label value="DTW path step" offset={-4} position="insideBottom" />
            </XAxis>
            <YAxis {...yCommonProps} />
            <Tooltip />
            <Legend />
            <Area type="monotone" dataKey="gap" name="|Live–Ref|" fillOpacity={0.15} strokeOpacity={0} />
            <Line type="monotone" dataKey="live" name="Live (aligned)" dot={false} strokeWidth={1.5} />
            <Line type="monotone" dataKey="ref"  name="Reference (aligned)" dot={false} strokeWidth={1.5} />
            <Customized component={
              <GapSegments data={aligned} xKey="k" y1Key="live" y2Key="ref" stroke="#64748b" strokeWidth={1} opacity={0.35} />
            }/>
          </ComposedChart>
        </ResponsiveContainer>
        <div className="text-xs text-muted-foreground mt-2">
          <b>Aligned {axisLabel} Motion</b> — After DTW, both series share a common timeline. Vertical lines show paired points used
          by DTW; shorter lines and a lighter band mean closer agreement.
        </div>
      </div>
    </div>
  );
}

/* ========================= Page ========================= */
const VideoSummary = () => {
  const { id, testId } = useParams<{ id: string; testId: string }>();

  // tests & videos
  const [selectedHistoryFilter, setSelectedHistoryFilter] = useState('all');
  const [testHistory] = useState<Test[]>(mockTestHistory);
  const [videoList, setVideoList] = useState<string[]>([]);
  const [selectedVideo, setSelectedVideo] = useState<string | null>(null);

  // DTW REST
  const [testKey, setTestKey] = useState<CanonicalTest | null>(null);
  const [sessions, setSessions] = useState<DtwSessionMeta[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [routeResolved, setRouteResolved] = useState<boolean>(false);
  const [errMsg, setErrMsg] = useState<string | null>(null);
  const [maxPoints, setMaxPoints] = useState<number>(600);
  const [axis, setAxis] = useState<'x' | 'y'>('x');

  // KPI metrics
  const [metrics, setMetrics] = useState<DtwSeriesMetrics | null>(null);
  const [metricsLoading, setMetricsLoading] = useState(false);
  const [metricsErr, setMetricsErr] = useState<string | null>(null);

  const currentTest = testHistory.find(t => t.type === testId) || testHistory[0];
  const filteredHistory = testHistory.filter(test =>
    selectedHistoryFilter === 'all' || test.type === selectedHistoryFilter
  );

  // Resolve route: testId may be a test type OR a session id
  useEffect(() => {
    setErrMsg(null);
    setRouteResolved(false);

    const norm = normalizeTestKey(testId);
    if (norm) {
      setTestKey(norm);
      setSessionId(null);
      setRouteResolved(true);
      return;
    }
    if (!testId) { setRouteResolved(true); return; }

    const ctrl = new AbortController();
    (async () => {
      try {
        const data = await fetchJSON<{ testName: string; sessionId: string }>(
          `/api/dtw/sessions/lookup/${encodeURIComponent(testId)}`, ctrl.signal
        );
        const key = normalizeTestKey(data.testName);
        if (!key) throw new Error(`Unknown DTW test '${data.testName}' for session '${data.sessionId}'`);
        setTestKey(key);
        setSessionId(data.sessionId);
      } catch (e: any) {
        setErrMsg(e?.message || 'Failed to resolve session from URL');
        setTestKey(null);
        setSessionId(null);
      } finally {
        setRouteResolved(true);
      }
    })();

    return () => ctrl.abort();
  }, [testId]);

  // Videos
  useEffect(() => {
    if (!routeResolved || !id || !testKey) return;
    const ctrl = new AbortController();
    (async () => {
      try {
        const data = await fetchJSON<{ success: boolean; videos: string[] }>(
          `/api/videos/${encodeURIComponent(id)}/${encodeURIComponent(testKey)}`, ctrl.signal
        );
        if (data.success && data.videos?.length > 0) {
          setVideoList(data.videos);
          setSelectedVideo(data.videos[0]);
        } else {
          setVideoList([]);
          setSelectedVideo(null);
        }
      } catch {
        setVideoList([]);
        setSelectedVideo(null);
      }
    })();
    return () => ctrl.abort();
  }, [routeResolved, id, testKey]);

  // List DTW sessions
  useEffect(() => {
    if (!routeResolved || !testKey) return;
    const ctrl = new AbortController();
    (async () => {
      try {
        const data = await fetchJSON<DtwSessionMeta[]>(
          `/api/dtw/sessions/${encodeURIComponent(testKey)}`, ctrl.signal
        );
        setSessions(data);
        setSessionId(prev => prev ?? data[0]?.session_id ?? null);
      } catch (e: any) {
        setSessions([]);
        setSessionId(null);
        setErrMsg(e?.message || "No DTW sessions found for this test.");
      }
    })();
    return () => ctrl.abort();
  }, [routeResolved, testKey]);

  // Fetch KPI metrics (distance, avg step cost, similarity) from /series
  useEffect(() => {
    if (!testKey || !sessionId) { setMetrics(null); setMetricsErr(null); return; }
    const ctrl = new AbortController();
    (async () => {
      try {
        setMetricsLoading(true); setMetricsErr(null);
        const data = await fetchJSON<DtwSeriesMetrics>(
          `/api/dtw/sessions/${encodeURIComponent(testKey)}/${encodeURIComponent(sessionId)}/series?max_points=200`,
          ctrl.signal
        );
        setMetrics(data);
      } catch (e: any) {
        setMetrics(null);
        setMetricsErr(e?.message || 'Failed to load DTW metrics');
      } finally {
        setMetricsLoading(false);
      }
    })();
    return () => ctrl.abort();
  }, [testKey, sessionId]);

  const onExport = async () => {
    if (!testKey || !sessionId) return;
    try {
      const payload = await fetchJSON<{ npz: string; meta: string }>(
        `/api/dtw/sessions/${encodeURIComponent(testKey)}/${encodeURIComponent(sessionId)}/download`
      );
      const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `dtw_${testKey}_${sessionId}.json`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      console.error(e);
    }
  };

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <div className="border-b bg-card shadow-card">
        <div className="container mx-auto px-6 py-6 flex justify-between items-center">
          <div className="flex items-center space-x-4">
            <Link to={`/patient/${id}`}>
              <Button variant="outline" size="sm">
                <ArrowLeft className="mr-2 h-4 w-4" />
                Back to Patient
              </Button>
            </Link>
            <div>
              <h1 className="text-3xl font-bold text-foreground">Video Processing Summary</h1>
              <p className="text-muted-foreground mt-1">DTW analysis and results</p>
            </div>
          </div>
          <div className="flex space-x-3">
            <Button variant="outline" disabled={!testKey || !sessionId} onClick={onExport}>
              <Download className="mr-2 h-4 w-4" />
              Export DTW Paths
            </Button>
            <Link to={`/patient/${id}/test-selection`}>
              <Button className="bg-gradient-primary hover:bg-primary-hover">New Test Session</Button>
            </Link>
          </div>
        </div>
      </div>

      {/* ===== Content: top grid then full-width chart ===== */}
      <div className="container mx-auto px-6 py-10 grid grid-cols-12 gap-10">
        {/* Left: Video (spans 8/12) */}
        <div className="col-span-12 xl:col-span-7">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center justify-between">
                Recorded Video
                <Badge variant="secondary" className="bg-success text-success-foreground">Processed</Badge>
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {selectedVideo ? (
                <>
                  <video controls className="w-full rounded-lg aspect-video">
                    <source
                      src={`/api/recordings/${selectedVideo}`}
                      type={
                        selectedVideo.endsWith('.webm')
                          ? 'video/webm'
                          : selectedVideo.endsWith('.mp4')
                          ? 'video/mp4'
                          : 'video/quicktime'
                      }
                    />
                    Your browser does not support the video tag.
                  </video>
                  <div className="text-xs text-muted-foreground mt-2">
                    Files are stored on the server under <code>backend/recordings</code>.
                  </div>
                </>
              ) : (
                <div className="bg-gray-900 text-white text-center py-10 rounded-lg">
                  No video available. Recordings are saved under <code>backend/recordings</code> with the patient and test name.
                </div>
              )}
              {videoList.length > 1 && (
                <div className="flex items-center gap-2">
                  <span className="block text-sm font-medium text-foreground">Select recording</span>
                  <select
                    value={selectedVideo || ''}
                    onChange={(e) => setSelectedVideo(e.target.value)}
                    className="border p-2 rounded-md text-sm"
                  >
                    {videoList.map((video, idx) => (
                      <option key={idx} value={video}>{video}</option>
                    ))}
                  </select>
                </div>
              )}
              <div className="flex justify-between text-sm text-muted-foreground">
                <span>Duration: {currentTest?.results?.duration || 0}s</span>
                <span>Resolution: 1920×1080</span>
                <span>Keypoints: Detected</span>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Right: History + Stats (spans 5/12) */}
        <div className="col-span-12 xl:col-span-5 space-y-10">
          <Card>
            <CardHeader>
              <CardTitle className="flex justify-between">
                <span className="flex items-center">
                  <Calendar className="mr-2 h-5 w-5" />
                  Test History
                </span>
                <Select value={selectedHistoryFilter} onValueChange={setSelectedHistoryFilter}>
                  <SelectTrigger className="w-40"><SelectValue placeholder="Filter" /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Tests</SelectItem>
                    <SelectItem value="stand-and-sit">Stand & Sit</SelectItem>
                    <SelectItem value="palm-open">Palm Open</SelectItem>
                  </SelectContent>
                </Select>
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {filteredHistory.map((test) => (
                <div key={test.id} className="border p-3 rounded-lg">
                  <div className="flex justify-between items-center">
                    <div>
                      <p className="font-medium text-sm">{test.name}</p>
                      <p className="text-xs text-muted-foreground">{test.date.toDateString()}</p>
                    </div>
                    <Badge variant="secondary" className="bg-success text-success-foreground">
                      Score: {test.results?.score}
                    </Badge>
                  </div>
                  <p className="text-xs text-muted-foreground mt-1">{test.results?.analysis}</p>
                </div>
              ))}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center">
                <BarChart3 className="mr-2 h-5 w-5" />
                Performance Statistics
              </CardTitle>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Metric</TableHead>
                    <TableHead>Value</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  <TableRow>
                    <TableCell>Overall Score</TableCell>
                    <TableCell>{currentTest?.results?.score}</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>Average Duration</TableCell>
                    <TableCell>{mockStats.averageDuration}</TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell>Tremor</TableCell>
                    <TableCell>{mockStats.tremor}</TableCell>
                  </TableRow>
                </TableBody>
              </Table>
              <div className="mt-4 p-3 bg-muted rounded-lg">
                <FileText className="inline mr-2 text-primary" />
                <span className="text-sm">{currentTest?.results?.analysis}</span>
              </div>
            </CardContent>
          </Card>
        </div>

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
                  <Select value={testKey ?? ''} onValueChange={(v) => setTestKey(v as CanonicalTest)}>
                    <SelectTrigger className="w-44">
                      <SelectValue placeholder="Select test" />
                    </SelectTrigger>
                    <SelectContent>
                      {canonicalTests.map((t) => (
                        <SelectItem key={t} value={t}>{t}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  {/* Session picker */}
                  <Select value={sessionId ?? ''} onValueChange={(v) => setSessionId(v)}>
                    <SelectTrigger className="w-64">
                      <SelectValue placeholder="Select session" />
                    </SelectTrigger>
                    <SelectContent>
                      {sessions.map((s) => (
                        <SelectItem key={s.session_id} value={s.session_id}>
                          {s.created_utc} • sim {s.similarity?.toFixed(2) ?? '-'}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  {/* Axis */}
                  <Select value={axis} onValueChange={(v) => setAxis(v as 'x'|'y')}>
                    <SelectTrigger className="w-28">
                      <SelectValue placeholder="Axis" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="x">X axis</SelectItem>
                      <SelectItem value="y">Y axis</SelectItem>
                    </SelectContent>
                  </Select>
                  {/* Downsample */}
                  <Select value={String(maxPoints)} onValueChange={(v) => setMaxPoints(Number(v))}>
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
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <div className="p-3 rounded-md bg-muted">
                  <div className="text-xs text-muted-foreground">Similarity</div>
                  <div className="mt-1 text-2xl font-semibold">
                    {metricsLoading ? '…' : (metrics?.similarity ?? sessions.find(s => s.session_id === sessionId)?.similarity ?? 0).toFixed(3)}
                  </div>
                </div>
                <div className="p-3 rounded-md bg-muted">
                  <div className="text-xs text-muted-foreground">Total DTW Distance</div>
                  <div className="mt-1 text-2xl font-semibold">
                    {metricsLoading ? '…' : (metrics?.distance ?? 0).toFixed(3)}
                  </div>
                </div>
                <div className="p-3 rounded-md bg-muted">
                  <div className="text-xs text-muted-foreground">Avg. Step Cost</div>
                  <div className="mt-1 text-2xl font-semibold">
                    {metricsLoading ? '…' : (metrics?.avg_step_cost ?? 0).toFixed(3)}
                  </div>
                </div>
              </div>
              {metricsErr && <div className="text-sm text-red-600">{metricsErr}</div>}

              <Explainer title="How to read this section">
                Top-left shows the original aggregated motion on the selected axis. Top-right shows the DTW staircase
                mapping (live → reference). The large bottom chart shows both signals after DTW alignment; the shaded band
                and vertical connectors visualize point-to-point differences. Similarity is a monotonic transform of the
                mean per-step cost (higher ≈ better); distance is the total DTW cost along the path.
              </Explainer>

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
