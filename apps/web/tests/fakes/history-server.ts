/**
 * The fake history service — Phase 04.
 *
 * The browser reads four HTTP routes from the voice service
 * (`prompts/parallel-G1/ADDENDUM.md` §B). This helper answers them with
 * fixture data so the history screen can be proved without a service.
 *
 * The responses are **fixtures**: they are labelled as such in the tests
 * and they are never used as evidence about the real service.
 */

import type { Page } from "@playwright/test";

/** What the fake history service answers. */
export type FakeHistoryKind =
  /** `401`, as the service answers for a guest. */
  | "guest"
  /** `200` with an empty list. */
  | "empty"
  /** `500`, the plain error state. */
  | "error"
  /** `200` with sessions, none of which has a recording. */
  | "list"
  /** `200` with sessions, one of which has a recording that can be fetched. */
  | "list-with-recording"
  /** `200` with sessions whose recording answers `404`. */
  | "list-with-missing-recording";

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "Authorization, Content-Type",
  "Access-Control-Allow-Methods": "GET, POST, DELETE, OPTIONS",
};

const SESSIONS = [
  {
    sessionId: "ses_fake0000000001",
    recordedAt: "2026-10-20T09:30:00.000Z",
    practiceLanguageId: "english",
    scenarioId: "interview",
    recordingId: null as string | null,
    turnCount: 6,
    speakingTimeMs: 74_000,
  },
];

/** A tiny, valid WAV file: one second of silence at 8 kHz. */
function fakeWav(): Buffer {
  const sampleRate = 8000;
  const samples = sampleRate;
  const dataSize = samples * 2;
  const buffer = Buffer.alloc(44 + dataSize);
  buffer.write("RIFF", 0);
  buffer.writeUInt32LE(36 + dataSize, 4);
  buffer.write("WAVE", 8);
  buffer.write("fmt ", 12);
  buffer.writeUInt32LE(16, 16);
  buffer.writeUInt16LE(1, 20);
  buffer.writeUInt16LE(1, 22);
  buffer.writeUInt32LE(sampleRate, 24);
  buffer.writeUInt32LE(sampleRate * 2, 28);
  buffer.writeUInt16LE(2, 32);
  buffer.writeUInt16LE(16, 34);
  buffer.write("data", 36);
  buffer.writeUInt32LE(dataSize, 40);
  return buffer;
}

export interface FakeHistoryService {
  /** The requests the page made. */
  readonly requests: string[];
  /** The recordings that were deleted. */
  readonly deleted: string[];
}

/** Install the fake history routes on the page. */
export async function installFakeHistoryService(
  page: Page,
  behaviour: FakeHistoryKind,
): Promise<FakeHistoryService> {
  const requests: string[] = [];
  const deleted: string[] = [];

  await page.route("http://localhost:8000/api/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    requests.push(`${request.method()} ${path}`);

    if (request.method() === "OPTIONS") {
      await route.fulfill({ status: 204, headers: CORS });
      return;
    }

    if (path === "/api/history") {
      if (behaviour === "guest") {
        await route.fulfill({
          status: 401,
          headers: { ...CORS, "Content-Type": "application/json" },
          body: JSON.stringify({
            errorVersion: "0.1",
            code: "not_found",
            category: "not_found",
            message: "No session.",
            retryable: false,
            correlationId: "cor_fixture000001",
            occurredAt: new Date().toISOString(),
          }),
        });
        return;
      }
      if (behaviour === "error") {
        await route.fulfill({
          status: 500,
          headers: { ...CORS, "Content-Type": "application/json" },
          body: JSON.stringify({
            errorVersion: "0.1",
            code: "internal.error",
            category: "internal",
            message: "Something went wrong.",
            retryable: true,
            correlationId: "cor_fixture000002",
            occurredAt: new Date().toISOString(),
          }),
        });
        return;
      }
      if (behaviour === "empty" || behaviour === "list") {
        await route.fulfill({
          status: 200,
          headers: { ...CORS, "Content-Type": "application/json" },
          body: JSON.stringify({ sessions: behaviour === "empty" ? [] : SESSIONS }),
        });
        return;
      }
      const sessions = SESSIONS.map((session) => ({
        ...session,
        recordingId:
          behaviour === "list-with-recording" ? "rec_fake0000000001" : "rec_missing000001",
      }));
      await route.fulfill({
        status: 200,
        headers: { ...CORS, "Content-Type": "application/json" },
        body: JSON.stringify({ sessions }),
      });
      return;
    }

    if (path.startsWith("/api/recordings/")) {
      const recordingId = path.slice("/api/recordings/".length);
      if (request.method() === "DELETE") {
        deleted.push(recordingId);
        await route.fulfill({ status: 204, headers: CORS });
        return;
      }
      if (behaviour === "list-with-missing-recording") {
        await route.fulfill({ status: 404, headers: CORS });
        return;
      }
      await route.fulfill({
        status: 200,
        headers: { ...CORS, "Content-Type": "audio/wav" },
        body: fakeWav(),
      });
      return;
    }

    if (path === "/api/consent") {
      await route.fulfill({
        status: 200,
        headers: { ...CORS, "Content-Type": "application/json" },
        body: JSON.stringify({
          recordingRetentionGranted: true,
          recordingRetentionGrantedAt: new Date().toISOString(),
        }),
      });
      return;
    }

    await route.fulfill({ status: 404, headers: CORS });
  });

  return { requests, deleted };
}
