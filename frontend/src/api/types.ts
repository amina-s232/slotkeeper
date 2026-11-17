export type Role = "admin" | "provider" | "client";

export interface User {
  id: number;
  email: string;
  full_name: string;
  phone: string;
  role: Role;
}

export interface Provider {
  id: number;
  display_name: string;
  specialty: string;
  bio: string;
  timezone: string;
  slot_minutes: number;
  booking_window_days: number;
  min_notice_hours: number;
  cancel_cutoff_hours: number;
}

export interface OwnProvider extends Provider {
  is_active: boolean;
}

export interface Slot {
  starts_at: string;
  ends_at: string;
}

export type AppointmentStatus = "booked" | "cancelled" | "completed" | "no_show";

export interface Appointment {
  id: number;
  provider: number;
  provider_name: string;
  provider_timezone: string;
  client: number;
  client_name: string;
  starts_at: string;
  ends_at: string;
  status: AppointmentStatus;
  notes: string;
  cancelled_at: string | null;
  created_at: string;
}

export interface AvailabilityRule {
  id: number;
  weekday: number;
  start_time: string;
  end_time: string;
  valid_from: string | null;
  valid_to: string | null;
}

export interface TimeOff {
  id: number;
  starts_at: string;
  ends_at: string;
  reason: string;
}

export interface Page<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface AppointmentFilters {
  status?: AppointmentStatus;
  starts_after?: string;
  starts_before?: string;
}
