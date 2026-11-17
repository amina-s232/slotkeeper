import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import * as api from "../api/endpoints";
import type { Appointment, Role, Slot } from "../api/types";
import { formatDateTime, formatTime } from "../lib/time";
import { ErrorBanner } from "./ErrorBanner";
import { SlotPicker } from "./SlotPicker";
import { StatusBadge } from "./StatusBadge";

function useRefreshAfter<TVars>(fn: (vars: TVars) => Promise<Appointment>, after?: () => void) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["appointments"] });
      void queryClient.invalidateQueries({ queryKey: ["slots"] });
      after?.();
    },
  });
}

function ReschedulePanel({ appointment, onDone }: { appointment: Appointment; onDone: () => void }) {
  const [slot, setSlot] = useState<Slot | null>(null);
  const provider = useQuery({ queryKey: ["provider", appointment.provider], queryFn: () => api.getProvider(appointment.provider) });
  const move = useRefreshAfter((startsAt: string) => api.rescheduleAppointment(appointment.id, startsAt), onDone);

  return (
    <div className="panel">
      <SlotPicker
        providerId={appointment.provider}
        timezone={appointment.provider_timezone}
        windowDays={provider.data?.booking_window_days ?? 30}
        selected={slot?.starts_at ?? null}
        onSelect={setSlot}
      />
      <ErrorBanner error={move.error} />
      <div className="actions">
        <button type="button" disabled={!slot || move.isPending} onClick={() => slot && move.mutate(slot.starts_at)}>
          {move.isPending ? "Moving…" : "Move appointment"}
        </button>
        <button type="button" className="secondary" onClick={onDone}>
          Keep current time
        </button>
      </div>
    </div>
  );
}

interface Props {
  appointment: Appointment;
  viewerRole: Role;
  /** Injectable so tests do not depend on the real clock. */
  now?: Date;
}

export function AppointmentCard({ appointment, viewerRole, now = new Date() }: Props) {
  const a = appointment;
  const tz = a.provider_timezone;
  const isBooked = a.status === "booked";
  const hasStarted = new Date(a.starts_at) <= now;
  const [mode, setMode] = useState<"idle" | "confirm-cancel" | "reschedule">("idle");

  const cancel = useRefreshAfter(api.cancelAppointment, () => setMode("idle"));
  const complete = useRefreshAfter(api.completeAppointment);
  const noShow = useRefreshAfter(api.markNoShow);
  const error = cancel.error ?? complete.error ?? noShow.error;
  const busy = cancel.isPending || complete.isPending || noShow.isPending;

  const title =
    viewerRole === "client" ? a.provider_name : viewerRole === "provider" ? a.client_name : `${a.client_name} with ${a.provider_name}`;
  const staff = viewerRole !== "client";

  return (
    <article className="card" aria-label={`Appointment with ${title}`}>
      <header className="card-head">
        <h3>{title}</h3>
        <StatusBadge status={a.status} />
      </header>
      <p>
        <time dateTime={a.starts_at}>{formatDateTime(a.starts_at, tz)}</time> to {formatTime(a.ends_at, tz)}{" "}
        <span className="muted">({tz})</span>
      </p>
      {a.notes && <p className="muted">Note: {a.notes}</p>}
      <ErrorBanner error={error} />

      {isBooked && mode === "idle" && (
        <div className="actions">
          {!hasStarted && (
            <>
              <button type="button" className="secondary" onClick={() => setMode("reschedule")}>
                Reschedule
              </button>
              <button type="button" className="danger" onClick={() => setMode("confirm-cancel")}>
                Cancel appointment
              </button>
            </>
          )}
          {staff && hasStarted && (
            <>
              <button type="button" disabled={busy} onClick={() => complete.mutate(a.id)}>
                Mark completed
              </button>
              <button type="button" className="secondary" disabled={busy} onClick={() => noShow.mutate(a.id)}>
                Mark no-show
              </button>
            </>
          )}
        </div>
      )}

      {mode === "confirm-cancel" && (
        <div className="actions" role="group" aria-label="Confirm cancellation">
          <span>Cancel this appointment?</span>
          <button type="button" className="danger" disabled={busy} onClick={() => cancel.mutate(a.id)}>
            Yes, cancel it
          </button>
          <button type="button" className="secondary" onClick={() => setMode("idle")}>
            Keep it
          </button>
        </div>
      )}

      {mode === "reschedule" && <ReschedulePanel appointment={a} onDone={() => setMode("idle")} />}
    </article>
  );
}
