/**
 * Time helpers. The API stores and returns UTC instants. A "day" for booking purposes is a day on
 * the PROVIDER's wall clock, so every conversion here takes an explicit IANA timezone instead of
 * trusting the browser's.
 */

const WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
export const weekdayName = (weekday: number): string => WEEKDAYS[weekday] ?? "?";

function parts(instant: Date, timeZone: string): Record<string, number> {
  const formatter = new Intl.DateTimeFormat("en-US", {
    timeZone,
    hourCycle: "h23",
    year: "numeric",
    month: "numeric",
    day: "numeric",
    hour: "numeric",
    minute: "numeric",
    second: "numeric",
  });
  const out: Record<string, number> = {};
  for (const part of formatter.formatToParts(instant)) {
    if (part.type !== "literal") out[part.type] = Number(part.value);
  }
  return out;
}

/** Milliseconds the zone is ahead of UTC at this instant (+19_800_000 for Asia/Kolkata). */
function offsetMs(instant: Date, timeZone: string): number {
  const p = parts(instant, timeZone);
  const asUtc = Date.UTC(p.year ?? 0, (p.month ?? 1) - 1, p.day ?? 1, p.hour ?? 0, p.minute ?? 0, p.second ?? 0);
  return asUtc - Math.floor(instant.getTime() / 1000) * 1000;
}

/** The UTC instant at which the wall clock in `timeZone` reads `date` `time` ("YYYY-MM-DD", "HH:MM"). */
export function zonedInstant(date: string, time: string, timeZone: string): Date {
  const [y = 0, m = 1, d = 1] = date.split("-").map(Number);
  const [hh = 0, mm = 0] = time.split(":").map(Number);
  const wallAsUtc = Date.UTC(y, m - 1, d, hh, mm, 0);
  let guess = wallAsUtc;
  for (let i = 0; i < 3; i++) {
    // Re-measure the offset at the guess: it can differ from the offset at "wallAsUtc" on a DST day.
    const next = wallAsUtc - offsetMs(new Date(guess), timeZone);
    if (next === guess) break;
    guess = next;
  }
  return new Date(guess);
}

export function addDays(date: string, days: number): string {
  const [y = 0, m = 1, d = 1] = date.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d + days)).toISOString().slice(0, 10);
}

/** [start, end) of one calendar day in `timeZone`, as ISO strings the API's filters accept. */
export function zonedDayRange(date: string, timeZone: string): { start: string; end: string } {
  return {
    start: zonedInstant(date, "00:00", timeZone).toISOString(),
    end: zonedInstant(addDays(date, 1), "00:00", timeZone).toISOString(),
  };
}

export function todayInZone(timeZone: string, now: Date = new Date()): string {
  const p = parts(now, timeZone);
  const pad = (n: number | undefined) => String(n ?? 0).padStart(2, "0");
  return `${p.year}-${pad(p.month)}-${pad(p.day)}`;
}

export function formatTime(iso: string, timeZone: string): string {
  return new Intl.DateTimeFormat("en-GB", { timeZone, hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).format(
    new Date(iso),
  );
}

export function formatDate(iso: string, timeZone: string): string {
  return new Intl.DateTimeFormat("en-GB", { timeZone, weekday: "short", day: "numeric", month: "short", year: "numeric" }).format(
    new Date(iso),
  );
}

export function formatDateTime(iso: string, timeZone: string): string {
  return `${formatDate(iso, timeZone)}, ${formatTime(iso, timeZone)}`;
}

/** "09:00:00" (what the API returns) -> "09:00". */
export const shortTime = (value: string): string => value.slice(0, 5);

/** `value` is what <input type="datetime-local"> gives ("2030-01-07T09:00", with NO zone). Read it as the PROVIDER's wall clock. */
export function wallClockToUtcIso(value: string, timeZone: string): string {
  const [date = "", time = "00:00"] = value.split("T");
  return zonedInstant(date, time, timeZone).toISOString();
}
