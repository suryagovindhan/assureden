import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider, createTheme, CssBaseline } from "@mui/material";

import { AuthProvider } from "./contexts/AuthContext";
import ProtectedRoute from "./components/ProtectedRoute";

import LoginPage      from "./pages/LoginPage";
import DashboardShell from "./pages/DashboardShell";
import DashboardHome  from "./pages/DashboardHome";
import UsersPage      from "./pages/admin/UsersPage";
import AgentsPage     from "./pages/admin/AgentsPage";
import ObjectExplorer    from "./pages/objects/ObjectExplorer";
import KeywordSearch     from "./pages/objects/KeywordSearch";
import TestSuiteBrowser  from "./pages/test_cases/TestSuiteBrowser";
import AllCasesPage      from "./pages/test_cases/AllCasesPage";
import TestCaseEditor    from "./pages/test_cases/TestCaseEditor";
import EnvironmentsPage  from "./pages/environments/EnvironmentsPage";
import FlowsPage         from "./pages/flows/FlowsPage";
import RunsPage          from "./pages/runs/RunsPage";
import RunDetailPage     from "./pages/runs/RunDetailPage";
import SchedulesPage     from "./pages/schedules/SchedulesPage";
import ReportsPage       from "./pages/reports/ReportsPage";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 30_000,
    },
  },
});

const theme = createTheme({
  palette: {
    mode: "dark",
    primary:    { main: "#667eea" },
    secondary:  { main: "#764ba2" },
    background: { default: "#0d0d1a", paper: "#13132a" },
  },
  typography: {
    fontFamily: "'Inter', 'Roboto', sans-serif",
  },
  components: {
    MuiButton: {
      styleOverrides: {
        root: { borderRadius: 8, textTransform: "none" },
      },
    },
    MuiCard: {
      styleOverrides: {
        root: { borderRadius: 12 },
      },
    },
  },
});

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider theme={theme}>
        <CssBaseline />
        <AuthProvider>
          <BrowserRouter>
            <Routes>
              <Route path="/login" element={<LoginPage />} />

              <Route element={<ProtectedRoute />}>
                <Route element={<DashboardShell />}>
                  <Route path="/dashboard" element={<DashboardHome />} />
                  <Route path="/objects"        element={<ObjectExplorer />} />
                  <Route path="/objects/search" element={<KeywordSearch />} />
                  <Route path="/test-cases"          element={<TestSuiteBrowser />} />
                  <Route path="/test-cases/all"      element={<AllCasesPage />} />
                  <Route path="/test-cases/:case_id" element={<TestCaseEditor />} />
                  <Route path="/environments"        element={<EnvironmentsPage />} />
                  <Route path="/flows"               element={<FlowsPage />} />
                  <Route path="/runs"                element={<RunsPage />} />
                  <Route path="/runs/:run_id"        element={<RunDetailPage />} />
                  <Route path="/schedules"           element={<SchedulesPage />} />
                  <Route path="/reports"             element={<ReportsPage />} />
                  <Route path="/admin/users"   element={<UsersPage />} />
                  <Route path="/admin/agents"  element={<AgentsPage />} />
                </Route>
              </Route>

              <Route path="/" element={<Navigate to="/dashboard" replace />} />
              <Route path="*" element={<Navigate to="/dashboard" replace />} />
            </Routes>
          </BrowserRouter>
        </AuthProvider>
      </ThemeProvider>
    </QueryClientProvider>
  );
}
