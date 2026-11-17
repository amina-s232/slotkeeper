import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import * as api from "../api/endpoints";
import type { Slot } from "../api/types";
import { addDays, formatTime, todayInZone } from "../lib/time";
import { ErrorBanner } from "./ErrorBanner";

interface Props {
  providerId: number;
  timezone: string;
  windowDays: number;
  /** `starts_at` of the chosen slot, if any. */
  selected: string | null;
  onSelect: (slot: Slot) => void;
}

/** Pick a day (on the PROVIDER's calendar), then one of that day's free slots. */
export function SlotPicker({ providerId, timezone, windowDays, selected, onSelect }: Props) {
  const today = todayInZone(timezone);
  const [date, setDate] = useState(today);
  const slots = useQuery({ queryKey: ["slots", providerId, date], queryFn: () => api.getSlots(providerId, date) });

  return (
    <div className="slot-picker">
      <label>
        Day
        <input type="date" value={date} min={today} max={addDays(today, windowDays)} onChange={(e) => setDate(e.target.value || today)} />
      </label>
      <p className="muted">Times are shown in the provider&apos;s time zone ({timezone}).</p>
      {slots.isPending && <p>Loading slots…</p>}
      <ErrorBanner error={slots.error} />
      {slots.data && slots.data.length === 0 && <p>No free slots on this day.</p>}
      {slots.data && slots.data.length > 0 && (
        <ul className="slots" aria-label="Free slots">
          {slots.data.map((slot) => (
            <li key={slot.starts_at}>
              <button
                type="button"
                className={slot.starts_at === selected ? "slot slot-selected" : "slot"}
                aria-pressed={slot.starts_at === selected}
                onClick={() => onSelect(slot)}
              >
                {formatTime(slot.starts_at, timezone)}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
