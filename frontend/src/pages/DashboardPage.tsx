import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import * as api from "../api/endpoints";
import { useAuth } from "../auth/AuthContext";
import { AppointmentList } from "../components/AppointmentList";
import { ErrorBanner } from "../components/ErrorBanner";
import { addDays, todayInZone, zonedDayRange } from "../lib/time";

/** A provider's day. "Day" means a day on THEIR wall clock, so the UTC range depends on their zone. */
export function DashboardPage() {
  const { user } = useAuth();
  const provider = useQuery({ queryKey: ["own-provider"], queryFn: api.getOwnProvider });
  const [chosen, setChosen] = useState<string | null>(null);

  if (provider.isPending) return <p>Loading…</p>;
  if (provider.error) return <ErrorBanner error={provider.error} />;
  const tz = provider.data.timezone;
  const date = chosen ?? todayInZone(tz);
  const range = zonedDayRange(date, tz);

  return (
    <section>
      <h1>Dashboard</h1>
      <p className="muted">
        Your day in {tz}. Need to change hours or time off? <Link to="/schedule">Open your schedule</Link>.
      </p>
      <div className="day-nav" role="group" aria-label="Choose day">
        <button type="button" className="secondary" onClick={() => setChosen(addDays(date, -1))}>
          ← Previous day
        </button>
        <label>
          <span className="visually-hidden">Day</span>
          <input type="date" value={date} onChange={(e) => setChosen(e.target.value || null)} />
        </label>
        <button type="button" className="secondary" onClick={() => setChosen(addDays(date, 1))}>
          Next day →
        </button>
        <button type="button" className="secondary" onClick={() => setChosen(null)}>
          Today
        </button>
      </div>
      <AppointmentList
        filters={{ starts_after: range.start, starts_before: range.end }}
        viewerRole={user?.role ?? "provider"}
        emptyText="Nothing scheduled this day."
      />
    </section>
  );
}
