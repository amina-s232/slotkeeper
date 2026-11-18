import { useInfiniteQuery } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import * as api from "../api/endpoints";
import { ErrorBanner } from "../components/ErrorBanner";
import { Avatar } from "../components/Avatar";


export function ProvidersPage() {
  const [draft, setDraft] = useState("");
  const [specialty, setSpecialty] = useState("");
  const query = useInfiniteQuery({
    queryKey: ["providers", specialty],
    queryFn: ({ pageParam }) => api.listProviders(pageParam, specialty || undefined),
    initialPageParam: 1,
    getNextPageParam: (last, pages) => (last.next ? pages.length + 1 : undefined),
  });

  const apply = (e: FormEvent) => {
    e.preventDefault();
    setSpecialty(draft.trim());
  };
  const providers = query.data?.pages.flatMap((p) => p.results) ?? [];

  return (
    <section>
      <h1>Find a provider</h1>
      <form onSubmit={apply} className="inline-form" role="search">
        <label>
          Specialty
          <input value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="e.g. Dentistry" />
        </label>
        <button type="submit">Filter</button>
      </form>

      {query.isPending && <p>Loading…</p>}
      <ErrorBanner error={query.error} />
      {query.data && providers.length === 0 && <p>No providers match.</p>}
      <div className="grid">
        {providers.map((p) => (
          <article key={p.id} className="card">
            <div className="person">
              <Avatar name={p.display_name} />
              <div>
                <h3>{p.display_name}</h3>
                <p className="muted">{p.specialty || "General"}</p>
              </div>
            </div>

            {p.bio && <p>{p.bio}</p>}
            <p className="muted">
              {p.slot_minutes}-minute visits · {p.timezone}
            </p>
            <Link to={`/providers/${p.id}`} className="button">
              View and book
            </Link>
          </article>
        ))}
      </div>
      {query.hasNextPage && (
        <button type="button" className="secondary" onClick={() => void query.fetchNextPage()} disabled={query.isFetchingNextPage}>
          Load more
        </button>
      )}
    </section>
  );
}
