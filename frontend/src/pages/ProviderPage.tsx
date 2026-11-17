import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ApiError } from "../api/client";
import * as api from "../api/endpoints";
import type { Appointment, Slot } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { ErrorBanner } from "../components/ErrorBanner";
import { SlotPicker } from "../components/SlotPicker";
import { formatDateTime } from "../lib/time";

export function ProviderPage() {
  const providerId = Number(useParams().id);
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const provider = useQuery({ queryKey: ["provider", providerId], queryFn: () => api.getProvider(providerId) });
  const [slot, setSlot] = useState<Slot | null>(null);
  const [notes, setNotes] = useState("");
  const [booked, setBooked] = useState<Appointment | null>(null);

  const book = useMutation({
    mutationFn: (startsAt: string) => api.bookAppointment({ provider: providerId, starts_at: startsAt, notes }),
    onSuccess: (appointment) => {
      setBooked(appointment);
      setSlot(null);
      setNotes("");
      void queryClient.invalidateQueries({ queryKey: ["appointments"] });
      void queryClient.invalidateQueries({ queryKey: ["slots", providerId] });
    },
    onError: (error) => {
      // Somebody else got there first (or we double-booked ourselves). Drop the stale choice and
      // reload the day, so the slot list the person sees is the truth again.
      if (error instanceof ApiError && (error.code === "slot_unavailable" || error.code === "client_conflict")) {
        setSlot(null);
        void queryClient.invalidateQueries({ queryKey: ["slots", providerId] });
      }
    },
  });

  if (provider.isPending) return <p>Loading…</p>;
  if (provider.error) return <ErrorBanner error={provider.error} />;
  const p = provider.data;
  const isClient = user?.role === "client";

  return (
    <section>
      <p>
        <Link to="/providers">← All providers</Link>
      </p>
      <h1>{p.display_name}</h1>
      <p className="muted">{p.specialty || "General"}</p>
      {p.bio && <p>{p.bio}</p>}
      <p className="muted">
        {p.slot_minutes}-minute visits. Book at least {p.min_notice_hours} hours ahead. Free cancellation until {p.cancel_cutoff_hours} hours
        before.
      </p>

      {booked && (
        <p role="status" className="banner banner-ok">
          Booked for {formatDateTime(booked.starts_at, booked.provider_timezone)}. <Link to="/appointments">See my appointments</Link>
        </p>
      )}

      <h2>Choose a time</h2>
      <SlotPicker
        providerId={p.id}
        timezone={p.timezone}
        windowDays={p.booking_window_days}
        selected={slot?.starts_at ?? null}
        onSelect={(s) => {
          setSlot(s);
          setBooked(null);
          book.reset();
        }}
      />

      {isClient ? (
        <form
          className="form"
          onSubmit={(e) => {
            e.preventDefault();
            if (slot) book.mutate(slot.starts_at);
          }}
        >
          <label>
            Note for the provider (optional)
            <textarea value={notes} maxLength={500} onChange={(e) => setNotes(e.target.value)} />
          </label>
          <ErrorBanner error={book.error} />
          <button type="submit" disabled={!slot || book.isPending}>
            {book.isPending ? "Booking…" : slot ? `Book ${formatDateTime(slot.starts_at, p.timezone)}` : "Pick a time to book"}
          </button>
        </form>
      ) : (
        <p className="muted">Only client accounts can book appointments.</p>
      )}
    </section>
  );
}
