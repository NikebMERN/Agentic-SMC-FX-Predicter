import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout.jsx";
import ProtectedRoute from "./components/ProtectedRoute.jsx";

const LoginPage = lazy(() => import("./pages/LoginPage.jsx"));
const DashboardPage = lazy(() => import("./pages/DashboardPage.jsx"));
const UsersPage = lazy(() => import("./pages/UsersPage.jsx"));
const UserDetailPage = lazy(() => import("./pages/UserDetailPage.jsx"));
const SignalsPage = lazy(() => import("./pages/SignalsPage.jsx"));
const TradesPage = lazy(() => import("./pages/TradesPage.jsx"));
const ModelsPage = lazy(() => import("./pages/ModelsPage.jsx"));
const PredictPage = lazy(() => import("./pages/PredictPage.jsx"));
const SettingsPage = lazy(() => import("./pages/SettingsPage.jsx"));
const ThresholdsPage = lazy(() => import("./pages/ThresholdsPage.jsx"));
const MLOpsPage = lazy(() => import("./pages/MLOpsPage.jsx"));
const LogsPage = lazy(() => import("./pages/LogsPage.jsx"));
const ReviewsPage = lazy(() => import("./pages/ReviewsPage.jsx"));
const TrainingRecordsPage = lazy(() => import("./pages/TrainingRecordsPage.jsx"));
const AuditPage = lazy(() => import("./pages/AuditPage.jsx"));
const PerformancePage = lazy(() => import("./pages/PerformancePage.jsx"));
const OperationsPage = lazy(() => import("./pages/OperationsPage.jsx"));

export default function App() {
  return (
    <Suspense fallback={<div className="p-8 text-slate-400">Loading page…</div>}>
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<ProtectedRoute />}>
        <Route element={<Layout />}>
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/users" element={<UsersPage />} />
          <Route path="/users/:id" element={<UserDetailPage />} />
          <Route path="/signals" element={<SignalsPage />} />
          <Route path="/trades" element={<TradesPage />} />
          <Route path="/models" element={<ModelsPage />} />
          <Route path="/reviews" element={<ReviewsPage />} />
          <Route path="/training-records" element={<TrainingRecordsPage />} />
          <Route path="/predict" element={<PredictPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/thresholds" element={<ThresholdsPage />} />
          <Route path="/ml-ops" element={<MLOpsPage />} />
          <Route path="/logs" element={<LogsPage />} />
          <Route path="/audit" element={<AuditPage />} />
          <Route path="/performance" element={<PerformancePage />} />
          <Route path="/operations" element={<OperationsPage />} />
        </Route>
      </Route>
      <Route path="/" element={<Navigate to="/dashboard" replace />} />
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
    </Suspense>
  );
}
