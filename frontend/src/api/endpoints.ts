import { request } from "./client";
import type {
  Appointment,
  AppointmentFilters,
  AvailabilityRule,
  OwnProvider,
  Page,
  Provider,
  Slot,
  TimeOff,
  User,
} from "./types";

export interface Tokens {
  access: string;
  refresh: string;
}

export interface RegisterInput {
  email: string;
  full_name: string;
  phone: string;
  password: string;
}

// ---- auth -------------------------------------------------------------------------------
export const login = (email: string, password: string) =>
  request<Tokens>("/auth/token/", { method: "POST", body: { email, password }, auth: false });
export const register = (input: RegisterInput) =>
  request<User>("/auth/register/", { method: "POST", body: input, auth: false });
export const me = () => request<User>("/auth/me/");

// ---- directory and booking --------------------------------------------------------------
export const listProviders = (page: number, specialty?: string) =>
  request<Page<Provider>>("/providers/", { query: { page, specialty } });
export const getProvider = (id: number) => request<Provider>(`/providers/${id}/`);
export const getSlots = (providerId: number, date: string) =>
  request<Slot[]>(`/providers/${providerId}/slots/`, { query: { date } });

export const bookAppointment = (input: { provider: number; starts_at: string; notes: string }) =>
  request<Appointment>("/appointments/", { method: "POST", body: input });

export const listAppointments = (page: number, filters: AppointmentFilters) =>
  request<Page<Appointment>>("/appointments/", { query: { page, ...filters } });
export const cancelAppointment = (id: number) =>
  request<Appointment>(`/appointments/${id}/cancel/`, { method: "POST" });
export const rescheduleAppointment = (id: number, starts_at: string) =>
  request<Appointment>(`/appointments/${id}/reschedule/`, { method: "POST", body: { starts_at } });
export const completeAppointment = (id: number) =>
  request<Appointment>(`/appointments/${id}/complete/`, { method: "POST" });
export const markNoShow = (id: number) =>
  request<Appointment>(`/appointments/${id}/no-show/`, { method: "POST" });

// ---- a provider's own schedule ----------------------------------------------------------
async function fetchAll<T>(path: string): Promise<T[]> {
  const all: T[] = [];
  for (let page = 1; ; page++) {
    const data = await request<Page<T>>(path, { query: { page } });
    all.push(...data.results);
    if (!data.next) return all;
  }
}

export const getOwnProvider = () => request<OwnProvider>("/me/provider/");
export const updateOwnProvider = (patch: Partial<Omit<OwnProvider, "id">>) =>
  request<OwnProvider>("/me/provider/", { method: "PATCH", body: patch });

export type RuleInput = Pick<AvailabilityRule, "weekday" | "start_time" | "end_time">;
export const listRules = () => fetchAll<AvailabilityRule>("/me/availability-rules/");
export const createRule = (input: RuleInput) =>
  request<AvailabilityRule>("/me/availability-rules/", { method: "POST", body: input });
export const deleteRule = (id: number) =>
  request<void>(`/me/availability-rules/${id}/`, { method: "DELETE" });

export type TimeOffInput = Pick<TimeOff, "starts_at" | "ends_at" | "reason">;
export const listTimeOff = () => fetchAll<TimeOff>("/me/time-off/");
export const createTimeOff = (input: TimeOffInput) =>
  request<TimeOff>("/me/time-off/", { method: "POST", body: input });
export const deleteTimeOff = (id: number) => request<void>(`/me/time-off/${id}/`, { method: "DELETE" });
