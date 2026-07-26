import { lazy, Suspense } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider } from "./context/AuthContext.jsx";
import ProtectedRoute from "./components/ProtectedRoute.jsx";
import PublicLayout from "./components/PublicLayout.jsx";

const HomePage = lazy(() => import("./pages/HomePage.jsx"));
const LoginPage = lazy(() => import("./pages/LoginPage.jsx"));
const RegisterPage = lazy(() => import("./pages/RegisterPage.jsx"));
const FeedbackPage = lazy(() => import("./pages/FeedbackPage.jsx"));
const HistoryPage = lazy(() => import("./pages/HistoryPage.jsx"));
const PredictPage = lazy(() => import("./pages/PredictPage.jsx"));
const TelegramPage = lazy(() => import("./pages/TelegramPage.jsx"));
const AlertsPage = lazy(() => import("./pages/AlertsPage.jsx"));
const ConfirmPage = lazy(() => import("./pages/ConfirmPage.jsx"));

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter basename={import.meta.env.BASE_URL.replace(/\/$/, "") || "/"}>
        <Suspense fallback={<div className="mx-auto max-w-6xl px-4 py-12 text-slate-400">Loading page…</div>}>
        <Routes>
          <Route element={<PublicLayout />}>
            <Route path="/" element={<HomePage />} />
            <Route path="/login" element={<LoginPage />} />
            <Route path="/register" element={<RegisterPage />} />
            <Route
              path="/feedback"
              element={
                <ProtectedRoute>
                  <FeedbackPage />
                </ProtectedRoute>
              }
            />
            <Route
              path="/history"
              element={
                <ProtectedRoute>
                  <HistoryPage />
                </ProtectedRoute>
              }
            />
            <Route
              path="/predict"
              element={
                <ProtectedRoute>
                  <PredictPage />
                </ProtectedRoute>
              }
            />
            <Route
              path="/predict/:symbol"
              element={
                <ProtectedRoute>
                  <PredictPage />
                </ProtectedRoute>
              }
            />
            <Route
              path="/alerts"
              element={
                <ProtectedRoute>
                  <AlertsPage />
                </ProtectedRoute>
              }
            />
            <Route
              path="/confirm/:id"
              element={
                <ProtectedRoute>
                  <ConfirmPage />
                </ProtectedRoute>
              }
            />
            <Route
              path="/telegram"
              element={
                <ProtectedRoute>
                  <TelegramPage />
                </ProtectedRoute>
              }
            />
          </Route>
          <Route path="/dashboard" element={<Navigate to="/feedback" replace />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
        </Suspense>
      </BrowserRouter>
    </AuthProvider>
  );
}
