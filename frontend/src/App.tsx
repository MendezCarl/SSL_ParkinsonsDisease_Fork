import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import PatientList from "./pages/PatientList";
import PatientDetails from "./pages/PatientDetails";
import PatientForm from "./pages/PatientForm";
import TestSelection from "./pages/TestSelection";
import VideoRecording from "./pages/VideoRecording";
import VideoSummary from "./pages/VideoSummary";
import Timeline from "./pages/Timeline";
import NotFound from "./pages/NotFound";
import Login from "./pages/Login";
import Register from "./pages/Register";
import Profile from "./pages/Profile";
import Welcome from "./pages/Welcome";
import { AuthProvider } from "@/auth/auth-context";
import { useAuth } from "@/auth/auth-context";

const queryClient = new QueryClient();

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

const App = () => (
  <QueryClientProvider client={queryClient}>
    <AuthProvider>
      <TooltipProvider>
        <Toaster />
        <Sonner />
        <BrowserRouter>
          <Routes>
            <Route path="/" element={<ProtectedRoute><PatientList /></ProtectedRoute>} />
            <Route path="/patients" element={<ProtectedRoute><PatientList /></ProtectedRoute>} />
            <Route path="/patient/:id" element={<ProtectedRoute><PatientDetails /></ProtectedRoute>} />
            <Route path="/patient-form" element={<ProtectedRoute><PatientForm /></ProtectedRoute>} />
            <Route path="/patient-form/:id" element={<ProtectedRoute><PatientForm /></ProtectedRoute>} />
            <Route path="/patient/:id/test-selection" element={<ProtectedRoute><TestSelection /></ProtectedRoute>} />
            <Route path="/patient/:id/video-recording/:testId" element={<ProtectedRoute><VideoRecording /></ProtectedRoute>} />
            <Route path="/patient/:id/video-summary" element={<ProtectedRoute><VideoSummary /></ProtectedRoute>} />
            <Route path="/patient/:id/video-summary/:testId" element={<ProtectedRoute><VideoSummary /></ProtectedRoute>} />
            <Route path="/patients/:id/video-summary/:testId" element={<ProtectedRoute><VideoSummary /></ProtectedRoute>} />
            <Route path="/patients/:patientId/timeline" element={<ProtectedRoute><Timeline /></ProtectedRoute>} />
            <Route path="/login" element={<Login />}/>
            <Route path="/register" element={<Register />}/>
            <Route path="/profile" element={<ProtectedRoute><Profile /></ProtectedRoute>}/>
            <Route path="/welcome" element={<Welcome />}/>
            <Route path="*" element={<NotFound />} />
          </Routes>
        </BrowserRouter>
      </TooltipProvider>
    </AuthProvider>
  </QueryClientProvider>
);

export default App;
