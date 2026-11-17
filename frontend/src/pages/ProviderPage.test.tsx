import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { makeUser, mockFetch, renderApp } from "../test/utils";
import { ProviderPage } from "./ProviderPage";

afterEach(() => vi.unstubAllGlobals());

const PROVIDER = {
  id: 7,
  display_name: "Dr Rao",
  specialty: "General practice",
  bio: "",
  timezone: "Asia/Kolkata",
  slot_minutes: 30,
  booking_window_days: 30,
  min_notice_hours: 2,
  cancel_cutoff_hours: 4,
};
const SLOTS = [
  { starts_at: "2030-01-07T03:30:00Z", ends_at: "2030-01-07T04:00:00Z" },
  { starts_at: "2030-01-07T04:00:00Z", ends_at: "2030-01-07T04:30:00Z" },
];
const BOOKED = {
  id: 1,
  provider: 7,
  provider_name: "Dr Rao",
  provider_timezone: "Asia/Kolkata",
  client: 1,
  client_name: "Test Person",
  starts_at: SLOTS[0]!.starts_at,
  ends_at: SLOTS[0]!.ends_at,
  status: "booked",
  notes: "",
  cancelled_at: null,
  created_at: "2029-12-30T00:00:00Z",
};

function page(user = makeUser("client")) {
  return renderApp(
    <Routes>
      <Route path="/providers/:id" element={<ProviderPage />} />
    </Routes>,
    { route: "/providers/7", user },
  );
}

describe("ProviderPage booking", () => {
  it("lists slots in the provider's zone and books the chosen one", async () => {
    const api = mockFetch({
      "GET /api/providers/7/": { json: PROVIDER },
      "GET /api/providers/7/slots/": { json: SLOTS },
      "POST /api/appointments/": { status: 201, json: BOOKED },
    });
    page();

    const button = await screen.findByRole("button", { name: "09:00" });
    expect(screen.getByRole("button", { name: "09:30" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Pick a time to book" })).toBeDisabled();

    await userEvent.click(button);
    await userEvent.type(screen.getByLabelText(/Note for the provider/), "First visit");
    await userEvent.click(screen.getByRole("button", { name: /^Book / }));

    await waitFor(() => expect(api.count("POST /api/appointments/")).toBe(1));
    expect(api.calls.find((c) => c.key === "POST /api/appointments/")?.body).toEqual({
      provider: 7,
      starts_at: "2030-01-07T03:30:00Z",
      notes: "First visit",
    });
    expect(await screen.findByRole("status")).toHaveTextContent("Booked for");
  });

  it("when the slot was just taken: shows why, clears the choice and reloads the slots", async () => {
    const api = mockFetch({
      "GET /api/providers/7/": { json: PROVIDER },
      "GET /api/providers/7/slots/": { json: SLOTS },
      "POST /api/appointments/": {
        status: 409,
        json: { detail: "That slot was just taken. Please pick another time.", code: "slot_unavailable" },
      },
    });
    page();

    await userEvent.click(await screen.findByRole("button", { name: "09:00" }));
    const slotLoadsBefore = api.count("GET /api/providers/7/slots/");
    await userEvent.click(screen.getByRole("button", { name: /^Book / }));

    expect(await screen.findByRole("alert")).toHaveTextContent("That slot was just taken");
    await waitFor(() => expect(api.count("GET /api/providers/7/slots/")).toBeGreaterThan(slotLoadsBefore));
    expect(screen.getByRole("button", { name: "Pick a time to book" })).toBeDisabled();
  });

  it("does not let a provider account book", async () => {
    mockFetch({
      "GET /api/providers/7/": { json: PROVIDER },
      "GET /api/providers/7/slots/": { json: SLOTS },
    });
    page(makeUser("provider"));
    expect(await screen.findByText("Only client accounts can book appointments.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Book / })).not.toBeInTheDocument();
  });

  it("says so when the day has no free slots", async () => {
    mockFetch({ "GET /api/providers/7/": { json: PROVIDER }, "GET /api/providers/7/slots/": { json: [] } });
    page();
    expect(await screen.findByText("No free slots on this day.")).toBeInTheDocument();
  });
});
