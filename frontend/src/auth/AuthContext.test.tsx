import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { clearTokens } from "../api/client";
import { LoginPage } from "../pages/LoginPage";
import { mockFetch } from "../test/utils";
import { AuthProvider, useAuth } from "./AuthContext";

const USER = { id: 3, email: "asha@demo.test", full_name: "Asha Nair", phone: "", role: "client" };

beforeEach(() => clearTokens());
afterEach(() => vi.unstubAllGlobals());

function Probe() {
  const { status, user, logout } = useAuth();
  return (
    <div>
      <p data-testid="status">{status}</p>
      <p data-testid="name">{user?.full_name ?? "nobody"}</p>
      <button type="button" onClick={logout}>
        sign out
      </button>
    </div>
  );
}

function mount(ui = <Probe />, queryClient = new QueryClient()) {
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/login"]}>
        <AuthProvider>
          <Routes>
            <Route path="/login" element={ui} />
            <Route path="/providers" element={<p>client home</p>} />
          </Routes>
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return queryClient;
}

describe("AuthProvider", () => {
  it("starts signed out when there is no stored session", () => {
    const api = mockFetch({});
    mount();
    expect(screen.getByTestId("status")).toHaveTextContent("anonymous");
    expect(api.fn).not.toHaveBeenCalled();
  });

  it("restores a session from the stored refresh token", async () => {
    localStorage.setItem("sk.refresh", "stored-refresh");
    mockFetch({
      "POST /api/auth/token/refresh/": { json: { access: "fresh-access" } },
      "GET /api/auth/me/": { json: USER },
    });
    mount();
    expect(screen.getByTestId("status")).toHaveTextContent("loading");
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("authenticated"));
    expect(screen.getByTestId("name")).toHaveTextContent("Asha Nair");
  });

  it("falls back to signed out, and forgets the token, when the stored session is dead", async () => {
    localStorage.setItem("sk.refresh", "revoked");
    mockFetch({ "POST /api/auth/token/refresh/": { status: 401, json: { detail: "Token is invalid", code: "token_not_valid" } } });
    mount();
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("anonymous"));
    expect(localStorage.getItem("sk.refresh")).toBeNull();
  });

  it("signing out clears the stored token AND every cached query", async () => {
    localStorage.setItem("sk.refresh", "stored-refresh");
    mockFetch({
      "POST /api/auth/token/refresh/": { json: { access: "fresh-access" } },
      "GET /api/auth/me/": { json: USER },
    });
    const queryClient = mount();
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("authenticated"));
    queryClient.setQueryData(["appointments", {}], { private: "data of the previous person" });

    await userEvent.click(screen.getByRole("button", { name: "sign out" }));

    expect(screen.getByTestId("status")).toHaveTextContent("anonymous");
    expect(localStorage.getItem("sk.refresh")).toBeNull();
    expect(queryClient.getQueryData(["appointments", {}])).toBeUndefined();
  });
});

describe("LoginPage", () => {
  it("signs in, remembers the session and goes to the role's home page", async () => {
    mockFetch({
      "POST /api/auth/token/": { json: { access: "a", refresh: "r" } },
      "GET /api/auth/me/": { json: USER },
    });
    mount(<LoginPage />);
    await userEvent.type(screen.getByLabelText("Email"), "asha@demo.test");
    await userEvent.type(screen.getByLabelText("Password"), "demo-pass-123");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByText("client home")).toBeInTheDocument();
    expect(localStorage.getItem("sk.refresh")).toBe("r");
  });

  it("shows the server's message for a wrong password and stores nothing", async () => {
    mockFetch({
      "POST /api/auth/token/": { status: 401, json: { detail: "No active account found with the given credentials", code: "no_active_account" } },
    });
    mount(<LoginPage />);
    await userEvent.type(screen.getByLabelText("Email"), "asha@demo.test");
    await userEvent.type(screen.getByLabelText("Password"), "wrong");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("No active account found");
    expect(localStorage.getItem("sk.refresh")).toBeNull();
    expect(screen.getByRole("button", { name: "Sign in" })).toBeEnabled();
  });
});
