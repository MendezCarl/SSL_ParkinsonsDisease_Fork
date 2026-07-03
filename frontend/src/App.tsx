import { Suspense, lazy } from "react";
import { Toaster } from "@/components/ui/toaster";
import { TooltipProvider } from "@/components/ui/tooltip";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider } from "@/auth/auth-context";
import { useAuth } from "@/auth/auth-context";

const PatientList = lazy(() => import("./pages/PatientList"));
const PatientDetails = lazy(() => import("./pages/PatientDetails"));
const PatientForm = lazy(() => import("./pages/PatientForm"));
const TestSelection = lazy(() => import("./pages/TestSelection"));
const VideoRecording = lazy(() => import("./pages/VideoRecording"));
const VideoSummary = lazy(() => import("./pages/VideoSummary"));
const Timeline = lazy(() => import("./pages/Timeline"));
const NotFound = lazy(() => import("./pages/NotFound"));
const Login = lazy(() => import("./pages/Login"));
const Register = lazy(() => import("./pages/Register"));
const Profile = lazy(() => import("./pages/Profile"));
const Welcome = lazy(() => import("./pages/Welcome"));

const ProtectedRoute = ({ children }: { children: JSX.Element }) => {
  const { isAuthenticated, isLoading } = useAuth();

  if (isLoading) {
    return <div className="min-h-screen flex items-center justify-center">Loading session...</div>;
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  return children;
};

const RouteFallback = () => (
  <div className="min-h-screen flex items-center justify-center">Loading page...</div>
);

const App = () => (
  <AuthProvider>
    <TooltipProvider>
      <Toaster />
      <BrowserRouter>
        <Suspense fallback={<RouteFallback />}>
          <Routes>
            <Route path="/" element={<Navigate to="/patients" replace />} />
            <Route path="/patients" element={<ProtectedRoute><PatientList /></ProtectedRoute>} />
            <Route path="/patients/new" element={<ProtectedRoute><PatientForm /></ProtectedRoute>} />
            <Route path="/patients/:id" element={<ProtectedRoute><PatientDetails /></ProtectedRoute>} />
            <Route path="/patients/:id/edit" element={<ProtectedRoute><PatientForm /></ProtectedRoute>} />
            <Route path="/patients/:id/test-selection" element={<ProtectedRoute><TestSelection /></ProtectedRoute>} />
            <Route path="/patients/:id/video-recording/:testId" element={<ProtectedRoute><VideoRecording /></ProtectedRoute>} />
            <Route path="/patients/:id/video-summary" element={<ProtectedRoute><VideoSummary /></ProtectedRoute>} />
            <Route path="/patients/:id/video-summary/:testId" element={<ProtectedRoute><VideoSummary /></ProtectedRoute>} />
            <Route path="/patients/:patientId/timeline" element={<ProtectedRoute><Timeline /></ProtectedRoute>} />
            <Route path="/login" element={<Login />}/>
            <Route path="/register" element={<Register />}/>
            <Route path="/profile" element={<ProtectedRoute><Profile /></ProtectedRoute>}/>
            <Route path="/welcome" element={<Welcome />}/>
            <Route path="*" element={<NotFound />} />
          </Routes>
        </Suspense>
      </BrowserRouter>
    </TooltipProvider>
  </AuthProvider>
);

export default App;
