import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import * as api from "../api/endpoints";
import { shortTime, weekdayName } from "../lib/time";
import { ErrorBanner } from "./ErrorBanner";

export function RulesPanel() {
  const queryClient = useQueryClient();
  const rules = useQuery({ queryKey: ["rules"], queryFn: api.listRules });
  const [form, setForm] = useState({ weekday: 0, start_time: "09:00", end_time: "12:00" });
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["rules"] });
  const add = useMutation({ mutationFn: api.createRule, onSuccess: refresh });
  const remove = useMutation({ mutationFn: api.deleteRule, onSuccess: refresh });

  const submit = (e: FormEvent) => {
    e.preventDefault();
    add.mutate(form);
  };

  return (
    <section aria-labelledby="rules-title" className="panel">
      <h2 id="rules-title">Weekly working hours</h2>
      {rules.isPending && <p>Loading…</p>}
      <ErrorBanner error={rules.error} />
      {rules.data && rules.data.length === 0 && <p>No working hours yet. Clients cannot book you until you add some.</p>}
      <ul className="plain">
        {rules.data?.map((rule) => (
          <li key={rule.id} className="row">
            <span>
              {weekdayName(rule.weekday)} {shortTime(rule.start_time)}–{shortTime(rule.end_time)}
            </span>
            <button type="button" className="danger small" disabled={remove.isPending} onClick={() => remove.mutate(rule.id)}>
              Remove
              <span className="visually-hidden">
                {" "}
                {weekdayName(rule.weekday)} {shortTime(rule.start_time)}
              </span>
            </button>
          </li>
        ))}
      </ul>
      <ErrorBanner error={remove.error} />

      <form onSubmit={submit} className="inline-form">
        <label>
          Day
          <select value={form.weekday} onChange={(e) => setForm({ ...form, weekday: Number(e.target.value) })}>
            {Array.from({ length: 7 }, (_, d) => (
              <option key={d} value={d}>
                {weekdayName(d)}
              </option>
            ))}
          </select>
        </label>
        <label>
          From
          <input type="time" value={form.start_time} onChange={(e) => setForm({ ...form, start_time: e.target.value })} required />
        </label>
        <label>
          To
          <input type="time" value={form.end_time} onChange={(e) => setForm({ ...form, end_time: e.target.value })} required />
        </label>
        <button type="submit" disabled={add.isPending}>
          Add hours
        </button>
      </form>
      <ErrorBanner error={add.error} />
    </section>
  );
}
