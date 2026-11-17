import { screen } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { makeUser, renderApp } from "../test/utils";
import { RequireRole } from "./RequireRole";

function app(user: ReturnType<typeof makeUser> | null, route: string) {
  return renderApp(
    <Routes>
      <Route path="/login" element={<p>login page</p>} />
      <Route path="/dashboard" element={<p>provider home</p>} />
      <Route path="/providers" element={<p>client home</p>} />
      <Route
        path="/schedule"
        element={
          <RequireRole roles={["provider"]}>
            <p>secret schedule</p>
          </RequireRole>
        }
      />
    </Routes>,
    { route, user },
  );
}

describe("RequireRole", () => {
  it("sends anonymous visitors to the login page", () => {
    app(null, "/schedule");
    expect(screen.getByText("login page")).toBeInTheDocument();
    expect(screen.queryByText("secret schedule")).not.toBeInTheDocument();
  });

  it("lets the right role in", () => {
    app(makeUser("provider"), "/schedule");
    expect(screen.getByText("secret schedule")).toBeInTheDocument();
  });

  it("sends the wrong role to its own home, not to a dead end", () => {
    app(makeUser("client"), "/schedule");
    expect(screen.getByText("client home")).toBeInTheDocument();
    expect(screen.queryByText("secret schedule")).not.toBeInTheDocument();
  });
});
