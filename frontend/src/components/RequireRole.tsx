import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { homeFor, useAuth } from "../auth/AuthContext";
import type { Role } from "../api/types";

/** Route guard. Not signed in -> /login (and back afterwards). Wrong role -> your own home page. */
export function RequireRole({ roles, children }: { roles?: Role[]; children: ReactNode }) {
  const { status, user } = useAuth();
  const location = useLocation();
  if (status === "loading") return <p>Loading…</p>;
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  if (roles && !roles.includes(user.role)) return <Navigate to={homeFor(user.role)} replace />;
  return <>{children}</>;
}
