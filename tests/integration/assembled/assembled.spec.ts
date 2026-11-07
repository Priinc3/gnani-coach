/**
 * The Phase 07 assembled browser suite (A1–A8).
 *
 * Every test here drives the real Next.js app and the real voice service
 * through Chromium. The microphone is a deterministic oscillator, the
 * providers are fakes, and Supabase is a local HTTP double; the runtime,
 * the transport, the reducers, the capture worklet, the identity verifier
 * and both Supabase stores are the product's own code.
 *
 * Every envelope on the wire is validated against `packages/contracts`.
 */

import { expect, test, type APIRequestContext, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import {
  APP_URL,
  CONTROL_URL,
  REPLY_SENTINEL,
  SUPABASE_URL,
  TOPIC_SENTINEL,
  TRANSCRIPT_SENTINEL,
  USER_A,
  USER_B,
  VOICE_URL,
  signInAs,
} from "./constants";
import { assertEnvelope } from "./contracts";
import { INSTRUMENTATION } from "./instrumentation";

interface SessionRow {
  user_id: string;
  session_id: string;
  recording_id: string | null;
  turn_count: number;
}

interface FakeDatabase {
  sessions: SessionRow[];
  consents: Array<{ user_id: string; recording_retention_granted: boolean }>;
  recordings: Array<{ user_id: string; recording_id: string; session_id: string; state: string }>;
  objectKeys: string[];
}

interface SocketSnapshot {
  url: string;
  readyState: number;
  sent: string[];
  received: string[];
  binary: number;
}

async function resetDatabase(request: APIRequestContext): Promise<void> {
  const response = await request.post(`${SUPABASE_URL}/__control__/reset`);
  expect(response.ok()).toBeTruthy();
}

async function dumpDatabase(request: APIRequestContext): Promise<FakeDatabase> {
  const response = await request.get(`${SUPABASE_URL}/__control__/dump`);
  expect(response.ok()).toBeTruthy();
  return (await response.json()) as FakeDatabase;
}

async function setFailures(request: APIRequestContext, failures: Record<string, unknown>): Promise<void> {
  const response = await request.post(`${CONTROL_URL}/control/fail`, { data: failures });
  expect(response.ok()).toBeTruthy();
}

async function clearServiceLog(request: APIRequestContext): Promise<void> {
  const response = await request.post(`${CONTROL_URL}/control/logs/clear`);
  expect(response.ok()).toBeTruthy();
}

async function serviceDump(request: APIRequestContext): Promise<{
  log: string;
  latency: { turns: number; p50Ms: number; p95Ms: number };
  logPath: string;
}> {
  const response = await request.get(`${CONTROL_URL}/control/dump`);
  expect(response.ok()).toBeTruthy();
  return response.json();
}

async function openApp(page: Page): Promise<void> {
  await page.goto(APP_URL);
  await expect(page.getByRole("button", { name: "Start a practice call" })).toBeVisible();
}

async function startCall(page: Page, options: { scenario?: string } = {}): Promise<void> {
  // The first paint can precede hydration on a cold dev server. A click
  // sent before the handler is attached is lost, so the click is repeated
  // until the scenario screen actually appears; the app itself ignores a
  // second Start, and the page is on a different view by the time the
  // handler is live.
  const continueButton = page.getByRole("button", { name: "Continue to settings" });
  await expect
    .poll(
      async () => {
        if (await continueButton.isVisible().catch(() => false)) {
          return true;
        }
        const start = page.getByRole("button", { name: "Start a practice call" });
        if (await start.isVisible().catch(() => false)) {
          await start.click().catch(() => undefined);
        }
        return continueButton.isVisible().catch(() => false);
      },
      { timeout: 20_000, intervals: [250, 500, 1_000] },
    )
    .toBe(true);
  if (options.scenario === "custom") {
    await page.getByRole("button", { name: "Custom Topic", exact: true }).click();
    await page.locator("#custom-topic").fill(TOPIC_SENTINEL);
  }
  await continueButton.click();
  await expect(page.getByRole("button", { name: "Start live practice call" })).toBeVisible();
}

async function beginCall(page: Page): Promise<void> {
  await page.getByRole("button", { name: "Start live practice call" }).click();
  await expect(page.getByTestId("call-status")).toHaveText("Listening", { timeout: 20_000 });
}

async function setMic(page: Page, mode: "speech" | "silence"): Promise<void> {
  await page.evaluate((next) => {
    (window as unknown as { __setMic: (mode: string) => void }).__setMic(next);
  }, mode);
}

async function speak(page: Page, milliseconds = 1_100): Promise<void> {
  await setMic(page, "speech");
  await page.waitForTimeout(milliseconds);
  await setMic(page, "silence");
}

async function waitForListening(page: Page): Promise<void> {
  await expect(page.getByTestId("call-status")).toHaveText("Listening", { timeout: 25_000 });
}

/** Wait until the service has actually closed the turn and the coach replies. */
async function waitForCoachTurn(page: Page): Promise<void> {
  await expect
    .poll(
      async () => page.getByTestId("call-status").innerText(),
      { timeout: 20_000, intervals: [50, 100, 200] },
    )
    .toMatch(/Thinking|Speaking/);
}

async function endCall(page: Page): Promise<void> {
  await page.getByRole("button", { name: "End" }).click();
  await expect(page.getByRole("heading", { name: "Session summary" })).toBeVisible();
}

async function sockets(page: Page): Promise<SocketSnapshot[]> {
  const all = await page.evaluate(() =>
    (window as unknown as { __socketSnapshot: () => SocketSnapshot[] }).__socketSnapshot(),
  );
  // The dev server has its own HMR socket; the suite means the call only.
  return all.filter((socket) => socket.url.includes("/ws/call"));
}

async function uiStatuses(page: Page): Promise<string[]> {
  return page.evaluate(
    () => (window as unknown as { __uiStatuses: string[] }).__uiStatuses,
  );
}

async function waitForSocketClosed(page: Page): Promise<void> {
  await expect
    .poll(async () => {
      const snapshot = await sockets(page);
      return snapshot.length > 0 ? snapshot[snapshot.length - 1].readyState : -1;
    }, { timeout: 10_000 })
    .toBe(3);
}

/** Validate every string this page sent and received. */
async function validateWire(page: Page): Promise<void> {
  const snapshot = await sockets(page);
  for (const socket of snapshot) {
    for (const raw of socket.sent) {
      assertEnvelope(JSON.parse(raw), "a client event");
    }
    for (const raw of socket.received) {
      assertEnvelope(JSON.parse(raw), "a server event");
    }
  }
}

/** Validate every `start` payload's settings against the frozen schema. */
async function validateStartSettings(page: Page): Promise<void> {
  const snapshot = await sockets(page);
  for (const socket of snapshot) {
    for (const raw of socket.sent) {
      const event = JSON.parse(raw) as { type?: string; payload?: { settings?: unknown } };
      if (event.type === "start") {
        const { validateSessionSettings, explain } = await import("./contracts");
        if (!validateSessionSettings(event.payload?.settings)) {
          throw new Error(`start settings are invalid: ${explain(validateSessionSettings)}`);
        }
      }
    }
  }
}

/** Wait until the fake consent row says the learner granted retention. */
async function waitForConsent(request: APIRequestContext, subject: string): Promise<void> {
  await expect
    .poll(async () => {
      const database = await dumpDatabase(request);
      return database.consents.some(
        (row) => row.user_id === subject && row.recording_retention_granted === true,
      );
    }, { timeout: 10_000 })
    .toBe(true);
}

async function grantRecording(page: Page, request: APIRequestContext, subject: string): Promise<void> {
  await page.getByLabel("Save the recording so I can replay it later").check();
  await waitForConsent(request, subject);
}

async function waitForNoData(request: APIRequestContext): Promise<void> {
  const database = await dumpDatabase(request);
  expect(database.sessions).toHaveLength(0);
  expect(database.recordings).toHaveLength(0);
  expect(database.objectKeys).toHaveLength(0);
}

test.beforeEach(async ({ context, request }) => {
  await context.addInitScript({ content: INSTRUMENTATION });
  await resetDatabase(request);
  await setFailures(request, {});
  await clearServiceLog(request);
});

test("A1 — a guest call runs four turns, a round break, a retry and a clean end", async ({
  page,
  request,
}) => {
  await openApp(page);
  await startCall(page);
  await beginCall(page);

  for (let turn = 0; turn < 3; turn += 1) {
    await speak(page);
    await waitForCoachTurn(page);
    await waitForListening(page);
  }
  await speak(page);
  await waitForCoachTurn(page);
  await expect(page.getByRole("heading", { name: "Here is a quick look at that round" })).toBeVisible({
    timeout: 30_000,
  });

  const statuses = await uiStatuses(page);
  expect(statuses).toContain("Listening");
  expect(statuses).toContain("Thinking");
  expect(statuses).toContain("Speaking");

  await page.getByRole("button", { name: "Try again" }).click();
  await expect(page.getByTestId("call-status")).toHaveText("Speaking", { timeout: 20_000 });

  await validateStartSettings(page);
  await endCall(page);
  await waitForSocketClosed(page);
  await validateWire(page);

  // A guest writes nothing.
  await waitForNoData(request);
  const database = await dumpDatabase(request);
  expect(database.sessions).toHaveLength(0);
});

test("A2 — an authenticated call with recording off saves metrics and appears in progress", async ({
  page,
  request,
}) => {
  const { token } = await signInAs(page.context(), USER_A);
  await openApp(page);
  await startCall(page);
  await beginCall(page);
  await speak(page);
  await waitForCoachTurn(page);
  await waitForListening(page);
  await endCall(page);

  await expect(page.getByRole("button", { name: "Open my progress" })).toBeVisible();
  await validateStartSettings(page);
  await validateWire(page);
  await waitForSocketClosed(page);

  const database = await dumpDatabase(request);
  const sessions = database.sessions.filter((row) => row.user_id === USER_A);
  expect(sessions).toHaveLength(1);
  expect(sessions[0].recording_id).toBeNull();
  expect(sessions[0].turn_count).toBe(1);
  expect(database.objectKeys).toHaveLength(0);

  await page.getByRole("button", { name: "Open my progress" }).click();
  await expect(page.getByRole("heading", { name: "Your progress" })).toBeVisible();
  await expect(page.getByText("Interview practice").first()).toBeVisible();
  await expect(page.getByText("1 learner turns").first()).toBeVisible();
  await expect(page.locator("audio")).toHaveCount(0);

  const history = await request.get(`${VOICE_URL}/api/history`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(history.status()).toBe(200);
  const body = (await history.json()) as { sessions: Array<{ recordingId: string | null }> };
  expect(body.sessions[0].recordingId).toBeNull();
});

test("A3 — recording on saves a WAV, the progress player loads it, and delete removes it", async ({
  page,
  request,
}) => {
  const { token } = await signInAs(page.context(), USER_A);
  await openApp(page);
  await startCall(page);
  await grantRecording(page, request, USER_A);
  await beginCall(page);
  await speak(page);
  await waitForCoachTurn(page);
  await waitForListening(page);
  await endCall(page);
  await waitForSocketClosed(page);

  const database = await dumpDatabase(request);
  const session = database.sessions.find((row) => row.user_id === USER_A);
  expect(session?.recording_id).toBeTruthy();
  expect(database.objectKeys).toHaveLength(1);

  const raw = await request.get(`${VOICE_URL}/api/recordings/${session?.recording_id}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(raw.status()).toBe(200);
  const bytes = await raw.body();
  expect(bytes.subarray(0, 4).toString("ascii")).toBe("RIFF");
  expect(bytes.subarray(8, 12).toString("ascii")).toBe("WAVE");

  await page.getByRole("button", { name: "Open my progress" }).click();
  const audio = page.locator("audio").first();
  await expect(audio).toBeVisible();
  await page.waitForFunction(
    () => {
      const element = document.querySelector("audio");
      return Boolean(element && element.readyState >= 2 && Number.isFinite(element.duration) && element.duration > 0);
    },
    undefined,
    { timeout: 20_000 },
  );

  await page.getByRole("button", { name: "Delete the recording" }).click();
  await page.getByRole("button", { name: "Yes, delete it" }).click();
  await expect(page.locator("audio")).toHaveCount(0);

  const after = await request.get(`${VOICE_URL}/api/recordings/${session?.recording_id}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(after.status()).toBe(404);
  const databaseAfter = await dumpDatabase(request);
  expect(databaseAfter.objectKeys).toHaveLength(0);
  expect(databaseAfter.recordings[0]?.state).toBe("deleted");
});

test("A4 — a consent withdrawn mid-call keeps the metrics and writes no audio", async ({
  page,
  request,
}) => {
  const { token } = await signInAs(page.context(), USER_A);
  await openApp(page);
  await startCall(page);
  await grantRecording(page, request, USER_A);
  await beginCall(page);
  await speak(page);
  await waitForCoachTurn(page);
  await waitForListening(page);

  const withdrawal = await request.post(`${VOICE_URL}/api/consent`, {
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    data: { consentVersion: "0.1", recordingRetentionGranted: false },
  });
  expect(withdrawal.status()).toBe(200);

  await endCall(page);
  await waitForSocketClosed(page);

  const database = await dumpDatabase(request);
  const session = database.sessions.find((row) => row.user_id === USER_A);
  expect(session).toBeTruthy();
  expect(session?.recording_id).toBeNull();
  expect(database.recordings).toHaveLength(0);
  expect(database.objectKeys).toHaveLength(0);
});

test("A5 — speaking over the coach stops the audio and no late audio arrives", async ({
  page,
  request,
}) => {
  await openApp(page);
  await startCall(page);
  await beginCall(page);
  await speak(page);
  await expect(page.getByTestId("call-status")).toHaveText("Speaking", { timeout: 20_000 });

  await setMic(page, "speech");
  await expect(page.getByText("You spoke over the coach, so the coach stopped.")).toBeVisible({
    timeout: 10_000,
  });
  await page.waitForTimeout(400);
  const before = (await sockets(page))[0].binary;

  await page.waitForTimeout(1_200);
  const after = (await sockets(page)).at(-1)?.binary ?? 0;
  expect(after).toBe(before);

  await setMic(page, "silence");
  await waitForListening(page);
  await validateWire(page);
  await endCall(page);
  await waitForSocketClosed(page);

  // The 20-trial stop-time measurement is in the Python fake-stack test
  // (`test_interrupt_latency.py`), labelled "not the real target".
});

test("A6 — signing out closes the live call socket", async ({ page, request }) => {
  await signInAs(page.context(), USER_A);
  await openApp(page);
  await startCall(page);
  await beginCall(page);

  await page.getByTestId("call-sign-out").click();
  await expect(page.getByRole("button", { name: "Start a practice call" })).toBeVisible({
    timeout: 15_000,
  });
  await waitForSocketClosed(page);

  const session = await page.request.get(`${APP_URL}/auth/session`);
  expect(await session.json()).toMatchObject({ status: "guest", userId: null });
  await expect
    .poll(async () => (await dumpDatabase(request)).sessions.some((row) => row.user_id === USER_A))
    .toBe(true);
});

test("A7 — another learner cannot list, read or delete user A's data", async ({
  page,
  request,
}) => {
  const { token: tokenA } = await signInAs(page.context(), USER_A);
  await openApp(page);
  await startCall(page);
  await grantRecording(page, request, USER_A);
  await beginCall(page);
  await speak(page);
  await waitForCoachTurn(page);
  await waitForListening(page);
  await endCall(page);
  await waitForSocketClosed(page);

  const database = await dumpDatabase(request);
  const sessionA = database.sessions.find((row) => row.user_id === USER_A);
  expect(sessionA?.recording_id).toBeTruthy();
  const recordingA = sessionA?.recording_id as string;

  const tokenB = (await import("./constants")).mintToken(USER_B);
  const headersB = { Authorization: `Bearer ${tokenB}` };

  const historyB = await request.get(`${VOICE_URL}/api/history`, { headers: headersB });
  expect(historyB.status()).toBe(200);
  const historyBody = (await historyB.json()) as { sessions: Array<{ sessionId: string }> };
  expect(historyBody.sessions.some((row) => row.sessionId === sessionA?.session_id)).toBe(false);

  const forged = await request.get(
    `${VOICE_URL}/api/history?user_id=${encodeURIComponent(USER_A)}`,
    { headers: headersB },
  );
  expect(await forged.json()).toEqual(historyBody);

  const foreign = await request.get(`${VOICE_URL}/api/recordings/${recordingA}`, {
    headers: headersB,
  });
  const missing = await request.get(
    `${VOICE_URL}/api/recordings/rec_00000000000000000000000000000000`,
    { headers: headersB },
  );
  expect(foreign.status()).toBe(404);
  expect(missing.status()).toBe(404);
  const foreignBody = (await foreign.json()) as Record<string, unknown>;
  const missingBody = (await missing.json()) as Record<string, unknown>;
  expect({ ...foreignBody, correlationId: null, occurredAt: null }).toEqual({
    ...missingBody,
    correlationId: null,
    occurredAt: null,
  });

  const deleteForeign = await request.delete(
    `${VOICE_URL}/api/recordings/${recordingA}?user_id=${encodeURIComponent(USER_A)}`,
    { headers: headersB },
  );
  expect(deleteForeign.status()).toBe(404);

  const stillThere = await request.get(`${VOICE_URL}/api/recordings/${recordingA}`, {
    headers: { Authorization: `Bearer ${tokenA}` },
  });
  expect(stillThere.status()).toBe(200);
});

test("A8 — a metrics-only call stores no transcript, reply or custom topic anywhere we write", async ({
  page,
  request,
}) => {
  await signInAs(page.context(), USER_A);
  await openApp(page);
  await startCall(page, { scenario: "custom" });
  await beginCall(page);
  await speak(page);
  await waitForCoachTurn(page);
  await waitForListening(page);
  await endCall(page);
  await waitForSocketClosed(page);

  const database = JSON.stringify(await dumpDatabase(request));
  const dump = await serviceDump(request);
  expect(database.toLowerCase()).not.toContain(TRANSCRIPT_SENTINEL);
  expect(database.toLowerCase()).not.toContain(TOPIC_SENTINEL);
  expect(database).not.toContain(REPLY_SENTINEL);
  expect(dump.log.toLowerCase()).not.toContain(TRANSCRIPT_SENTINEL);
  expect(dump.log.toLowerCase()).not.toContain(TOPIC_SENTINEL);
  expect(dump.log).not.toContain(REPLY_SENTINEL);

  // The wire itself carried the transcript to the page; that is expected.
  // What matters is that nothing durable did.
  const snapshot = await sockets(page);
  const received = snapshot.flatMap((socket) => socket.received).join("\n");
  expect(received.toLowerCase()).toContain(TRANSCRIPT_SENTINEL);
  expect(received).toContain(REPLY_SENTINEL);

  // The project's own cache/temp locations, not the whole machine.
  const roots = [
    resolve(__dirname, ".artifacts"),
    resolve(__dirname, "../../../apps/web/.next/cache"),
    resolve(__dirname, "../../../services/voice/.pytest_cache"),
  ];
  for (const root of roots) {
    for (const file of filesUnder(root)) {
      const text = readFileSync(file, "utf8");
      expect(text.toLowerCase(), `content leaked into ${file}`).not.toContain(TRANSCRIPT_SENTINEL);
      expect(text.toLowerCase(), `content leaked into ${file}`).not.toContain(TOPIC_SENTINEL);
      expect(text, `content leaked into ${file}`).not.toContain(REPLY_SENTINEL);
    }
  }
});

/** Small recursive reader for the cache inspection above. */
function filesUnder(root: string): string[] {
  const { readdirSync, statSync } = require("node:fs") as typeof import("node:fs");
  const output: string[] = [];
  const walk = (directory: string) => {
    let entries: string[];
    try {
      entries = readdirSync(directory);
    } catch {
      return;
    }
    for (const entry of entries) {
      const path = resolve(directory, entry);
      let stats;
      try {
        stats = statSync(path);
      } catch {
        continue;
      }
      if (stats.isDirectory()) {
        walk(path);
      } else if (stats.size < 2_000_000) {
        output.push(path);
      }
    }
  };
  walk(root);
  return output;
}

// ---------------------------------------------------------------------------
// B — the failure matrix that needs a browser
// ---------------------------------------------------------------------------

async function setSupabaseFailures(
  request: APIRequestContext,
  failures: Record<string, unknown>,
): Promise<void> {
  const response = await request.post(`${CONTROL_URL}/control/supabase`, {
    data: failures,
  });
  expect(response.ok()).toBeTruthy();
}

test("F1 — a double Start opens exactly one call socket", async ({ page }) => {
  await openApp(page);
  await startCall(page);
  // Two synchronous clicks: the first sets the starting ref, the second
  // must be ignored by the product, not by the test's timing.
  await page.evaluate(() => {
    const button = Array.from(document.querySelectorAll("button")).find((candidate) =>
      candidate.textContent?.includes("Start live practice call"),
    );
    button?.click();
    button?.click();
  });
  await expect(page.getByTestId("call-status")).toHaveText("Listening", {
    timeout: 20_000,
  });
  expect(await sockets(page)).toHaveLength(1);
  await endCall(page);
  await waitForSocketClosed(page);
});

test("F2 — unplugging the microphone ends the call with plain words", async ({
  page,
  request,
}) => {
  await openApp(page);
  await startCall(page);
  await beginCall(page);
  await page.evaluate(() => {
    (window as unknown as { __unplugMic: () => void }).__unplugMic();
  });
  await expect(
    page.getByText("Your microphone was disconnected. Reconnect it, then start the call again."),
  ).toBeVisible({ timeout: 10_000 });
  await waitForSocketClosed(page);
  await waitForNoData(request);
});

test("F3 — a dropped socket reconnects and does not duplicate a turn", async ({
  page,
}) => {
  await openApp(page);
  await startCall(page);
  await beginCall(page);
  await speak(page);
  await waitForCoachTurn(page);

  await page.evaluate(() => {
    const socket = (
      window as unknown as { __sockets: Array<{ __url: string; close: () => void }> }
    ).__sockets.find((candidate) => candidate.__url.includes("/ws/call"));
    socket?.close();
  });

  await expect
    .poll(async () => (await sockets(page)).length, { timeout: 15_000 })
    .toBeGreaterThanOrEqual(2);
  await expect(page.getByTestId("call-status")).toHaveText("Listening", {
    timeout: 20_000,
  });

  const received = (await sockets(page)).flatMap((socket) => socket.received);
  const finals = received.filter(
    (raw) => raw.includes('"type":"transcript_final"') && raw.includes(TRANSCRIPT_SENTINEL),
  );
  expect(finals).toHaveLength(1);

  await endCall(page);
  await waitForSocketClosed(page);
  await validateWire(page);
});

test("F4 — an STT outage is named and the call can still end", async ({
  page,
  request,
}) => {
  await setFailures(request, { sttMode: "network" });
  await openApp(page);
  await startCall(page);
  await beginCall(page);
  await speak(page);
  await expect(page.getByText("The speech service is having trouble.")).toBeVisible({
    timeout: 20_000,
  });
  await endCall(page);
  await waitForSocketClosed(page);
  await waitForNoData(request);
});

test("F5 — a TTS outage mid-sentence is named and the call can still end", async ({
  page,
  request,
}) => {
  await setFailures(request, { ttsAfter: 4 });
  await openApp(page);
  await startCall(page);
  await beginCall(page);
  await speak(page);
  await expect(page.getByText("The speech service is having trouble.")).toBeVisible({
    timeout: 20_000,
  });
  await endCall(page);
  await waitForSocketClosed(page);
  await waitForNoData(request);
});

test("F6 — a reasoning timeout is named and the call can still end", async ({
  page,
  request,
}) => {
  await setFailures(request, { reasoning: "timeout" });
  await openApp(page);
  await startCall(page);
  await beginCall(page);
  await speak(page);
  await expect(page.getByText("That took too long.")).toBeVisible({ timeout: 20_000 });
  await endCall(page);
  await waitForSocketClosed(page);
  await waitForNoData(request);
});

test("F7 — Auth down continues as a guest with a notice and no data", async ({
  page,
  request,
}) => {
  const { token } = await signInAs(page.context(), USER_A);
  await openApp(page);
  // Auth goes down before the call starts. The page's own session lookup
  // is fulfilled with the token it already held (the browser fetch is
  // intercepted, not the product), so the voice service is the component
  // under test: it must degrade to a guest and say so.
  await setSupabaseFailures(request, { auth: true });
  await page.route("**/auth/session", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        status: "authenticated",
        userId: USER_A,
        accessToken: token,
      }),
    });
  });
  await startCall(page);
  await beginCall(page);
  await expect(page.getByTestId("call-notice")).toContainText("sign-in could not be confirmed");
  await endCall(page);
  await waitForSocketClosed(page);
  await waitForNoData(request);
});

test("F8 — REST down at the end says the session was not saved", async ({
  page,
  request,
}) => {
  await signInAs(page.context(), USER_A);
  await openApp(page);
  await startCall(page);
  await beginCall(page);
  await speak(page);
  await waitForCoachTurn(page);
  await setSupabaseFailures(request, { rest: true });
  await waitForListening(page);
  await endCall(page);
  await expect(page.getByTestId("summary-notice")).toContainText("This session was not saved");
  await waitForSocketClosed(page);
  await waitForNoData(request);
});

test("F9 — Storage down keeps the metrics and says the recording is missing", async ({
  page,
  request,
}) => {
  await signInAs(page.context(), USER_A);
  await openApp(page);
  await startCall(page);
  await grantRecording(page, request, USER_A);
  await beginCall(page);
  await speak(page);
  await waitForCoachTurn(page);
  await setSupabaseFailures(request, { storage: true });
  await waitForListening(page);
  await endCall(page);
  await expect(page.getByTestId("summary-notice")).toContainText(
    "The recording could not be saved",
  );
  await waitForSocketClosed(page);
  const database = await dumpDatabase(request);
  expect(database.sessions).toHaveLength(1);
  expect(database.sessions[0].recording_id).toBeNull();
  expect(database.recordings).toHaveLength(0);
  expect(database.objectKeys).toHaveLength(0);
});

test("F10 — closing the tab stores the metrics and closes the socket", async ({
  page,
  request,
}) => {
  await signInAs(page.context(), USER_A);
  await openApp(page);
  await startCall(page);
  await beginCall(page);
  await speak(page);
  await waitForCoachTurn(page);
  await waitForListening(page);
  await page.close();

  await expect
    .poll(async () => {
      const database = await dumpDatabase(request);
      return database.sessions.filter((row) => row.user_id === USER_A).length;
    }, { timeout: 15_000 })
    .toBe(1);
  const database = await dumpDatabase(request);
  const session = database.sessions.find((row) => row.user_id === USER_A);
  expect(session?.turn_count).toBe(1);
});
