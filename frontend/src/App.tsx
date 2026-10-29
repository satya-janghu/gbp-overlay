import { BrowserRouter, Routes, Route } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "sonner";
import { Layout } from "@/components/layout/layout";
import { SetupPage } from "@/pages/setup-page";
import { ReviewPage } from "@/pages/review-page";
import { ProgressPage } from "@/pages/progress-page";
import { ProjectsPage } from "@/pages/projects-page";
import { GuidePage } from "@/pages/guide-page";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 10_000,
    },
  },
});

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <Toaster position="top-right" richColors />
      <BrowserRouter>
        <Routes>
          <Route element={<Layout />}>
            <Route path="/" element={<SetupPage />} />
            <Route path="/project/:id/review" element={<ReviewPage />} />
            <Route path="/project/:id/progress" element={<ProgressPage />} />
            <Route path="/projects" element={<ProjectsPage />} />
            <Route path="/guide" element={<GuidePage />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
