import { useInfiniteQuery } from "@tanstack/react-query";
import * as api from "../api/endpoints";
import type { AppointmentFilters, Role } from "../api/types";
import { AppointmentCard } from "./AppointmentCard";
import { ErrorBanner } from "./ErrorBanner";

interface Props {
  filters: AppointmentFilters;
  viewerRole: Role;
  emptyText: string;
}

/** Appointments matching `filters`, 20 at a time, with a "Load more" button. */
export function AppointmentList({ filters, viewerRole, emptyText }: Props) {
  const query = useInfiniteQuery({
    queryKey: ["appointments", filters],
    queryFn: ({ pageParam }) => api.listAppointments(pageParam, filters),
    initialPageParam: 1,
    getNextPageParam: (last, pages) => (last.next ? pages.length + 1 : undefined),
  });

  if (query.isPending) return <p>Loading…</p>;
  if (query.error) return <ErrorBanner error={query.error} />;
  const items = query.data.pages.flatMap((page) => page.results);
  if (items.length === 0) return <p>{emptyText}</p>;

  return (
    <div className="stack">
      {items.map((appointment) => (
        <AppointmentCard key={appointment.id} appointment={appointment} viewerRole={viewerRole} />
      ))}
      {query.hasNextPage && (
        <button type="button" className="secondary" disabled={query.isFetchingNextPage} onClick={() => void query.fetchNextPage()}>
          {query.isFetchingNextPage ? "Loading…" : "Load more"}
        </button>
      )}
    </div>
  );
}
