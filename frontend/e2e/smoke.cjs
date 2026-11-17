/**
 * End-to-end smoke test: a real browser, the real React app, the real Django API.
 *
 * Needs: seeded backend running, frontend dev server running. Usage:
 *   node e2e/smoke.cjs [FRONTEND_URL]
 *
 * The browser is set to a time zone (Los Angeles) that is NOT the provider's (Kolkata) on purpose:
 * if any time on screen follows the browser instead of the provider, this fails.
 */
const { chromium } = require("playwright");
const assert = require("node:assert/strict");

const BASE = process.argv[2] ?? "http://127.0.0.1:5173";
const PASSWORD = "demo-pass-123";
const today = () => new Date().toISOString().slice(0, 10);
const plusDays = (n) => new Date(Date.now() + n * 86_400_000).toISOString().slice(0, 10);

async function signIn(page, email) {
  await page.goto(`${BASE}/login`);
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
}

async function step(name, fn) {
  try {
    await fn();
    console.log(`ok   ${name}`);
  } catch (error) {
    console.log(`FAIL ${name}\n     ${String(error.message).split("\n")[0]}`);
    process.exitCode = 1;
    throw error;
  }
}

(async () => {
  const browser = await chromium.launch();
  const context = await browser.newContext({ timezoneId: "America/Los_Angeles", viewport: { width: 1100, height: 800 } });
  const page = await context.newPage();
  const pageErrors = [];
  page.on("pageerror", (e) => pageErrors.push(e.message));
  page.on("console", (m) => m.type() === "error" && pageErrors.push(m.text()));

  try {
    await step("protected pages send anonymous visitors to the login page", async () => {
      await page.goto(`${BASE}/appointments`);
      await page.waitForURL("**/login");
    });

    await step("a wrong password shows the server's message", async () => {
      await page.getByLabel("Email").fill("asha@demo.test");
      await page.getByLabel("Password").fill("nope-nope-nope");
      await page.getByRole("button", { name: "Sign in" }).click();
      await page.getByRole("alert").waitFor();
      assert.match(await page.getByRole("alert").innerText(), /No active account/);
    });

    await step("client signs in and lands on the provider list", async () => {
      await signIn(page, "asha@demo.test");
      await page.waitForURL("**/providers");
      await page.getByRole("heading", { name: "Find a provider" }).waitFor();
    });

    await step("filtering by specialty narrows the list", async () => {
      await page.getByLabel("Specialty").fill("Dentistry");
      await page.getByRole("button", { name: "Filter" }).click();
      await page.getByRole("heading", { name: "Dr Hughes" }).waitFor();
      assert.equal(await page.getByRole("heading", { name: "Dr Rao" }).count(), 0);
      await page.getByLabel("Specialty").fill("");
      await page.getByRole("button", { name: "Filter" }).click();
      await page.getByRole("heading", { name: "Dr Rao" }).waitFor();
    });

    let bookedLabel = "";
    await step("slot times follow the PROVIDER's zone, not the browser's, and booking works", async () => {
      await page.getByRole("article").filter({ hasText: "Dr Rao" }).getByRole("link", { name: "View and book" }).click();
      await page.getByRole("heading", { name: "Dr Rao", level: 1 }).waitFor();
      const slots = page.getByRole("list", { name: "Free slots" }).getByRole("button");
      let found = false;
      for (let i = 1; i <= 14 && !found; i++) {
        await page.locator('input[type="date"]').fill(plusDays(i));
        await page.waitForTimeout(400);
        found = (await slots.count()) > 0;
      }
      assert.ok(found, "no free slot found in 14 days");
      const labels = await slots.allInnerTexts();
      for (const text of labels) {
        const [h] = text.split(":").map(Number);
        const inMorning = h >= 9 && h < 12;
        const inAfternoon = h >= 14 && h < 17;
        assert.ok(inMorning || inAfternoon, `slot ${text} is outside Dr Rao's hours (09-12 and 14-17 Kolkata); the browser zone leaked in`);
      }
      bookedLabel = labels[0];
      await slots.first().click();
      await page.getByLabel(/Note for the provider/).fill("e2e booking");
      await page.getByRole("button", { name: /^Book / }).click();
      await page.getByRole("status").waitFor();
      assert.match(await page.getByRole("status").innerText(), new RegExp(`Booked for .*${bookedLabel}`));
    });

    await step("the booking shows up in My appointments with the provider's time", async () => {
      await page.getByRole("link", { name: "My appointments" }).first().click();
      const card = page.getByRole("article").filter({ hasText: "e2e booking" });
      await card.waitFor();
      assert.match(await card.innerText(), new RegExp(`${bookedLabel}[\\s\\S]*Asia/Kolkata`));
    });

    await step("rescheduling moves the same appointment to another slot", async () => {
      const card = page.getByRole("article").filter({ hasText: "e2e booking" });
      await card.getByRole("button", { name: "Reschedule" }).click();
      const slots = card.getByRole("list", { name: "Free slots" }).getByRole("button");
      let found = false;
      for (let i = 1; i <= 14 && !found; i++) {
        await card.locator('input[type="date"]').fill(plusDays(i));
        await page.waitForTimeout(400);
        found = (await slots.count()) > 0;
      }
      assert.ok(found);
      await slots.last().click();
      await card.getByRole("button", { name: "Move appointment" }).click();
      await card.getByRole("button", { name: "Reschedule" }).waitFor();
    });

    await step("cancelling needs a confirmation, then the status changes", async () => {
      const card = page.getByRole("article").filter({ hasText: "e2e booking" });
      await card.getByRole("button", { name: "Cancel appointment" }).click();
      await card.getByRole("button", { name: "Yes, cancel it" }).click();
      await card.getByText("Cancelled").waitFor();
      assert.equal(await card.getByRole("button").count(), 0);
    });

    await step("a client cannot open provider-only pages", async () => {
      await page.goto(`${BASE}/schedule`);
      await page.waitForURL("**/providers");
    });

    await step("signing out and reloading keeps the session closed", async () => {
      await page.getByRole("button", { name: "Sign out" }).click();
      await page.reload();
      await page.goto(`${BASE}/appointments`);
      await page.waitForURL("**/login");
    });

    await step("a provider signs in and sees a day's appointments (days in THEIR zone)", async () => {
      await signIn(page, "dr.rao@demo.test");
      await page.waitForURL("**/dashboard");
      await page.getByRole("heading", { name: "Dashboard" }).waitFor();
      let found = false;
      for (let i = 0; i < 10 && !found; i++) {
        await page.waitForTimeout(400);
        found = (await page.getByRole("article").count()) > 0;
        if (!found) await page.getByRole("button", { name: "Next day →" }).click();
      }
      assert.ok(found, "no appointment found on the next 10 days of the dashboard");
    });

    await step("a provider changes booking rules and they persist after a reload", async () => {
      await page.getByRole("link", { name: "Schedule" }).first().click();
      const field = page.getByLabel(/Clients may cancel until/);
      await field.fill("12");
      await page.getByRole("button", { name: "Save settings" }).click();
      await page.getByText("Saved.").waitFor();
      await page.reload();
      assert.equal(await page.getByLabel(/Clients may cancel until/).inputValue(), "12");
    });

    await step("invalid settings are rejected with the server's message", async () => {
      await page.getByLabel(/Time zone/).fill("Mars/Olympus");
      await page.getByRole("button", { name: "Save settings" }).click();
      await page.locator(".field-error").first().waitFor();
      await page.reload();
    });

    await step("working hours can be added and removed", async () => {
      const rules = page.getByRole("region", { name: "Weekly working hours" });
      await rules.locator("select").selectOption("5");
      await rules.getByLabel("From").fill("10:00");
      await rules.getByLabel("To").fill("11:00");
      await rules.getByRole("button", { name: "Add hours" }).click();
      await rules.getByText("Saturday 10:00–11:00").waitFor();
      await rules.getByRole("button", { name: /Remove Saturday 10:00/ }).click();
      await rules.getByText("Saturday 10:00–11:00").waitFor({ state: "detached" });
    });

    await step("no uncaught errors, and only the two failed requests this script caused on purpose", async () => {
      const failedRequests = pageErrors.filter((m) => m.startsWith("Failed to load resource"));
      const unexpected = pageErrors.filter((m) => !m.startsWith("Failed to load resource"));
      assert.deepEqual(unexpected, []);
      // The wrong password (401) and the invalid time zone (400). A third one would be a real bug.
      assert.equal(failedRequests.length, 2, `unexpected failed requests: ${JSON.stringify(failedRequests)}`);
    });
  } finally {
    await page.screenshot({ path: process.env.SHOT ?? "/tmp/e2e-last.png", fullPage: true });
    await browser.close();
  }
})().catch((error) => {
  console.error(error.message.split("\n")[0]);
  process.exit(1);
});
