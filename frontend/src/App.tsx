import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route } from "react-router-dom";
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

const queryClient = new QueryClient();

const App = () => (
  <QueryClientProvider client={queryClient}>
    <TooltipProvider>
      <Toaster />
      <Sonner />
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<PatientList />} />
          <Route path="/patients" element={<PatientList />} />
          <Route path="/patient/:id" element={<PatientDetails />} />
          <Route path="/patient-form" element={<PatientForm />} />
          <Route path="/patient-form/:id" element={<PatientForm />} />
          <Route path="/patient/:id/test-selection" element={<TestSelection />} />
          <Route path="/patient/:id/video-recording/:testId" element={<VideoRecording />} />
          <Route path="/patient/:id/video-summary" element={<VideoSummary />} />
          <Route path="/patient/:id/video-summary/:testId" element={<VideoSummary />} />
          <Route path="/patients/:id/video-summary/:testId" element={<VideoSummary />} />
          <Route path="/patients/:patientId/timeline" element={<Timeline />} />
          <Route path="/login" element={<Login />}/>
          <Route path="/register" element={<Register />}/>
          <Route path="/profile" element={<Profile />}/>
          <Route path="/welcome" element={<Welcome />}/>
          <Route path="*" element={<NotFound />} />
        </Routes>
      </BrowserRouter>
    </TooltipProvider>
  </QueryClientProvider>
);

export default App;
