import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, clearTokens, request, setSessionExpiredHandler, storeTokens } from "./client";

function reply(status: number, body: unknown) {
  return new Response(status === 204 ? null : JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

beforeEach(() => {
  clearTokens();
  setSessionExpiredHandler(null);
});
afterEach(() => vi.unstubAllGlobals());

describe("request", () => {
  it("sends the access token as a Bearer header", async () => {
    storeTokens("abc", "refresh-1");
    const fetchMock = vi.fn().mockResolvedValue(reply(200, { ok: true }));
    vi.stubGlobal("fetch", fetchMock);
    await request("/things/");
    const headers = fetchMock.mock.calls[0]?.[1]?.headers as Record<string, string>;
    expect(headers.Authorization).toBe("Bearer abc");
  });

  it("refreshes an expired token once and retries the request", async () => {
    storeTokens("old", "refresh-1");
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(reply(401, { detail: "expired" }))
      .mockResolvedValueOnce(reply(200, { access: "new" }))
      .mockResolvedValueOnce(reply(200, { value: 42 }));
    vi.stubGlobal("fetch", fetchMock);

    expect(await request<{ value: number }>("/things/")).toEqual({ value: 42 });
    expect(fetchMock.mock.calls.map((c) => String(c[0]))).toEqual(["/api/things/", "/api/auth/token/refresh/", "/api/things/"]);
    const retryHeaders = fetchMock.mock.calls[2]?.[1]?.headers as Record<string, string>;
    expect(retryHeaders.Authorization).toBe("Bearer new");
  });

  it("shares one refresh between requests that expire together", async () => {
    storeTokens("old", "refresh-1");
    let refreshCalls = 0;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("token/refresh")) {
        refreshCalls++;
        return reply(200, { access: "new" });
      }
      const auth = (init?.headers as Record<string, string>).Authorization;
      return auth === "Bearer new" ? reply(200, { ok: true }) : reply(401, { detail: "expired" });
    });
    vi.stubGlobal("fetch", fetchMock);

    await Promise.all([request("/a/"), request("/b/"), request("/c/")]);
    expect(refreshCalls).toBe(1);
  });

  it("signs the user out when the refresh token is no longer valid", async () => {
    storeTokens("old", "refresh-1");
    const expired = vi.fn();
    setSessionExpiredHandler(expired);
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => (String(input).includes("token/refresh") ? reply(401, { detail: "bad" }) : reply(401, { detail: "expired" }))),
    );

    await expect(request("/things/")).rejects.toMatchObject({ status: 401 });
    expect(expired).toHaveBeenCalledTimes(1);
    expect(localStorage.getItem("sk.refresh")).toBeNull();
  });

  it("does not try to refresh when logging in with a wrong password", async () => {
    storeTokens("old", "refresh-1");
    const fetchMock = vi.fn().mockResolvedValue(reply(401, { detail: "No active account found", code: "no_active_account" }));
    vi.stubGlobal("fetch", fetchMock);
    await expect(request("/auth/token/", { method: "POST", body: {}, auth: false })).rejects.toMatchObject({
      status: 401,
      code: "no_active_account",
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("exposes the machine-readable code and the message of a 409", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(reply(409, { detail: "That slot was just taken.", code: "slot_unavailable" })));
    const error = await request("/appointments/", { method: "POST", body: {} }).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 409, code: "slot_unavailable", message: "That slot was just taken." });
  });

  it("collects per-field validation errors from a 400", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(reply(400, { starts_at: ["Not offered."], notes: ["Too long."] })));
    const error = (await request("/appointments/", { method: "POST", body: {} }).catch((e: unknown) => e)) as ApiError;
    expect(error.fields).toEqual({ starts_at: ["Not offered."], notes: ["Too long."] });
    expect(error.message).toBe("Not offered.");
  });

  it("turns a network failure into a readable ApiError", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    await expect(request("/things/")).rejects.toMatchObject({ status: 0, code: "network_error" });
  });

  it("returns undefined for 204 No Content and builds the query string", async () => {
    const fetchMock = vi.fn().mockResolvedValue(reply(204, null));
    vi.stubGlobal("fetch", fetchMock);
    expect(await request("/things/1/", { method: "DELETE", query: { a: 1, b: undefined, c: "x y" } })).toBeUndefined();
    expect(String(fetchMock.mock.calls[0]?.[0])).toBe("/api/things/1/?a=1&c=x+y");
  });
});
