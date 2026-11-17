import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import * as api from "../api/endpoints";
import type { OwnProvider } from "../api/types";
import { ErrorBanner, fieldError } from "./ErrorBanner";

const NUMBERS = [
  { key: "slot_minutes", label: "Visit length (minutes)", min: 5, max: 240 },
  { key: "booking_window_days", label: "Bookable this many days ahead", min: 1, max: 365 },
  { key: "min_notice_hours", label: "Minimum notice (hours)", min: 0, max: 168 },
  { key: "cancel_cutoff_hours", label: "Clients may cancel until (hours before)", min: 0, max: 168 },
] as const;

export function SettingsPanel({ provider }: { provider: OwnProvider }) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState({ ...provider });
  const save = useMutation({
    mutationFn: () =>
      api.updateOwnProvider({
        display_name: form.display_name,
        specialty: form.specialty,
        bio: form.bio,
        timezone: form.timezone,
        slot_minutes: form.slot_minutes,
        booking_window_days: form.booking_window_days,
        min_notice_hours: form.min_notice_hours,
        cancel_cutoff_hours: form.cancel_cutoff_hours,
        is_active: form.is_active,
      }),
    onSuccess: (updated) => {
      queryClient.setQueryData(["own-provider"], updated);
      void queryClient.invalidateQueries({ queryKey: ["providers"] });
    },
  });

  const submit = (e: FormEvent) => {
    e.preventDefault();
    save.mutate();
  };

  return (
    <section aria-labelledby="settings-title" className="panel">
      <h2 id="settings-title">Profile and booking rules</h2>
      <form onSubmit={submit} className="form">
        <label>
          Display name
          <input value={form.display_name} onChange={(e) => setForm({ ...form, display_name: e.target.value })} required />
        </label>
        <label>
          Specialty
          <input value={form.specialty} onChange={(e) => setForm({ ...form, specialty: e.target.value })} />
        </label>
        <label>
          Bio
          <textarea value={form.bio} onChange={(e) => setForm({ ...form, bio: e.target.value })} />
        </label>
        <label>
          Time zone (IANA name, e.g. Asia/Kolkata)
          <input value={form.timezone} onChange={(e) => setForm({ ...form, timezone: e.target.value })} required />
          {fieldError(save.error, "timezone") && <span className="field-error">{fieldError(save.error, "timezone")}</span>}
        </label>
        {NUMBERS.map((n) => (
          <label key={n.key}>
            {n.label}
            <input
              type="number"
              min={n.min}
              max={n.max}
              value={form[n.key]}
              onChange={(e) => setForm({ ...form, [n.key]: Number(e.target.value) })}
              required
            />
            {fieldError(save.error, n.key) && <span className="field-error">{fieldError(save.error, n.key)}</span>}
          </label>
        ))}
        <label className="check">
          <input type="checkbox" checked={form.is_active} onChange={(e) => setForm({ ...form, is_active: e.target.checked })} />
          Accepting new bookings
        </label>
        <ErrorBanner error={save.error} />
        {save.isSuccess && (
          <p role="status" className="banner banner-ok">
            Saved.
          </p>
        )}
        <button type="submit" disabled={save.isPending}>
          {save.isPending ? "Saving…" : "Save settings"}
        </button>
      </form>
    </section>
  );
}
