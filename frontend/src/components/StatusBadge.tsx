import type { AppointmentStatus } from "../api/types";

const LABELS: Record<AppointmentStatus, string> = {
  booked: "Booked",
  cancelled: "Cancelled",
  completed: "Completed",
  no_show: "No show",
};

export function StatusBadge({ status }: { status: AppointmentStatus }) {
  return <span className={`badge badge-${status}`}>{LABELS[status]}</span>;
}
