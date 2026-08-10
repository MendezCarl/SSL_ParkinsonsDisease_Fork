import { Link } from 'react-router-dom';
import { AlertTriangle, ArrowLeft, BarChart3, Brain, Calendar, CheckCircle2, Download, Pencil, ShieldAlert } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Textarea } from '@/components/ui/textarea';
import type { PersistedAnomalyPrediction, Test } from '@/types/patient';
import type { DtwSeriesMetrics, DtwSessionMeta, MlPrediction } from '@/services/dtw';

type HistoryFilter = 'all' | Test['type'];

const getVideoMimeType = (filename: string | null): string => {
  if (!filename) return 'video/mp4';
  const lower = filename.toLowerCase();
  if (lower.endsWith('.mov')) return 'video/quicktime';
  if (lower.endsWith('.webm')) return 'video/webm';
  if (lower.endsWith('.mp4')) return 'video/mp4';
  return 'video/mp4';
};

export function VideoSummaryHeader({
  patientId,
  canExport,
  onExport,
}: {
  patientId?: string;
  canExport: boolean;
  onExport: () => void;
}) {
  return (
    <div className="border-b bg-card shadow-card">
      <div className="container mx-auto px-6 py-6 flex justify-between items-center">
        <div className="flex items-center space-x-4">
          <Link to={`/patients/${patientId}`}>
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
          <Button variant="outline" disabled={!canExport} onClick={onExport}>
            <Download className="mr-2 h-4 w-4" />
            Export DTW Paths
          </Button>
          <Link to={`/patients/${patientId}/test-selection`}>
            <Button className="bg-gradient-primary hover:bg-primary-hover">New Test Session</Button>
          </Link>
        </div>
      </div>
    </div>
  );
}

export function RecordedVideoCard({
  normalizedVideoName,
  videoSrc,
  videoList,
  selectedVideo,
  onSelectVideo,
  duration,
}: {
  normalizedVideoName: string | null;
  videoSrc: string | null;
  videoList: string[];
  selectedVideo: string | null;
  onSelectVideo: (value: string) => void;
  duration: string;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center justify-between">
          Recorded Video
          <Badge variant="secondary" className="bg-success text-success-foreground">
            Processed
          </Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {normalizedVideoName && videoSrc ? (
          <>
            <video key={normalizedVideoName} controls className="w-full rounded-lg aspect-video">
              <source src={videoSrc} type={getVideoMimeType(normalizedVideoName)} />
              Your browser does not support the video tag.
            </video>
            <div className="text-xs text-muted-foreground mt-2">
              Playing from: <code>{videoSrc}</code>
            </div>
          </>
        ) : (
          <div className="bg-gray-900 text-white text-center py-10 rounded-lg">
            No video available. Recordings are saved under <code>backend/data/recordings</code>.
          </div>
        )}
        {videoList.length > 1 && (
          <div className="flex items-center gap-2">
            <span className="block text-sm font-medium text-foreground">Select recording</span>
            <select
              value={selectedVideo || ''}
              onChange={(e) => onSelectVideo(e.target.value)}
              className="border p-2 rounded-md text-sm"
            >
              {videoList.map((video, idx) => (
                <option key={idx} value={video}>
                  {video}
                </option>
              ))}
            </select>
          </div>
        )}
        <div className="flex justify-between text-sm text-muted-foreground">
          <span>Duration: {duration}</span>
          <span>Resolution: 1920×1080</span>
          <span>Keypoints: Detected</span>
        </div>
      </CardContent>
    </Card>
  );
}

export function TestHistoryCard({
  selectedHistoryFilter,
  onFilterChange,
  historyLoading,
  filteredHistory,
  formatHistorySummary,
  hasUnknownHistory,
}: {
  selectedHistoryFilter: HistoryFilter;
  onFilterChange: (value: HistoryFilter) => void;
  historyLoading: boolean;
  filteredHistory: Test[];
  formatHistorySummary: (test: Test) => string;
  hasUnknownHistory: boolean;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex justify-between">
          <span className="flex items-center">
            <Calendar className="mr-2 h-5 w-5" />
            Test History
          </span>
          <Select value={selectedHistoryFilter} onValueChange={(value) => onFilterChange(value as HistoryFilter)}>
            <SelectTrigger className="w-40">
              <SelectValue placeholder="Filter" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Tests</SelectItem>
              <SelectItem value="stand-and-sit">Stand & Sit</SelectItem>
              <SelectItem value="finger-tapping">Finger Tapping</SelectItem>
              <SelectItem value="fist-open-close">Fist Open & Close</SelectItem>
              {hasUnknownHistory && <SelectItem value="unknown">Unsupported</SelectItem>}
            </SelectContent>
          </Select>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {historyLoading ? (
          <p className="text-sm text-muted-foreground">Loading test history…</p>
        ) : filteredHistory.length === 0 ? (
          <p className="text-sm text-muted-foreground">No backend test history available for this filter.</p>
        ) : (
          filteredHistory.map((test) => (
            <div key={test.id} className="border p-3 rounded-lg">
              <div className="flex justify-between items-center gap-3">
                <div>
                  <p className="font-medium text-sm">{test.name}</p>
                  <p className="text-xs text-muted-foreground">{test.date.toDateString()}</p>
                </div>
                <Badge variant="secondary">{test.status}</Badge>
              </div>
              <p className="text-xs text-muted-foreground mt-1">{formatHistorySummary(test)}</p>
            </div>
          ))
        )}
      </CardContent>
    </Card>
  );
}

export function PerformanceStatisticsCard({
  metricsLoading,
  metricsErr,
  metrics,
  sessions,
  sessionId,
}: {
  metricsLoading: boolean;
  metricsErr: string | null;
  metrics: DtwSeriesMetrics | null;
  sessions: DtwSessionMeta[];
  sessionId: string | null;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center">
          <BarChart3 className="mr-2 h-5 w-5" />
          Performance Statistics
        </CardTitle>
      </CardHeader>
      <CardContent>
        {metricsLoading ? (
          <p className="text-sm text-muted-foreground">Loading metrics…</p>
        ) : metricsErr ? (
          <p className="text-sm text-red-600">{metricsErr}</p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Metric</TableHead>
                <TableHead>Value</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              <TableRow>
                <TableCell>Overall Similarity</TableCell>
                <TableCell>{metrics?.similarity_overall != null ? `${(metrics.similarity_overall * 100).toFixed(1)}%` : '—'}</TableCell>
              </TableRow>
              <TableRow>
                <TableCell>Position Similarity</TableCell>
                <TableCell>{metrics?.similarity_pos != null ? `${(metrics.similarity_pos * 100).toFixed(1)}%` : '—'}</TableCell>
              </TableRow>
              <TableRow>
                <TableCell>Amplitude Similarity</TableCell>
                <TableCell>{metrics?.similarity_amp != null ? `${(metrics.similarity_amp * 100).toFixed(1)}%` : '—'}</TableCell>
              </TableRow>
              <TableRow>
                <TableCell>Speed Similarity</TableCell>
                <TableCell>{metrics?.similarity_spd != null ? `${(metrics.similarity_spd * 100).toFixed(1)}%` : '—'}</TableCell>
              </TableRow>
              <TableRow>
                <TableCell>Positional DTW Distance</TableCell>
                <TableCell>{metrics?.distance_pos != null ? metrics.distance_pos.toFixed(3) : '—'}</TableCell>
              </TableRow>
              <TableRow>
                <TableCell>Avg. Step Cost</TableCell>
                <TableCell>{metrics?.avg_step_pos != null ? metrics.avg_step_pos.toFixed(4) : '—'}</TableCell>
              </TableRow>
              <TableRow>
                <TableCell>Live Frames</TableCell>
                <TableCell>{sessions.find((s) => s.session_id === sessionId)?.live_len ?? '—'}</TableCell>
              </TableRow>
              <TableRow>
                <TableCell>Reference Frames</TableCell>
                <TableCell>{sessions.find((s) => s.session_id === sessionId)?.ref_len ?? '—'}</TableCell>
              </TableRow>
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}

export function MlPredictionCard({
  mlLoading,
  mlErr,
  mlPrediction,
  canConfirm,
  labelResult,
  onOpenLabelDialog,
}: {
  mlLoading: boolean;
  mlErr: string | null;
  mlPrediction: MlPrediction | null;
  canConfirm: boolean;
  labelResult: { stage: number; source: string } | null;
  onOpenLabelDialog: () => void;
}) {
  return (
    <Card className="border-2 border-amber-200 dark:border-amber-800">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Brain className="h-5 w-5 text-amber-600 dark:text-amber-400" />
          AI-Predicted UPDRS Motor Stage
        </CardTitle>
        <div className="flex items-start gap-2 rounded-md border border-amber-300 bg-amber-50 p-3 text-sm dark:border-amber-700 dark:bg-amber-950">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-600 dark:text-amber-400" />
          <span className="text-amber-800 dark:text-amber-300">
            <strong>This is an AI model estimate and may be incorrect.</strong> It was trained on a limited dataset and reliably predicts only UPDRS stages&nbsp;1–3. Stage&nbsp;0 predictions are experimental. Do not use this result as a clinical diagnosis. Always consult a qualified clinician.
          </span>
        </div>
      </CardHeader>
      <CardContent>
        {mlLoading ? (
          <p className="text-sm text-muted-foreground">Running model…</p>
        ) : mlErr ? (
          <p className="text-sm text-red-600">{mlErr}</p>
        ) : !mlPrediction ? (
          <p className="text-sm text-muted-foreground">Select a test and session above to run the prediction.</p>
        ) : (
          <div className="space-y-5">
            <div className="flex flex-col items-center gap-1 rounded-lg bg-muted py-6">
              <p className="text-xs font-medium uppercase tracking-widest text-muted-foreground">Predicted Stage</p>
              <p className="text-5xl font-bold text-amber-700 dark:text-amber-400">Stage {mlPrediction.predicted_updrs_stage}</p>
              <p className="text-sm text-muted-foreground">
                Confidence: <span className="font-medium">{(mlPrediction.confidence * 100).toFixed(1)}%</span>
              </p>
            </div>
            <div>
              <p className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">Class Probabilities</p>
              <div className="space-y-2">
                {Object.entries(mlPrediction.probabilities)
                  .sort(([a], [b]) => Number(a) - Number(b))
                  .map(([stage, prob]) => {
                    const pct = (prob * 100).toFixed(1);
                    const isTop = Number(stage) === mlPrediction.predicted_updrs_stage;
                    return (
                      <div key={stage} className="flex items-center gap-3">
                        <span className="w-16 shrink-0 text-xs text-muted-foreground">Stage {stage}</span>
                        <div className="flex-1 overflow-hidden rounded-full bg-muted">
                          <div
                            className={`h-2 rounded-full transition-all ${isTop ? 'bg-amber-500' : 'bg-slate-400 dark:bg-slate-600'}`}
                            style={{ width: `${pct}%` }}
                          />
                        </div>
                        <span className={`w-12 text-right text-xs tabular-nums ${isTop ? 'font-semibold text-amber-700 dark:text-amber-400' : 'text-muted-foreground'}`}>
                          {pct}%
                        </span>
                      </div>
                    );
                  })}
              </div>
            </div>
            {canConfirm && (
              <div className="flex items-center justify-end pt-2">
                {labelResult ? (
                  <div className="flex items-center gap-2 rounded-md border border-green-300 bg-green-50 px-4 py-2 text-sm text-green-800 dark:border-green-700 dark:bg-green-950 dark:text-green-300">
                    <CheckCircle2 className="h-4 w-4" />
                    Stage {labelResult.stage} confirmed
                    {labelResult.source === 'doctor_correction' ? ' (corrected)' : ''} and saved for training.
                  </div>
                ) : (
                  <Button
                    variant="outline"
                    className="gap-2 border-amber-400 text-amber-700 hover:bg-amber-50 dark:border-amber-600 dark:text-amber-400"
                    onClick={onOpenLabelDialog}
                  >
                    <Pencil className="h-4 w-4" />
                    Confirm / Adjust Stage
                  </Button>
                )}
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

const formatModelValue = (value?: string | null): string => value || '—';

const formatPredictionTimestamp = (value?: string | null): string => {
  if (!value) return '—';
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
};

export function WholeVideoAnomalyCard({
  anomalyPrediction,
}: {
  anomalyPrediction?: PersistedAnomalyPrediction | null;
}) {
  const probability = anomalyPrediction?.anomaly_probability;
  const score = anomalyPrediction?.anomaly_score;
  const timestamp = anomalyPrediction?.created_at ?? anomalyPrediction?.generated_at ?? null;
  const anomalyModel = anomalyPrediction?.anomaly_model ?? anomalyPrediction?.classifier_model ?? null;
  const isPersisted = anomalyPrediction?.persisted !== false;

  return (
    <Card className="border-2 border-sky-200 dark:border-sky-800">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <ShieldAlert className="h-5 w-5 text-sky-600 dark:text-sky-400" />
          Whole-Video Anomaly
        </CardTitle>
      </CardHeader>
      <CardContent>
        {!anomalyPrediction ? (
          <p className="text-sm text-muted-foreground">No persisted whole-video anomaly prediction is available for this test.</p>
        ) : (
          <div className="space-y-4">
            <div className="flex flex-col items-center gap-2 rounded-lg bg-muted py-6">
              <p className="text-xs font-medium uppercase tracking-widest text-muted-foreground">Prediction</p>
              <p className="text-4xl font-bold capitalize text-sky-700 dark:text-sky-400">{anomalyPrediction.predicted_label}</p>
              <Badge variant={isPersisted ? 'secondary' : 'outline'}>
                {isPersisted ? 'Persisted' : 'Not Persisted'}
              </Badge>
            </div>
            <Table>
              <TableBody>
                <TableRow>
                  <TableCell>Probability</TableCell>
                  <TableCell>{probability != null ? `${(probability * 100).toFixed(1)}%` : '—'}</TableCell>
                </TableRow>
                <TableRow>
                  <TableCell>Score</TableCell>
                  <TableCell>{score != null ? score.toFixed(4) : '—'}</TableCell>
                </TableRow>
                <TableRow>
                  <TableCell>Video Model</TableCell>
                  <TableCell>{formatModelValue(anomalyPrediction.video_model)}</TableCell>
                </TableRow>
                <TableRow>
                  <TableCell>Anomaly Model</TableCell>
                  <TableCell>{formatModelValue(anomalyModel)}</TableCell>
                </TableRow>
                <TableRow>
                  <TableCell>Timestamp</TableCell>
                  <TableCell>{formatPredictionTimestamp(timestamp)}</TableCell>
                </TableRow>
              </TableBody>
            </Table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export function DoctorLabelDialog({
  open,
  onOpenChange,
  mlPrediction,
  labelStage,
  onLabelStageChange,
  labelNotes,
  onLabelNotesChange,
  labelSubmitting,
  onConfirm,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  mlPrediction: MlPrediction | null;
  labelStage: number;
  onLabelStageChange: (value: number) => void;
  labelNotes: string;
  onLabelNotesChange: (value: string) => void;
  labelSubmitting: boolean;
  onConfirm: () => void;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Brain className="h-5 w-5 text-amber-600" />
            Confirm or Adjust AI-Predicted Stage
          </DialogTitle>
          <DialogDescription className="text-sm text-muted-foreground">
            Review the model's suggestion and select the clinically correct UPDRS stage. Your selection will update the patient record and be saved as labelled training data to improve the model over time.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-2">
          {mlPrediction && (
            <div className="rounded-md border bg-muted/50 px-4 py-2 text-sm">
              <span className="text-muted-foreground">AI suggested: </span>
              <span className="font-semibold">{mlPrediction.severity}</span>
              <span className="text-muted-foreground ml-2">({(mlPrediction.confidence * 100).toFixed(1)}% confidence)</span>
            </div>
          )}

          <div className="space-y-1.5">
            <Label htmlFor="stage-select">Confirmed UPDRS Stage</Label>
            <Select value={String(labelStage)} onValueChange={(v) => onLabelStageChange(Number(v))}>
              <SelectTrigger id="stage-select">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {[1, 2, 3, 4, 5].map((s) => (
                  <SelectItem key={s} value={String(s)}>
                    Stage {s}
                    {mlPrediction && s === mlPrediction.predicted_updrs_stage + 1 ? ' (AI suggested)' : ''}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="label-notes">
              Clinical notes <span className="font-normal text-muted-foreground">(optional)</span>
            </Label>
            <Textarea
              id="label-notes"
              placeholder="e.g. Patient showed mild tremor, AI over-estimated severity…"
              rows={3}
              value={labelNotes}
              onChange={(e) => onLabelNotesChange(e.target.value)}
            />
          </div>

          <p className="text-xs text-muted-foreground">
            This action will update the patient's severity record and archive this session as labelled training data.
          </p>
        </div>

        <DialogFooter className="gap-2">
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={labelSubmitting}>
            Cancel
          </Button>
          <Button disabled={labelSubmitting} onClick={onConfirm}>
            {labelSubmitting ? 'Saving…' : 'Confirm Stage'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
