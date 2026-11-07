/**
 * Fencing — Phase 04.
 *
 * "Fencing" is the set of rules that stops an event from a *previous* moment
 * being applied to the current one. `docs/contracts/call-transport.md` §4 and
 * §5 ask for three separate protections, and they are implemented here as
 * one pure, testable object:
 *
 * 1. **Connection fencing.** A reconnect gets a new `connectionId`. Events
 *    from the old connection are dropped, never applied to the new one.
 * 2. **Sequence fencing.** `sequence` is a monotonic per-connection counter.
 *    An event whose sequence is not greater than the last accepted one is a
 *    duplicate (or out of order) and is dropped.
 * 3. **Turn fencing.** A coach text, an audio descriptor and the audio
 *    frames that follow it belong to one turn. An event for a turn that is
 *    no longer current — or for a turn the learner interrupted, which the
 *    server fences — is dropped.
 *
 * The rules live in one place so they can be tested without a browser, a
 * socket or a server.
 */

/** The reason an event was refused. */
export type FenceRejection =
  | "malformed"
  | "stale_connection"
  | "duplicate_sequence"
  | "fenced_turn"
  | "stale_turn";

export type FenceResult =
  | { accepted: true }
  | { accepted: false; reason: FenceRejection };

/** The part of an envelope the fence needs. */
export interface FenceEvent {
  type: string;
  connectionId: string | null;
  sequence: number;
  turnId: string | null;
}

/** The event types that belong to a single coach turn. */
export const TURN_BOUND_EVENT_TYPES = new Set([
  "coach_text",
  "audio.frame.descriptor",
]);

export class Fence {
  private connectionId: string | null = null;
  private lastSequence = -1;
  private currentTurnId: string | null = null;
  private currentTurnOrdinal = 0;
  private readonly turnOrdinals = new Map<string, number>();
  private nextOrdinal = 0;
  private readonly fencedTurns = new Set<string>();
  private expectingNewConnection = false;

  /**
   * Announce that the client is about to open a new connection.
   *
   * The current `connectionId` is deliberately **kept**: until the new
   * connection says hello, an event carrying the old id is by definition
   * late, and must be dropped. The new connection is recognised by its
   * *different* id.
   */
  beginNewConnection(): void {
    this.expectingNewConnection = true;
  }

  /** The connection id currently in force, or null before the first event. */
  currentConnectionId(): string | null {
    return this.connectionId;
  }

  /** The turn the coach is currently on, or null. */
  currentTurn(): string | null {
    return this.currentTurnId;
  }

  /** True when the turn was interrupted and may no longer be played. */
  isTurnFenced(turnId: string): boolean {
    return this.fencedTurns.has(turnId);
  }

  /** Mark a turn as fenced: no coach text and no audio for it any more. */
  fenceTurn(turnId: string): void {
    this.fencedTurns.add(turnId);
  }

  /**
   * Decide whether an event may be applied.
   *
   * The order matters: the connection is settled first, then the sequence,
   * then the turn.
   */
  accept(event: FenceEvent): FenceResult {
    if (event.connectionId === null) {
      return { accepted: false, reason: "malformed" };
    }

    if (this.expectingNewConnection) {
      if (event.connectionId === this.connectionId) {
        // A late event from the connection we just left.
        return { accepted: false, reason: "stale_connection" };
      }
      this.adoptConnection(event.connectionId);
    } else if (this.connectionId === null) {
      this.adoptConnection(event.connectionId);
    } else if (event.connectionId !== this.connectionId) {
      return { accepted: false, reason: "stale_connection" };
    }

    if (event.sequence <= this.lastSequence) {
      return { accepted: false, reason: "duplicate_sequence" };
    }
    this.lastSequence = event.sequence;

    if (TURN_BOUND_EVENT_TYPES.has(event.type) && event.turnId !== null) {
      const turnId = event.turnId;
      if (this.fencedTurns.has(turnId)) {
        return { accepted: false, reason: "fenced_turn" };
      }
      const known = this.turnOrdinals.get(turnId);
      if (known !== undefined && known < this.currentTurnOrdinal) {
        return { accepted: false, reason: "stale_turn" };
      }
      if (known === undefined) {
        this.nextOrdinal += 1;
        this.turnOrdinals.set(turnId, this.nextOrdinal);
        this.currentTurnOrdinal = this.nextOrdinal;
        this.currentTurnId = turnId;
      } else {
        this.currentTurnId = turnId;
      }
    }

    return { accepted: true };
  }

  private adoptConnection(connectionId: string): void {
    this.connectionId = connectionId;
    this.expectingNewConnection = false;
    // A new connection has its own sequence space.
    this.lastSequence = -1;
  }
}
