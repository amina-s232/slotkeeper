import { useState } from "react";
import type { AppointmentStatus } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { AppointmentList } from "../components/AppointmentList";

const STATUSES: { value: "" | AppointmentStatus; label: string }[] = [
  { value: "", label: "All" },
  { value: "booked", label: "Booked" },
  { value: "completed", label: "Completed" },
  { value: "cancelled", label: "Cancelled" },
  { value: "no_show", label: "No show" },
];

export function AppointmentsPage() {
  const { user } = useAuth();
  const [status, setStatus] = useState<"" | AppointmentStatus>("");
  if (!user) return null;
  return (
    <section>
      <h1>{user.role === "client" ? "My appointments" : "All appointments"}</h1>
      <label className="inline-label">
        Show
        <select value={status} onChange={(e) => setStatus(e.target.value as "" | AppointmentStatus)}>
          {STATUSES.map((s) => (
            <option key={s.value} value={s.value}>
              {s.label}
            </option>
          ))}
        </select>
      </label>
      <AppointmentList
        filters={status ? { status } : {}}
        viewerRole={user.role}
        emptyText={user.role === "client" ? "You have no appointments yet." : "No appointments."}
      />
    </section>
  );
}
