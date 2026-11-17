import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import * as api from "../api/endpoints";
import { formatDateTime, wallClockToUtcIso } from "../lib/time";
import { ErrorBanner } from "./ErrorBanner";

export function TimeOffPanel({ timezone }: { timezone: string }) {
  const queryClient = useQueryClient();
  const items = useQuery({ queryKey: ["time-off"], queryFn: api.listTimeOff });
  const [form, setForm] = useState({ starts: "", ends: "", reason: "" });
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["time-off"] });
  const add = useMutation({
    mutationFn: api.createTimeOff,
    onSuccess: () => {
      setForm({ starts: "", ends: "", reason: "" });
      return refresh();
    },
  });
  const remove = useMutation({ mutationFn: api.deleteTimeOff, onSuccess: refresh });

  const submit = (e: FormEvent) => {
    e.preventDefault();
    add.mutate({
      starts_at: wallClockToUtcIso(form.starts, timezone),
      ends_at: wallClockToUtcIso(form.ends, timezone),
      reason: form.reason,
    });
  };

  return (
    <section aria-labelledby="timeoff-title" className="panel">
      <h2 id="timeoff-title">Time off</h2>
      <p className="muted">Enter times as they read on your clock ({timezone}).</p>
      {items.isPending && <p>Loading…</p>}
      <ErrorBanner error={items.error} />
      {items.data && items.data.length === 0 && <p>No time off scheduled.</p>}
      <ul className="plain">
        {items.data?.map((t) => (
          <li key={t.id} className="row">
            <span>
              {formatDateTime(t.starts_at, timezone)} → {formatDateTime(t.ends_at, timezone)}
              {t.reason && <span className="muted"> · {t.reason}</span>}
            </span>
            <button type="button" className="danger small" disabled={remove.isPending} onClick={() => remove.mutate(t.id)}>
              Remove
              <span className="visually-hidden"> time off starting {formatDateTime(t.starts_at, timezone)}</span>
            </button>
          </li>
        ))}
      </ul>
      <ErrorBanner error={remove.error} />

      <form onSubmit={submit} className="inline-form">
        <label>
          From
          <input type="datetime-local" value={form.starts} onChange={(e) => setForm({ ...form, starts: e.target.value })} required />
        </label>
        <label>
          To
          <input type="datetime-local" value={form.ends} onChange={(e) => setForm({ ...form, ends: e.target.value })} required />
        </label>
        <label>
          Reason
          <input value={form.reason} maxLength={200} onChange={(e) => setForm({ ...form, reason: e.target.value })} />
        </label>
        <button type="submit" disabled={add.isPending}>
          Add time off
        </button>
      </form>
      <ErrorBanner error={add.error} />
    </section>
  );
}
