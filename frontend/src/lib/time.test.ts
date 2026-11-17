import { describe, expect, it } from "vitest";
import { addDays, formatDateTime, formatTime, shortTime, todayInZone, wallClockToUtcIso, zonedDayRange, zonedInstant } from "./time";

describe("formatTime", () => {
  it("shows the wall clock of the given zone, not the browser's", () => {
    expect(formatTime("2030-01-07T03:30:00Z", "Asia/Kolkata")).toBe("09:00");
    expect(formatTime("2030-01-07T03:30:00Z", "America/New_York")).toBe("22:30");
    expect(formatTime("2030-01-07T03:30:00Z", "UTC")).toBe("03:30");
  });

  it("includes the date for formatDateTime", () => {
    const text = formatDateTime("2030-01-07T03:30:00Z", "Asia/Kolkata");
    expect(text).toContain("7");
    expect(text).toContain("Jan");
    expect(text).toContain("09:00");
  });
});

describe("zonedDayRange", () => {
  it("covers one local day in Asia/Kolkata (UTC+05:30)", () => {
    expect(zonedDayRange("2030-01-07", "Asia/Kolkata")).toEqual({
      start: "2030-01-06T18:30:00.000Z",
      end: "2030-01-07T18:30:00.000Z",
    });
  });

  it("is only 23 hours long on the day US clocks go forward", () => {
    const { start, end } = zonedDayRange("2030-03-10", "America/New_York");
    expect(start).toBe("2030-03-10T05:00:00.000Z"); // midnight EST = UTC-5
    expect(end).toBe("2030-03-11T04:00:00.000Z"); // next midnight EDT = UTC-4
    expect((Date.parse(end) - Date.parse(start)) / 3_600_000).toBe(23);
  });

  it("is 25 hours long on the day US clocks go back", () => {
    const { start, end } = zonedDayRange("2030-11-03", "America/New_York");
    expect((Date.parse(end) - Date.parse(start)) / 3_600_000).toBe(25);
  });

  it("leaves the end open: the next day's first instant is the following range's start", () => {
    expect(zonedDayRange("2030-01-07", "Asia/Kolkata").end).toBe(zonedDayRange("2030-01-08", "Asia/Kolkata").start);
  });
});

describe("zonedInstant", () => {
  it("converts a wall-clock time in a zone to the right UTC instant", () => {
    expect(zonedInstant("2030-01-07", "09:00", "Asia/Kolkata").toISOString()).toBe("2030-01-07T03:30:00.000Z");
    expect(zonedInstant("2030-07-01", "09:00", "America/New_York").toISOString()).toBe("2030-07-01T13:00:00.000Z");
    expect(zonedInstant("2030-01-01", "09:00", "America/New_York").toISOString()).toBe("2030-01-01T14:00:00.000Z");
  });

  it("gets a time AFTER the clocks change right (this is what the second measuring pass is for)", () => {
    // 2030-03-10: New York jumps from EST (UTC-5) to EDT (UTC-4) at 02:00 local.
    expect(zonedInstant("2030-03-10", "03:30", "America/New_York").toISOString()).toBe("2030-03-10T07:30:00.000Z");
    // 2030-11-03: back from EDT to EST at 02:00 local.
    expect(zonedInstant("2030-11-03", "03:30", "America/New_York").toISOString()).toBe("2030-11-03T08:30:00.000Z");
  });
});

describe("dates", () => {
  it("adds days across month and year ends", () => {
    expect(addDays("2030-01-31", 1)).toBe("2030-02-01");
    expect(addDays("2030-01-01", -1)).toBe("2029-12-31");
    expect(addDays("2028-02-28", 1)).toBe("2028-02-29"); // leap year
  });

  it("reads today's date in the given zone", () => {
    const moment = new Date("2030-01-07T20:00:00Z"); // already Tuesday morning in Kolkata
    expect(todayInZone("Asia/Kolkata", moment)).toBe("2030-01-08");
    expect(todayInZone("America/New_York", moment)).toBe("2030-01-07");
  });

  it("trims seconds from API times", () => {
    expect(shortTime("09:00:00")).toBe("09:00");
  });
});


describe("wallClockToUtcIso (time-off form)", () => {
  it("reads a datetime-local value as the PROVIDER's wall clock, whatever the browser's zone", () => {
    expect(wallClockToUtcIso("2030-01-07T09:00", "Asia/Kolkata")).toBe("2030-01-07T03:30:00.000Z");
    expect(wallClockToUtcIso("2030-07-01T09:00", "America/New_York")).toBe("2030-07-01T13:00:00.000Z");
  });
});
