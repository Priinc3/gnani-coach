/**
 * The Phase 03 integration smoke test — the browser half.
 *
 * It boots the real web app and the real voice service and checks the
 * frozen seams from the outside: the real landing screen (Start enabled,
 * leading to the scenario picker), no microphone request on load, the
 * service answers `/health`, the history seam answers a guest with
 * `unauthenticated`, and the call socket's first message is
 * `status connecting`.
 *
 * Batch B2 extends this file with the real call, the four-turn coaching
 * round, an interruption and the recording lifecycle.
 */
import { expect, test } from "@playwright/test";

const serviceURL = process.env.SPEAKING_COACH_SERVICE_URL ?? "http://127.0.0.1:8000";

test("the home page renders the real landing and Start leads to the scenario picker", async ({
  page,
}) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /Speak with/ })).toBeVisible();
  // The real app: Start is enabled and opens the scenario picker. Nothing
  // pretends to be live before the learner starts a call.
  const start = page.getByRole("button", { name: "Start a practice call" });
  await expect(start).toBeEnabled();
  await start.click();
  await expect(
    page.getByRole("heading", { name: "Choose what you want to practise" }),
  ).toBeVisible();
});

test("the web page requests no microphone access", async ({ page }) => {
  await page.addInitScript(() => {
    const state = window as unknown as { __micRequests: number };
    state.__micRequests = 0;
    if (navigator.mediaDevices) {
      const original = navigator.mediaDevices.getUserMedia?.bind(navigator.mediaDevices);
      navigator.mediaDevices.getUserMedia = ((...args: Parameters<MediaDevices["getUserMedia"]>) => {
        state.__micRequests += 1;
        return original ? original(...args) : Promise.reject(new Error("no media devices"));
      }) as MediaDevices["getUserMedia"];
    }
  });
  await page.goto("/");
  await expect(page.getByRole("status")).toContainText("practising");
  const requests = await page.evaluate(
    () => (window as unknown as { __micRequests: number }).__micRequests,
  );
  expect(requests).toBe(0);
});

test("the voice service answers /health", async ({ request }) => {
  const response = await request.get(`${serviceURL}/health`);
  expect(response.status()).toBe(200);
  const body = await response.json();
  expect(body.status).toBe("ok");
  expect(body.liveCallingImplemented).toBe(false);
});

test("the history seam answers a guest with unauthenticated", async ({ request }) => {
  const response = await request.get(`${serviceURL}/api/history`);
  expect(response.status()).toBe(401);
  const body = await response.json();
  expect(body.code).toBe("unauthenticated");
  expect(body.category).toBe("unauthenticated");
  expect(body.retryable).toBe(false);
});

test("the call socket's first message is status connecting", async ({ page }) => {
  await page.goto("/");
  const outcome = await page.evaluate(async (service: string) => {
    const url = service.replace(/^http/, "ws") + "/ws/call";
    return await new Promise<{ message: unknown; closed: boolean }>((resolve, reject) => {
      const socket = new WebSocket(url);
      const timer = setTimeout(() => reject(new Error("timed out")), 10_000);
      socket.onmessage = (event) => {
        clearTimeout(timer);
        socket.close();
        resolve({ message: JSON.parse(String(event.data)), closed: true });
      };
      socket.onerror = () => {
        clearTimeout(timer);
        reject(new Error("the socket could not be opened"));
      };
    });
  }, serviceURL);

  const message = outcome.message as {
    envelopeVersion: string;
    direction: string;
    type: string;
    payload: { state: string };
  };
  expect(message.envelopeVersion).toBe("0.1");
  expect(message.direction).toBe("server_to_client");
  expect(message.type).toBe("status");
  expect(message.payload.state).toBe("connecting");
});
