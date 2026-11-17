import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";
import type { Role, User } from "../api/types";
import { AuthContext, type AuthValue } from "../auth/AuthContext";

export function makeUser(role: Role = "client"): User {
  return { id: 1, email: `${role}@example.com`, full_name: "Test Person", phone: "", role };
}

export function renderApp(ui: ReactElement, options: { route?: string; user?: User | null } = {}) {
  const { route = "/", user = makeUser() } = options;
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  const auth: AuthValue = {
    status: user ? "authenticated" : "anonymous",
    user,
    login: vi.fn(),
    register: vi.fn(),
    logout: vi.fn(),
  };
  return render(
    <QueryClientProvider client={queryClient}>
      <AuthContext.Provider value={auth}>
        <MemoryRouter initialEntries={[route]}>{ui}</MemoryRouter>
      </AuthContext.Provider>
    </QueryClientProvider>,
  );
}

export interface Reply {
  status?: number;
  json?: unknown;
}
export type Handler = (request: { url: URL; body: unknown }) => Reply;

/**
 * Replace fetch with a router keyed by "METHOD /path". An unexpected request FAILS the test, so a
 * page that calls an endpoint nobody planned for cannot pass by accident.
 */
export function mockFetch(routes: Record<string, Handler | Reply>) {
  const calls: { key: string; body: unknown }[] = [];
  const fn = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input), "http://localhost");
    const method = init?.method ?? "GET";
    const key = `${method} ${url.pathname}`;
    const body = init?.body ? JSON.parse(String(init.body)) : undefined;
    calls.push({ key, body });
    const route = routes[key];
    if (!route) throw new Error(`Unexpected request: ${key}`);
    const reply = typeof route === "function" ? route({ url, body }) : route;
    return new Response(reply.status === 204 ? null : JSON.stringify(reply.json ?? {}), {
      status: reply.status ?? 200,
      headers: { "Content-Type": "application/json" },
    });
  });
  vi.stubGlobal("fetch", fn);
  return { fn, calls, count: (key: string) => calls.filter((c) => c.key === key).length };
}
