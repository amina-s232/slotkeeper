import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";

export function Layout() {
  const { user, logout } = useAuth();
  return (
    <>
      <header className="topbar">
        <NavLink to="/" className="brand">
          SlotKeeper
        </NavLink>
        <nav aria-label="Main">
          {user?.role === "client" && (
            <>
              <NavLink to="/providers">Providers</NavLink>
              <NavLink to="/appointments">My appointments</NavLink>
            </>
          )}
          {user?.role === "provider" && (
            <>
              <NavLink to="/dashboard">Dashboard</NavLink>
              <NavLink to="/appointments">All appointments</NavLink>
              <NavLink to="/schedule">Schedule</NavLink>
            </>
          )}
          {user?.role === "admin" && <NavLink to="/appointments">All appointments</NavLink>}
        </nav>
        <div className="who">
          {user ? (
            <>
              <span>{user.full_name}</span>
              <button type="button" className="secondary" onClick={logout}>
                Sign out
              </button>
            </>
          ) : (
            <>
              <NavLink to="/login">Sign in</NavLink>
              <NavLink to="/register">Register</NavLink>
            </>
          )}
        </div>
      </header>
      <main className="page">
        <Outlet />
      </main>
    </>
  );
}
