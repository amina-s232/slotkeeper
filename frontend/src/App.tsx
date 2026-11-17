import { Navigate, Route, Routes } from "react-router-dom";
import { homeFor, useAuth } from "./auth/AuthContext";
import { Layout } from "./components/Layout";
import { RequireRole } from "./components/RequireRole";
import { AppointmentsPage } from "./pages/AppointmentsPage";
import { DashboardPage } from "./pages/DashboardPage";
import { LoginPage } from "./pages/LoginPage";
import { NotFoundPage } from "./pages/NotFoundPage";
import { ProviderPage } from "./pages/ProviderPage";
import { ProvidersPage } from "./pages/ProvidersPage";
import { RegisterPage } from "./pages/RegisterPage";
import { SchedulePage } from "./pages/SchedulePage";

function Home() {
  const { status, user } = useAuth();
  if (status === "loading") return <p>Loading…</p>;
  return <Navigate to={user ? homeFor(user.role) : "/login"} replace />;
}

export function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Home />} />
        <Route path="login" element={<LoginPage />} />
        <Route path="register" element={<RegisterPage />} />
        <Route
          path="providers"
          element={
            <RequireRole roles={["client"]}>
              <ProvidersPage />
            </RequireRole>
          }
        />
        <Route
          path="providers/:id"
          element={
            <RequireRole>
              <ProviderPage />
            </RequireRole>
          }
        />
        <Route
          path="appointments"
          element={
            <RequireRole>
              <AppointmentsPage />
            </RequireRole>
          }
        />
        <Route
          path="dashboard"
          element={
            <RequireRole roles={["provider"]}>
              <DashboardPage />
            </RequireRole>
          }
        />
        <Route
          path="schedule"
          element={
            <RequireRole roles={["provider"]}>
              <SchedulePage />
            </RequireRole>
          }
        />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}
