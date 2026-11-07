/**
 * Browser instrumentation for the assembled suite — installed **before**
 * any page script runs.
 *
 * Two things are installed:
 *
 * 1. a fake microphone built from an oscillator, so the test can set
 *    deterministic speech or silence; the real capture worklet, the real
 *    resampler and the real frame size are still exercised;
 * 2. a WebSocket tracker, so every string the browser sends and every
 *    server envelope can be validated against `packages/contracts` and the
 *    socket's final state can be asserted.
 *
 * This is instrumentation, not a mock of the product: no application code
 * is replaced.
 */

export const INSTRUMENTATION = `
(() => {
  const RealWebSocket = window.WebSocket;
  const sockets = [];
  window.__sockets = sockets;

  class TrackedWebSocket extends RealWebSocket {
    constructor(url, protocols) {
      super(url, protocols);
      this.__url = String(url);
      this.__sent = [];
      this.__received = [];
      this.__binary = 0;
      sockets.push(this);
      this.addEventListener("message", (event) => {
        if (typeof event.data === "string") {
          this.__received.push(event.data);
        } else {
          this.__binary += 1;
        }
      });
    }
    send(data) {
      if (typeof data === "string") {
        this.__sent.push(data);
      }
      return super.send(data);
    }
  }
  TrackedWebSocket.CONNECTING = RealWebSocket.CONNECTING;
  TrackedWebSocket.OPEN = RealWebSocket.OPEN;
  TrackedWebSocket.CLOSING = RealWebSocket.CLOSING;
  TrackedWebSocket.CLOSED = RealWebSocket.CLOSED;
  window.WebSocket = TrackedWebSocket;

  let context = null;
  let gain = null;
  let tracks = [];
  let mode = "silence";
  window.__micMode = mode;

  const build = async () => {
    if (context) {
      return;
    }
    const AudioContextCtor = window.AudioContext || window.webkitAudioContext;
    context = new AudioContextCtor();
    await context.resume();
    const oscillator = context.createOscillator();
    oscillator.type = "sine";
    oscillator.frequency.value = 320;
    gain = context.createGain();
    gain.gain.value = mode === "speech" ? 0.3 : 0;
    const destination = context.createMediaStreamDestination();
    oscillator.connect(gain);
    gain.connect(destination);
    oscillator.start();
    tracks = destination.stream.getAudioTracks();
    window.__micTracks = tracks;
  };

  const realGetUserMedia = navigator.mediaDevices && navigator.mediaDevices.getUserMedia
    ? navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices)
    : null;

  navigator.mediaDevices.getUserMedia = async (constraints) => {
    const wantsAudio = !constraints || constraints.audio === undefined || constraints.audio;
    if (!wantsAudio) {
      return realGetUserMedia ? realGetUserMedia(constraints) : new MediaStream();
    }
    await build();
    return new MediaStream(tracks);
  };

  window.__setMic = (next) => {
    mode = next === "speech" ? "speech" : "silence";
    window.__micMode = mode;
    if (gain) {
      gain.gain.value = mode === "speech" ? 0.3 : 0;
    }
  };

  window.__unplugMic = () => {
    for (const track of tracks) {
      // A stopped track does not fire "ended" by itself, so the test
      // dispatches the event a real device removal would fire.
      track.dispatchEvent(new Event("ended"));
    }
  };

  window.__socketSnapshot = () =>
    sockets.map((socket) => ({
      url: socket.__url,
      readyState: socket.readyState,
      sent: socket.__sent.slice(),
      received: socket.__received.slice(),
      binary: socket.__binary,
    }));

  window.__uiStatuses = [];
  setInterval(() => {
    const element = document.querySelector('[data-testid="call-status"]');
    if (!element) {
      return;
    }
    const text = (element.textContent || "").trim();
    const seen = window.__uiStatuses;
    if (seen.length === 0 || seen[seen.length - 1] !== text) {
      seen.push(text);
    }
  }, 40);
})();
`;
