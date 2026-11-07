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
}

export class CoachAudioPlayer {
  private readonly context: AudioContext;
  private readonly gain: GainNode;
  private readonly sources: ScheduledSource[] = [];
  /** The end time of the last chunk scheduled for a turn. */
  private readonly nextStartByTurn = new Map<string, number>();
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
  appendChunk(turnId: string, bytes: Uint8Array, sampleRateHz: number): void {
    if (this.disposed || bytes.length === 0) {
      return;
    }
    const sampleCount = Math.floor(bytes.length / 2);
    if (sampleCount === 0) {
      return;
    }
    const buffer = this.context.createBuffer(1, sampleCount, sampleRateHz);
    const channel = buffer.getChannelData(0);
    const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
    for (let index = 0; index < sampleCount; index += 1) {
      channel[index] = view.getInt16(index * 2, true) / 32768;
    }

    const duration = sampleCount / sampleRateHz;
    const previousEnd = this.nextStartByTurn.get(turnId) ?? 0;
    const startAt = Math.max(this.context.currentTime + 0.02, previousEnd);
    const source = this.context.createBufferSource();
    source.buffer = buffer;
    source.connect(this.gain);
    source.start(startAt);
    this.sources.push({ turnId, source });
    this.nextStartByTurn.set(turnId, startAt + duration);
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
