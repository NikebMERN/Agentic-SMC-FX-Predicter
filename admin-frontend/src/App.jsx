import { Navigate, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout.jsx";
import ProtectedRoute from "./components/ProtectedRoute.jsx";
import LoginPage from "./pages/LoginPage.jsx";
import DashboardPage from "./pages/DashboardPage.jsx";
import UsersPage from "./pages/UsersPage.jsx";
import UserDetailPage from "./pages/UserDetailPage.jsx";
import SignalsPage from "./pages/SignalsPage.jsx";
import TradesPage from "./pages/TradesPage.jsx";
import ModelsPage from "./pages/ModelsPage.jsx";
import PredictPage from "./pages/PredictPage.jsx";
import SettingsPage from "./pages/SettingsPage.jsx";
import LogsPage from "./pages/LogsPage.jsx";
import ReviewsPage from "./pages/ReviewsPage.jsx";
import TrainingRecordsPage from "./pages/TrainingRecordsPage.jsx";
import AuditPage from "./pages/AuditPage.jsx";

export default function App() {
  return (
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
          <Route path="/logs" element={<LogsPage />} />
          <Route path="/audit" element={<AuditPage />} />
        </Route>
      </Route>
      <Route path="/" element={<Navigate to="/dashboard" replace />} />
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  );
}
