/**
 * Fencing — Phase 04.
 *
 * The three protections the transport contract asks for, as pure logic:
 * connection fencing, sequence fencing and turn fencing.
 */

import { expect, test } from "@playwright/test";

import { Fence } from "../../src/lib/transport/fencing";

function event(
  type: string,
  connectionId: string,
  sequence: number,
  turnId: string | null = null,
) {
  return { type, connectionId, sequence, turnId };
}

test("the first event of a connection is accepted and adopts its connection id", () => {
  const fence = new Fence();
  const result = fence.accept(event("status", "con_abcdefgh", 0));
  expect(result.accepted).toBe(true);
  expect(fence.currentConnectionId()).toBe("con_abcdefgh");
});

test("an event with no connection id is refused as malformed", () => {
  const fence = new Fence();
  const result = fence.accept({
    type: "status",
    connectionId: null,
    sequence: 0,
    turnId: null,
  });
  expect(result).toEqual({ accepted: false, reason: "malformed" });
});

test("a duplicate sequence is dropped", () => {
  const fence = new Fence();
  expect(fence.accept(event("status", "con_abcdefgh", 1)).accepted).toBe(true);
  const duplicate = fence.accept(event("status", "con_abcdefgh", 1));
  expect(duplicate).toEqual({ accepted: false, reason: "duplicate_sequence" });
  // An older sequence is dropped as well.
  const older = fence.accept(event("status", "con_abcdefgh", 0));
  expect(older).toEqual({ accepted: false, reason: "duplicate_sequence" });
  // A newer one is accepted.
  expect(fence.accept(event("status", "con_abcdefgh", 2)).accepted).toBe(true);
});

test("an event from another connection is dropped as stale", () => {
  const fence = new Fence();
  fence.accept(event("status", "con_abcdefgh", 1));
  const stale = fence.accept(event("status", "con_different1", 2));
  expect(stale).toEqual({ accepted: false, reason: "stale_connection" });
});

test("a reconnect adopts the new connection id and drops late events from the old one", () => {
  const fence = new Fence();
  fence.accept(event("status", "con_abcdefgh", 5));
  fence.beginNewConnection();
  // A late event from the connection we just left is dropped.
  const late = fence.accept(event("status", "con_abcdefgh", 6));
  expect(late).toEqual({ accepted: false, reason: "stale_connection" });
  // The new connection is recognised by its different id, and its sequence
  // space starts again.
  const fresh = fence.accept(event("status", "con_newconn01", 0));
  expect(fresh.accepted).toBe(true);
  expect(fence.currentConnectionId()).toBe("con_newconn01");
});

test("a stale turn is dropped and a new turn is accepted", () => {
  const fence = new Fence();
  fence.accept(event("status", "con_abcdefgh", 1));
  expect(fence.accept(event("coach_text", "con_abcdefgh", 2, "trn_firstturn")).accepted).toBe(
    true,
  );
  expect(fence.currentTurn()).toBe("trn_firstturn");
  // A new turn starts.
  expect(fence.accept(event("coach_text", "con_abcdefgh", 3, "trn_secondturn")).accepted).toBe(
    true,
  );
  // A late event for the older turn is dropped.
  const stale = fence.accept(event("coach_text", "con_abcdefgh", 4, "trn_firstturn"));
  expect(stale).toEqual({ accepted: false, reason: "stale_turn" });
});

test("a fenced turn is dropped", () => {
  const fence = new Fence();
  fence.accept(event("status", "con_abcdefgh", 1));
  fence.accept(event("coach_text", "con_abcdefgh", 2, "trn_firstturn"));
  fence.fenceTurn("trn_firstturn");
  expect(fence.isTurnFenced("trn_firstturn")).toBe(true);
  const late = fence.accept(event("audio.frame.descriptor", "con_abcdefgh", 3, "trn_firstturn"));
  expect(late).toEqual({ accepted: false, reason: "fenced_turn" });
});

test("a transcript is not fenced by the turn rules", () => {
  const fence = new Fence();
  fence.accept(event("status", "con_abcdefgh", 1));
  fence.accept(event("coach_text", "con_abcdefgh", 2, "trn_coachturn"));
  // A transcript for a different turn is not a coach turn, so the turn
  // rules do not apply to it.
  const transcript = fence.accept(event("transcript_final", "con_abcdefgh", 3, "trn_learnerturn"));
  expect(transcript.accepted).toBe(true);
});
