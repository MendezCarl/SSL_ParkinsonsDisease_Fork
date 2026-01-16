import { useState, useEffect, useRef } from "react";
import { useParams, useNavigate, Link, useLocation } from "react-router-dom";
import {
  ArrowLeft,
  Play,
  Pause,
  Square,
  RotateCcw,
  CheckCircle,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { useToast } from "@/hooks/use-toast";
import { AVAILABLE_TESTS } from "@/types/patient";

type MPHandPoint = { x: number; y: number; z?: number };
type MPPosePoint = { x: number; y: number; z?: number; v?: number };

// --- WebSocket URL builder
const WS_PATH = "/ws/camera";
const wsURL = () => new URL(WS_PATH, window.location.origin).toString();

const modelForTest = (testId?: string) => {
  switch (testId) {
    case "stand-and-sit":
      return "pose";
    case "finger-tapping":
    case "fist-open-close":
    case "palm-open":
    default:
      return "hands";
  }
};

const MIN_RECORDING_TIME = 12; // seconds

const VideoRecording = () => {
  const { id, testId } = useParams<{ id: string; testId: string }>();
  const navigate = useNavigate();
  const location = useLocation();
  const { toast } = useToast();

  const selectedTests = location.state?.selectedTests || [];
  const [currentTestIndex, setCurrentTestIndex] = useState(0);
  const [isRecording, setIsRecording] = useState(false);
  const [isPaused, setIsPaused] = useState(false);
  const [recordingTime, setRecordingTime] = useState(0);
  const [completedTests, setCompletedTests] = useState<string[]>([]);
  const [wsConnected, setWsConnected] = useState(false);

  const totalTests = selectedTests.length;
  const currentTestId = selectedTests[currentTestIndex];
  const currentTest = AVAILABLE_TESTS.find((test) => test.id === currentTestId);
  const isCurrentTestCompleted = currentTestId
    ? completedTests.includes(currentTestId)
    : false;
  const progress = totalTests === 0
    ? 0
    : ((currentTestIndex + (isCurrentTestCompleted ? 1 : 0)) / totalTests) * 100;

  // Media refs
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const overlayRef = useRef<HTMLCanvasElement | null>(null); // keypoint overlay
  const snapRef = useRef<HTMLCanvasElement | null>(null); // offscreen snapshot for WS

  // Recording refs
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const recordedChunks = useRef<Blob[]>([]);
  const recordingRef = useRef(false);

  const ensureCameraStream = async (): Promise<boolean> => {
    if (mediaStreamRef.current && mediaStreamRef.current.active) {
      if (videoRef.current && videoRef.current.srcObject !== mediaStreamRef.current) {
        videoRef.current.srcObject = mediaStreamRef.current;
        await videoRef.current.play().catch(() => {});
      }
      return true;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "user" },
        audio: false,
      });
      mediaStreamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play().catch(() => {});
      }
      return true;
    } catch {
      toast({
        title: "Camera Access Denied",
        description: "Allow camera access to record the test.",
        variant: "destructive",
      });
      return false;
    }
  };

  const releaseCameraStream = () => {
    const stream = mediaStreamRef.current;
    if (stream) {
      stream.getTracks().forEach((track) => track.stop());
      mediaStreamRef.current = null;
    }
    if (videoRef.current) {
      videoRef.current.srcObject = null;
    }
    const overlay = overlayRef.current;
    if (overlay) {
      const ctx = overlay.getContext("2d");
      if (ctx) ctx.clearRect(0, 0, overlay.width, overlay.height);
    }
  };

  useEffect(() => {
    recordingRef.current = isRecording;
  }, [isRecording]);

  // WS refs
  const wsRef = useRef<WebSocket | null>(null);
  const rafRef = useRef<number | null>(null);
  const lastSentRef = useRef<number>(0);
  const sendFps = 15; // throttle frame sends

  // ---- Regular COMPUTER CAMERA init ----
  useEffect(() => {
    if (selectedTests.length === 0) {
      return undefined;
    }

    let isMounted = true;
    (async () => {
      if (isMounted) {
        await ensureCameraStream();
      }
    })();

    return () => {
      isMounted = false;
      stopFrameLoop();

      if (wsRef.current) {
        wsEndAndClose(recordingRef.current);
      }

      if (mediaRecorderRef.current) {
        const recorder = mediaRecorderRef.current;
        mediaRecorderRef.current = null;
        recorder.ondataavailable = null;
        recorder.onstop = null;
        try {
          if (recorder.state !== "inactive") {
            recorder.stop();
          }
        } catch {
          /* ignore */
        }
      }

      recordedChunks.current = [];
      releaseCameraStream();

      const overlay = overlayRef.current;
      if (overlay) {
        const ctx = overlay.getContext("2d");
        if (ctx) ctx.clearRect(0, 0, overlay.width, overlay.height);
      }

      if (rafRef.current) {
        cancelAnimationFrame(rafRef.current);
        rafRef.current = null;
      }
    };
  }, [selectedTests.length]);

  // ---- Recording timer ----
  useEffect(() => {
    let interval: NodeJS.Timeout | undefined;
    if (isRecording && !isPaused) {
      interval = setInterval(() => setRecordingTime((prev) => prev + 1), 1000);
    }
    return () => interval && clearInterval(interval);
  }, [isRecording, isPaused]);

  // ---- WS helpers ----
  const wsInit = () => {
    if (wsRef.current?.readyState === 1) return;
    const url = wsURL();
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      setWsConnected(true);
      ws.send(
        JSON.stringify({
          type: "init",
          patientId: id,
          testType: currentTest?.id,
          testId: testId,
          model: modelForTest(currentTest?.id),
          fps: sendFps,
        })
      );
      startFrameLoop();
    };

    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data);
        if (msg.type === "keypoints") drawKeypoints(msg);
      } catch {
        /* ignore */
      }
    };

    ws.onclose = () => {
      setWsConnected(false);
      stopFrameLoop();
      wsRef.current = null;
    };
    ws.onerror = () => {
      setWsConnected(false);
      stopFrameLoop();
      wsRef.current = null;
    };
  };

  const wsPause = (paused: boolean) => {
    if (wsRef.current?.readyState === 1) {
      wsRef.current.send(JSON.stringify({ type: "pause", paused }));
    }
  };

  const wsEndAndClose = (sendEnd: boolean = true) => {
    const ws = wsRef.current;
    if (!ws) return;

    if (sendEnd && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "end" }));
    }

    ws.onopen = null;
    ws.onmessage = null;
    ws.onclose = null;
    ws.onerror = null;
    wsRef.current = null;
    setWsConnected(false);

    const delay = sendEnd ? 150 : 0;
    setTimeout(() => {
      try {
        ws.close();
      } catch {
        /* ignore */
      }
    }, delay);
  };

  // ---- Frame push loop ----
  const startFrameLoop = () => {
    stopFrameLoop();
    const tick = (t: number) => {
      rafRef.current = requestAnimationFrame(tick);

      if (!videoRef.current || !wsRef.current || wsRef.current.readyState !== 1)
        return;
      if (isPaused || !recordingRef.current) return;

      if (t - lastSentRef.current < 1000 / sendFps) return;
      lastSentRef.current = t;

      const v = videoRef.current;
      const snap =
        snapRef.current || (snapRef.current = document.createElement("canvas"));
      const sctx = snap.getContext("2d");
      if (!sctx) return;

      if (snap.width !== v.videoWidth || snap.height !== v.videoHeight) {
        snap.width = v.videoWidth || 640;
        snap.height = v.videoHeight || 480;
      }
      sctx.drawImage(v, 0, 0, snap.width, snap.height);
      const dataUrl = snap.toDataURL("image/jpeg", 0.6);
      wsRef.current.send(JSON.stringify({ type: "frame", data: dataUrl }));
    };
    rafRef.current = requestAnimationFrame(tick);
  };
  const stopFrameLoop = () => {
    if (rafRef.current) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
  };

  // ---- Draw keypoints on overlay (crisp with DPR) ----
  const drawKeypoints = (msg: any) => {
    const overlay = overlayRef.current;
    const video = videoRef.current;
    if (!overlay || !video) return;

    const rect = video.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    overlay.width = Math.floor(rect.width * dpr);
    overlay.height = Math.floor(rect.height * dpr);
    overlay.style.width = `${Math.floor(rect.width)}px`;
    overlay.style.height = `${Math.floor(rect.height)}px`;

    const ctx = overlay.getContext("2d");
    if (!ctx) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, overlay.width, overlay.height);

    const dot = (x: number, y: number) => {
      ctx.beginPath();
      ctx.arc(x, y, 3, 0, Math.PI * 2);
      ctx.fill();
    };
    const line = (x1: number, y1: number, x2: number, y2: number) => {
      ctx.beginPath();
      ctx.moveTo(x1, y1);
      ctx.lineTo(x2, y2);
      ctx.stroke();
    };
    const toPx = (p: { x: number; y: number }) => ({
      x: p.x * (overlay.width / dpr),
      y: p.y * (overlay.height / dpr),
    });

    if (msg.model === "hands" && Array.isArray(msg.hands)) {
      const chains = [
        [0, 1, 2, 3, 4],
        [0, 5, 6, 7, 8],
        [0, 9, 10, 11, 12],
        [0, 13, 14, 15, 16],
        [0, 17, 18, 19, 20],
      ];
      for (const hand of msg.hands as { landmarks: MPHandPoint[] }[]) {
        const pts = hand.landmarks;
        ctx.lineWidth = 2;
        for (const ch of chains) {
          for (let i = 0; i < ch.length - 1; i++) {
            const a = toPx(pts[ch[i]]),
              b = toPx(pts[ch[i + 1]]);
            line(a.x, a.y, b.x, b.y);
          }
        }
        for (const p of pts) {
          const { x, y } = toPx(p);
          dot(x, y);
        }
      }
    }

    if (msg.model === "pose" && Array.isArray(msg.pose)) {
      const pts = msg.pose as MPPosePoint[];
      for (const p of pts) {
        if (p.v !== undefined && p.v < 0.5) continue;
        const { x, y } = toPx(p);
        dot(x, y);
      }
      const pairs = [
        [11, 12],
        [11, 13],
        [13, 15],
        [12, 14],
        [14, 16],
        [11, 23],
        [12, 24],
        [23, 24],
        [23, 25],
        [24, 26],
        [25, 27],
        [26, 28],
      ];
      ctx.lineWidth = 2;
      for (const [i, j] of pairs) {
        const a = pts[i],
          b = pts[j];
        if (!a || !b) continue;
        if (
          (a.v !== undefined && a.v < 0.5) ||
          (b.v !== undefined && b.v < 0.5)
        )
          continue;
        const ap = toPx(a),
          bp = toPx(b);
        line(ap.x, ap.y, bp.x, bp.y);
      }
    }
  };

  // ---- Recording handlers ----
  const handleStartRecording = async () => {
    if (isRecording) return;

    if (!currentTestId) {
      toast({
        title: "No Test Selected",
        description: "Please choose a test before recording.",
        variant: "destructive",
      });
      return;
    }

    if (isCurrentTestCompleted) {
      setCompletedTests((prev) => prev.filter((id) => id !== currentTestId));
    }

    const streamReady = await ensureCameraStream();
    if (!streamReady || !videoRef.current || !videoRef.current.srcObject) {
      return;
    }

    if (wsRef.current) {
      wsEndAndClose(false);
    }

    setIsRecording(true);
    setIsPaused(false);
    setRecordingTime(0);
    recordingRef.current = true;

    recordedChunks.current = [];
    const stream = videoRef.current.srcObject as MediaStream;
    const mediaRecorder = new MediaRecorder(stream, {
      mimeType: "video/webm",
    });
    mediaRecorder.ondataavailable = (event) => {
      if (event.data.size > 0) recordedChunks.current.push(event.data);
    };
    mediaRecorderRef.current = mediaRecorder;
    mediaRecorder.start();

    wsInit();
  };

  const handlePauseRecording = () => {
    if (!mediaRecorderRef.current) return;
    if (isPaused) {
      mediaRecorderRef.current.resume();
      wsPause(false);
    } else {
      mediaRecorderRef.current.pause();
      wsPause(true);
    }
    setIsPaused(!isPaused);
  };

  const handleStopRecording = async () => {
    // Enforce minimum time (double-safety; Stop button is also disabled until met)
    if (recordingTime < MIN_RECORDING_TIME) {
      const remaining = MIN_RECORDING_TIME - recordingTime;
      toast({
        title: "Recording Too Short",
        description: `Please record at least ${MIN_RECORDING_TIME} seconds. ${remaining}s remaining.`,
        variant: "destructive",
      });
      return;
    }

    if (!mediaRecorderRef.current) return;

    const activeTestId = currentTestId || currentTest?.id || "";

    wsEndAndClose();
    stopFrameLoop();

    return new Promise<void>((resolve) => {
      const recorder = mediaRecorderRef.current!;
      recorder.onstop = async () => {
        setIsRecording(false);
        setIsPaused(false);
        recordingRef.current = false;
        mediaRecorderRef.current = null;

        const chunks = [...recordedChunks.current];
        recordedChunks.current = [];
        const blob = new Blob(chunks, { type: "video/webm" });
        const formData = new FormData();
        formData.append("patient_id", id || "");
        formData.append("test_name", activeTestId || "unknown");
        formData.append("video", blob, "recording.webm");

        try {
          const resp = await fetch("/api/upload-video/", {
            method: "POST",
            body: formData,
          });
          if (resp.ok) {
            const data = await resp.json();
            const diskHint = data?.disk_path
              ? data.disk_path
              : data?.filename
              ? `backend/recordings/${data.filename}`
              : undefined;
            toast({
              title: "Recording Saved",
              description: diskHint ? `Saved to ${diskHint}` : `Saved as ${data.filename}`,
            });
            if (data?.filename) {
              console.info(
                `[VideoRecording] Saved video '${data.filename}' at '${diskHint || "(unknown path)"}'`
              );
            }
          } else throw new Error("Upload failed");
        } catch (err) {
          console.error("Upload error:", err);
          toast({
            title: "Upload Error",
            description: "Could not upload the video.",
            variant: "destructive",
          });
        }

        setCompletedTests((prev) => {
          if (!activeTestId || prev.includes(activeTestId)) {
            return prev;
          }
          return [...prev, activeTestId];
        });
        releaseCameraStream();
        resolve();
      };
      try {
        recorder.stop();
      } catch {
        resolve();
      }
    });
  };

  const handleNextTest = () => {
    if (isRecording) {
      toast({
        title: "Recording In Progress",
        description: "Stop or reset the current recording before moving to the next test.",
        variant: "destructive",
      });
      return;
    }

    setIsRecording(false);
    setIsPaused(false);
    recordingRef.current = false;
    stopFrameLoop();
    wsEndAndClose(false);
    recordedChunks.current = [];
    if (currentTestIndex < selectedTests.length - 1) {
      setCurrentTestIndex((prev) => prev + 1);
      setRecordingTime(0);
      const ctx = overlayRef.current?.getContext("2d");
      if (ctx && overlayRef.current)
        ctx.clearRect(
          0,
          0,
          overlayRef.current.width,
          overlayRef.current.height
        );
  void ensureCameraStream();
    } else {
      releaseCameraStream();
      navigate(`/patient/${id}/video-summary/${testId}`);
    }
  };

  const handleRetakeCurrentTest = () => {
    if (!currentTestId) {
      return;
    }
    if (isRecording) {
      toast({
        title: "Recording In Progress",
        description: "Stop or reset before starting a new take.",
        variant: "destructive",
      });
      return;
    }

    setCompletedTests((prev) => prev.filter((id) => id !== currentTestId));
    setRecordingTime(0);
    setIsPaused(false);
    recordingRef.current = false;
    const ctx = overlayRef.current?.getContext("2d");
    if (ctx && overlayRef.current) {
      ctx.clearRect(0, 0, overlayRef.current.width, overlayRef.current.height);
    }
    recordedChunks.current = [];
    void ensureCameraStream();
    toast({
      title: "Ready to Retake",
      description: "Start recording again when you are ready.",
    });
  };

  const handleReset = () => {
    if (mediaRecorderRef.current) {
      const recorder = mediaRecorderRef.current;
      mediaRecorderRef.current = null;
      recorder.ondataavailable = null;
      recorder.onstop = null;
      try {
        if (recorder.state !== "inactive") {
          recorder.stop();
        }
      } catch {
        /* ignore */
      }
    }

    recordedChunks.current = [];
    setIsRecording(false);
    setIsPaused(false);
    setRecordingTime(0);
    recordingRef.current = false;
    wsEndAndClose();
    stopFrameLoop();
    const ctx = overlayRef.current?.getContext("2d");
    if (ctx && overlayRef.current)
      ctx.clearRect(0, 0, overlayRef.current.width, overlayRef.current.height);
    releaseCameraStream();
  };

  const formatTime = (s: number) =>
    `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(
      2,
      "0"
    )}`;

  const getTestInstructions = (testType: string) => {
    switch (testType) {
      case "stand-and-sit":
        return [
          "Start in a seated position",
          "Stand up slowly when ready",
          "Hold standing for 3s",
          "Sit down slowly",
          "Repeat 3–5 times",
        ];
      case "palm-open":
        return [
          "Extend both arms forward",
          "Palms facing camera",
          "Open/close hands repeatedly",
          "Keep arms steady",
          "Continue for 30s",
        ];
      case "finger-tapping":
        return [
          "Hand in view",
          "Tap index & thumb quickly",
          "Continue for the duration",
        ];
      case "fist-open-close":
        return [
          "Hand in view",
          "Open hand wide → close fist",
          "Repeat for the duration",
        ];
      default:
        return ["Follow the on-screen instructions"];
    }
  };

  const minRemaining = Math.max(0, MIN_RECORDING_TIME - recordingTime);
  const minMet = minRemaining === 0;

  if (totalTests === 0 || !currentTestId || !currentTest) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center px-6">
        <Card className="max-w-lg w-full">
          <CardHeader>
            <CardTitle>No Tests Selected</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="text-sm text-muted-foreground">
              There are no tests queued for recording. Please return to the test selection page and choose at least one assessment to begin.
            </p>
            <Button asChild>
              <Link to={`/patient/${id}/test-selection`}>
                Back to Test Selection
              </Link>
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <div className="border-b bg-card shadow-card">
        <div className="container mx-auto px-6 py-6">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-4">
              <Link to={`/patient/${id}/test-selection`}>
                <Button variant="outline" size="sm">
                  <ArrowLeft className="mr-2 h-4 w-4" />
                  Back to Selection
                </Button>
              </Link>
              <div>
                <h1 className="text-3xl font-bold text-foreground">
                  Video Recording
                </h1>
                <p className="text-muted-foreground mt-1">
                  Test {currentTestIndex + 1} of {totalTests}:{" "}
                  {currentTest?.name}
                </p>
              </div>
            </div>
            <div className="text-right">
              <div className="flex items-center justify-end gap-2">
                <div className="text-2xl font-bold text-primary">
                  {formatTime(recordingTime)}
                </div>
                <Badge
                  variant="secondary"
                  className={
                    minMet
                      ? "bg-green-600 text-white"
                      : "bg-yellow-500 text-black"
                  }
                  title={
                    minMet
                      ? "Minimum met"
                      : `Minimum recording time required: ${MIN_RECORDING_TIME}s`
                  }
                >
                  {minMet
                    ? "Min met"
                    : `Min ${formatTime(MIN_RECORDING_TIME)} · ${minRemaining}s left`}
                </Badge>
              </div>
              <Progress value={progress} className="w-32 mt-2" />
            </div>
          </div>
        </div>
      </div>

      {/* Body */}
      <div className="container mx-auto px-6 py-8">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          {/* Test List + Instructions */}
          <div className="lg:order-2 space-y-6">
            <Card>
              <CardHeader>
                <CardTitle>Test Progress</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  {selectedTests.map((tid, index) => {
                    const test = AVAILABLE_TESTS.find((t) => t.id === tid);
                    const isCompleted = completedTests.includes(tid);
                    const isCurrent = index === currentTestIndex;
                    return (
                      <div
                        key={tid}
                        className={`p-3 rounded-lg border ${
                          isCurrent
                            ? "border-primary bg-medical-light"
                            : isCompleted
                            ? "border-success bg-success/10"
                            : "border-border"
                        }`}
                      >
                        <div className="flex items-center justify-between">
                          <div>
                            <p className="font-medium text-sm">{test?.name}</p>
                            <p className="text-xs text-muted-foreground">
                              Test {index + 1} of {totalTests}
                            </p>
                          </div>
                          {isCompleted && (
                            <CheckCircle className="h-5 w-5 text-success" />
                          )}
                          {isCurrent && !isCompleted && (
                            <Badge
                              variant="secondary"
                              className="bg-primary text-primary-foreground"
                            >
                              Current
                            </Badge>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Instructions</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  {currentTest &&
                    getTestInstructions(currentTest.id).map(
                      (instruction, i) => (
                        <div key={i} className="flex items-start space-x-2">
                          <span className="text-primary font-bold text-sm mt-0.5">
                            {i + 1}.
                          </span>
                          <span className="text-sm">{instruction}</span>
                        </div>
                      )
                    )}
                  <div className="mt-3 text-xs text-muted-foreground">
                    Note: A minimum recording length of{" "}
                    <span className="font-semibold">
                      {formatTime(MIN_RECORDING_TIME)}
                    </span>{" "}
                    is required before you can stop.
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Video + Controls */}
          <div className="lg:col-span-2 lg:order-1">
            <Card className="h-full">
              <CardHeader>
                <CardTitle className="flex items-center justify-between">
                  <span>Live Video Feed</span>
                  <div className="flex items-center gap-2">
                    <Badge
                      variant="secondary"
                      className={
                        wsConnected
                          ? "bg-green-600 text-white"
                          : "bg-muted text-muted-foreground"
                      }
                    >
                      WS: {wsConnected ? "connected" : "disconnected"}
                    </Badge>
                    <Badge
                      variant="secondary"
                      className={
                        isRecording
                          ? isPaused
                            ? "bg-yellow-500 text-black"
                            : "bg-red-600 text-white animate-pulse"
                          : "bg-muted text-muted-foreground"
                      }
                    >
                      {isRecording
                        ? isPaused
                          ? "PAUSED"
                          : "RECORDING"
                        : "STOPPED"}
                    </Badge>
                  </div>
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="relative bg-black rounded-lg aspect-video mb-6 overflow-hidden">
                  <video
                    ref={videoRef}
                    autoPlay
                    playsInline
                    muted
                    className="w-full h-full object-cover"
                  />
                  <canvas
                    ref={overlayRef}
                    className="absolute inset-0 w-full h-full pointer-events-none"
                  />
                </div>

                <div className="flex flex-col items-center gap-2">
                  <div
                    className={`text-sm ${
                      minMet ? "text-green-600" : "text-yellow-600"
                    }`}
                    aria-live="polite"
                  >
                    {minMet
                      ? "Minimum recording time reached — you can stop now."
                      : `Please record at least ${MIN_RECORDING_TIME}s. ${minRemaining}s remaining.`}
                  </div>

                  <div className="flex justify-center space-x-4">
                    {isRecording ? (
                      <>
                        <Button onClick={handlePauseRecording} variant="outline">
                          {isPaused ? (
                            <Play className="mr-2 h-4 w-4" />
                          ) : (
                            <Pause className="mr-2 h-4 w-4" />
                          )}
                          {isPaused ? "Resume" : "Pause"}
                        </Button>
                        <Button
                          onClick={handleStopRecording}
                          variant="destructive"
                          disabled={!minMet}
                          title={
                            minMet
                              ? "Stop and save recording"
                              : "Reach minimum time before stopping"
                          }
                        >
                          <Square className="mr-2 h-4 w-4" />
                          Stop
                        </Button>
                        <Button onClick={handleReset} variant="outline">
                          <RotateCcw className="mr-2 h-4 w-4" />
                          Reset
                        </Button>
                      </>
                    ) : (
                      !isCurrentTestCompleted && (
                        <Button
                          onClick={handleStartRecording}
                          className="bg-[hsl(var(--secondary))] text-black hover:bg-[hsl(var(--primary-hover))] hover:text-white"
                          disabled={!currentTestId}
                        >
                          <Play className="mr-2 h-4 w-4" />
                          Start Recording
                        </Button>
                      )
                    )}
                  </div>
                </div>

                {isCurrentTestCompleted && (
                  <div className="mt-6 text-center">
                    <div className="bg-success/10 border border-success rounded-lg p-4 mb-4">
                      <CheckCircle className="mx-auto h-8 w-8 text-success mb-2" />
                      <p className="text-success font-semibold">
                        Test Completed Successfully!
                      </p>
                    </div>
                    <div className="flex flex-col items-center gap-3">
                      <Button
                        variant="outline"
                        onClick={handleRetakeCurrentTest}
                        className="w-full sm:w-auto"
                      >
                        Retake Recording
                      </Button>
                      {currentTestIndex < selectedTests.length - 1 ? (
                        <Button
                          onClick={handleNextTest}
                          className="bg-[hsl(var(--secondary))] text-black hover:bg-[hsl(var(--primary-hover))] hover:text-white"
                        >
                          Next Test ({currentTestIndex + 2} of {totalTests})
                        </Button>
                      ) : (
                        <Button
                          onClick={() =>
                            navigate(`/patient/${id}/video-summary/${testId}`)
                          }
                          className="bg-primary hover:bg-primary-hover"
                        >
                          View Summary
                        </Button>
                      )}
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </div>
      </div>
    </div>
  );
};

export default VideoRecording;
