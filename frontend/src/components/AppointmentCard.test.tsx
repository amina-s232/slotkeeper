import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Appointment } from "../api/types";
import { makeUser, mockFetch, renderApp } from "../test/utils";
import { AppointmentCard } from "./AppointmentCard";

afterEach(() => vi.unstubAllGlobals());

const NOW = new Date("2030-01-01T00:00:00Z");

function appointment(overrides: Partial<Appointment> = {}): Appointment {
  return {
    id: 5,
    provider: 7,
    provider_name: "Dr Rao",
    provider_timezone: "Asia/Kolkata",
    client: 1,
    client_name: "Asha Nair",
    starts_at: "2030-01-07T03:30:00Z",
    ends_at: "2030-01-07T04:00:00Z",
    status: "booked",
    notes: "",
    cancelled_at: null,
    created_at: "2029-12-30T00:00:00Z",
    ...overrides,
  };
}

describe("AppointmentCard as a client", () => {
  it("shows the time in the PROVIDER's zone, labelled", () => {
    renderApp(<AppointmentCard appointment={appointment()} viewerRole="client" now={NOW} />);
    expect(screen.getByText(/09:00/)).toBeInTheDocument();
    expect(screen.getByText("(Asia/Kolkata)")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Dr Rao" })).toBeInTheDocument();
  });

  it("asks for confirmation before cancelling, then cancels", async () => {
    const api = mockFetch({
      "POST /api/appointments/5/cancel/": { json: appointment({ status: "cancelled" }) },
      "GET /api/appointments/": { json: { count: 0, next: null, previous: null, results: [] } },
    });
    renderApp(<AppointmentCard appointment={appointment()} viewerRole="client" now={NOW} />);

    await userEvent.click(screen.getByRole("button", { name: "Cancel appointment" }));
    expect(api.count("POST /api/appointments/5/cancel/")).toBe(0); // nothing sent yet
    await userEvent.click(screen.getByRole("button", { name: "Yes, cancel it" }));
    await waitFor(() => expect(api.count("POST /api/appointments/5/cancel/")).toBe(1));
  });

  it("can back out of a cancellation without sending anything", async () => {
    const api = mockFetch({});
    renderApp(<AppointmentCard appointment={appointment()} viewerRole="client" now={NOW} />);
    await userEvent.click(screen.getByRole("button", { name: "Cancel appointment" }));
    await userEvent.click(screen.getByRole("button", { name: "Keep it" }));
    expect(api.fn).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Cancel appointment" })).toBeInTheDocument();
  });

  it("shows the server's reason when the cut-off has passed", async () => {
    mockFetch({
      "POST /api/appointments/5/cancel/": {
        status: 409,
        json: { detail: "Changes are not allowed within 4 hours of the start. Contact the provider.", code: "deadline_passed" },
      },
    });
    renderApp(<AppointmentCard appointment={appointment()} viewerRole="client" now={NOW} />);
    await userEvent.click(screen.getByRole("button", { name: "Cancel appointment" }));
    await userEvent.click(screen.getByRole("button", { name: "Yes, cancel it" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Changes are not allowed within 4 hours");
  });

  it("offers no actions on a cancelled appointment", () => {
    renderApp(<AppointmentCard appointment={appointment({ status: "cancelled" })} viewerRole="client" now={NOW} />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.getByText("Cancelled")).toBeInTheDocument();
  });

  it("never offers complete or no-show to a client, even after the start", () => {
    const later = new Date("2030-01-08T00:00:00Z");
    renderApp(<AppointmentCard appointment={appointment()} viewerRole="client" now={later} />);
    expect(screen.queryByRole("button", { name: /completed|no-show/i })).not.toBeInTheDocument();
  });
});

describe("AppointmentCard as a provider", () => {
  const provider = makeUser("provider");

  it("can complete or mark no-show only once the appointment has started", async () => {
    const api = mockFetch({
      "POST /api/appointments/5/complete/": { json: appointment({ status: "completed" }) },
      "GET /api/appointments/": { json: { count: 0, next: null, previous: null, results: [] } },
    });
    const started = new Date("2030-01-07T04:00:00Z");
    renderApp(<AppointmentCard appointment={appointment()} viewerRole="provider" now={started} />, { user: provider });

    expect(screen.queryByRole("button", { name: "Cancel appointment" })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Mark completed" }));
    await waitFor(() => expect(api.count("POST /api/appointments/5/complete/")).toBe(1));
  });

  it("sees the client's name, and cannot complete a future appointment", () => {
    renderApp(<AppointmentCard appointment={appointment()} viewerRole="provider" now={NOW} />, { user: provider });
    expect(screen.getByRole("heading", { name: "Asha Nair" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Mark completed" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cancel appointment" })).toBeInTheDocument();
  });
});
