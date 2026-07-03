import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider } from "./context/AuthContext.jsx";
import ProtectedRoute from "./components/ProtectedRoute.jsx";
import PublicLayout from "./components/PublicLayout.jsx";
import HomePage from "./pages/HomePage.jsx";
import LoginPage from "./pages/LoginPage.jsx";
import RegisterPage from "./pages/RegisterPage.jsx";
import FeedbackPage from "./pages/FeedbackPage.jsx";
import HistoryPage from "./pages/HistoryPage.jsx";
import PredictPage from "./pages/PredictPage.jsx";
import TelegramPage from "./pages/TelegramPage.jsx";

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter basename={import.meta.env.BASE_URL.replace(/\/$/, "") || "/"}>
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
      </BrowserRouter>
    </AuthProvider>
  );
}
