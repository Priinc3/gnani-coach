/**
 * Coach audio playback — Phase 04.
 *
 * The rules this module implements, from `docs/contracts/call-transport.md`:
 *
 * - TTS chunks are played **in order per turn id**. The provider's chunk
 *   sizes are not uniform, so the run is append-only and never reordered by
 *   size or by a guessed arrival time.
 * - On an interrupt — or as soon as the learner's own speech starts — the
 *   coach's audio **stops immediately** and the rest of that turn's queue is
 *   dropped.
 * - Audio for a fenced or stale turn is never played at all.
 *
 * **Stopping playback is not cancelling the provider.** The reviewed TTS
 * interface has no cancel message: the request may still be running and may
 * still be billed. Nothing in this module (or in the UI) claims otherwise.
 */

/** A source node that is currently scheduled, with the turn it belongs to. */
interface ScheduledSource {
  turnId: string;
  source: AudioBufferSourceNode;
  kind: "reply" | "backchannel";
  startAt: number;
  duration: number;
}

export class CoachAudioPlayer {
  private readonly context: AudioContext;
  private readonly gain: GainNode;
  private readonly sources: ScheduledSource[] = [];
  /** The end time of the last chunk scheduled for a turn. */
  private readonly nextStartByTurn = new Map<string, number>();
  /** The end of the last backchannel chunk, so a reply starts after it. */
  private backchannelEndAt = 0;
  /** The end of the last real-reply chunk, so a backchannel can be dropped. */
  private replyEndAt = 0;
  private outputEnabled = true;
  private disposed = false;

  constructor(context: AudioContext) {
    this.context = context;
    this.gain = context.createGain();
    this.gain.gain.value = 1;
    this.gain.connect(context.destination);
  }

  /** Mute or unmute the coach's voice (the "speaker" control). */
  setOutputEnabled(enabled: boolean): void {
    this.outputEnabled = enabled;
    this.gain.gain.value = enabled ? 1 : 0;
  }

  /** Whether the coach's voice is currently audible. */
  isOutputEnabled(): boolean {
    return this.outputEnabled;
  }

  /**
   * Append one TTS chunk to a turn and schedule it right after the previous
   * chunk of the same turn.
   */
  appendChunk(
    turnId: string,
    bytes: Uint8Array,
    sampleRateHz: number,
    kind: "reply" | "backchannel" = "reply",
    learnerSpeaking = false,
  ): void {
    if (this.disposed || bytes.length === 0) {
      return;
    }
    const sampleCount = Math.floor(bytes.length / 2);
    if (sampleCount === 0) {
      return;
    }
    const now = this.context.currentTime;
    if (kind === "backchannel") {
      // A reaction is low priority: it is dropped, never queued, while the
      // learner speaks or the real reply is playing.
      if (learnerSpeaking || this.replyEndAt > now) {
        return;
      }
    }
    const buffer = this.context.createBuffer(1, sampleCount, sampleRateHz);
    const channel = buffer.getChannelData(0);
    const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
    for (let index = 0; index < sampleCount; index += 1) {
      channel[index] = view.getInt16(index * 2, true) / 32768;
    }

    const duration = sampleCount / sampleRateHz;
    const previousEnd = this.nextStartByTurn.get(turnId) ?? 0;
    // The real reply waits for the acknowledgement to finish.
    const afterBackchannel =
      kind === "reply" && this.backchannelEndAt > now ? this.backchannelEndAt : 0;
    const startAt = Math.max(
      now + 0.02,
      previousEnd,
      afterBackchannel,
    );
    const source = this.context.createBufferSource();
    source.buffer = buffer;
    source.connect(this.gain);
    source.start(startAt);
    this.sources.push({ turnId, source, kind, startAt, duration });
    this.nextStartByTurn.set(turnId, startAt + duration);
    if (kind === "backchannel") {
      this.backchannelEndAt = Math.max(this.backchannelEndAt, startAt + duration);
    } else {
      this.replyEndAt = Math.max(this.replyEndAt, startAt + duration);
    }
  }

  /** Stop every spoken reaction, keeping the real reply untouched. */
  stopBackchannels(): void {
    for (let index = this.sources.length - 1; index >= 0; index -= 1) {
      const entry = this.sources[index];
      if (entry.kind !== "backchannel") {
        continue;
      }
      this.sources.splice(index, 1);
      try {
        entry.source.stop();
      } catch {
        // A source that already finished throws when stopped; that is fine.
      }
      entry.source.disconnect();
    }
    this.backchannelEndAt = 0;
  }

  private recomputeEnds(): void {
    let replyEnd = 0;
    let backchannelEnd = 0;
    for (const entry of this.sources) {
      const end = entry.startAt + entry.duration;
      if (entry.kind === "backchannel") {
        backchannelEnd = Math.max(backchannelEnd, end);
      } else {
        replyEnd = Math.max(replyEnd, end);
      }
    }
    this.replyEndAt = replyEnd;
    this.backchannelEndAt = backchannelEnd;
  }

  /**
   * Stop a turn immediately and drop everything still queued for it.
   *
   * This is what an interruption does. It does **not** tell the provider
   * anything — the request on the server side is untouched.
   */
  stopTurn(turnId: string): void {
    for (let index = this.sources.length - 1; index >= 0; index -= 1) {
      const entry = this.sources[index];
      if (entry.turnId !== turnId) {
        continue;
      }
      this.sources.splice(index, 1);
      try {
        entry.source.stop();
      } catch {
        // A source that already finished throws when stopped; that is fine.
      }
      entry.source.disconnect();
    }
    this.nextStartByTurn.delete(turnId);
    this.recomputeEnds();
  }

  /** Stop every turn. */
  stopAll(): void {
    for (const entry of [...this.sources]) {
      try {
        entry.source.stop();
      } catch {
        // Already finished.
      }
      entry.source.disconnect();
    }
    this.sources.length = 0;
    this.nextStartByTurn.clear();
    this.replyEndAt = 0;
    this.backchannelEndAt = 0;
  }

  /** Close the audio graph. */
  dispose(): void {
    this.stopAll();
    this.disposed = true;
    try {
      this.gain.disconnect();
    } catch {
      // Already disconnected.
    }
  }
}
