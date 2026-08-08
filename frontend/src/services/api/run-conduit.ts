import { BASE_URL, USE_MOCK, getApiToken } from "@/config/env";
import { toCamelCase, toSnakeCase } from "@/services/transforms";
import { MockWebSocket } from "@/services/mock/ws";
import type { ClientWsMessage, ServerWsMessage } from "@/types/ws";

const WS_URL = BASE_URL.replace(/^http/, "ws");

// Read when the socket opens, not at module load. The token usually arrives
// after the first REST call prompted for it, which happens well before
// anything opens a socket — captured at import, this would still be "".
function wsTokenParam(): string {
  const token = getApiToken();
  return token ? `?token=${encodeURIComponent(token)}` : "";
}

export class RunConduitSocket {
  private ws: WebSocket;
  onMessage: (msg: ServerWsMessage) => void = () => {};
  onError: (ev: Event) => void = () => {};
  onClose: (code: number, reason: string) => void = () => {};

  constructor() {
    if (USE_MOCK) {
      this.ws = new MockWebSocket() as unknown as WebSocket;
    } else {
      this.ws = new WebSocket(`${WS_URL}/ws/run-conduit${wsTokenParam()}`);
    }

    this.ws.onmessage = (ev) => {
      try {
        const raw = JSON.parse(ev.data);
        const msg = toCamelCase<ServerWsMessage>(raw);
        if (import.meta.env.DEV) console.log("[ws] recv:", msg.type, msg);
        this.onMessage(msg);
      } catch (err) {
        console.error("[ws] failed to parse message", ev.data, err);
      }
    };

    this.ws.onerror = (ev) => {
      console.error("[ws] error", ev);
      this.onError(ev);
    };

    this.ws.onclose = (ev) => {
      console.warn("[ws] closed", ev.code, ev.reason);
      this.onClose(ev.code, ev.reason);
    };
  }

  get readyState() {
    return this.ws.readyState;
  }

  send(msg: ClientWsMessage) {
    const payload = JSON.stringify(toSnakeCase(msg));
    const doSend = () => this.ws.send(payload);
    if (this.ws.readyState === WebSocket.OPEN) {
      doSend();
    } else if (this.ws.readyState === WebSocket.CONNECTING) {
      this.ws.addEventListener("open", doSend, { once: true });
    } else {
      // Closed/closing: don't swallow — surface so callers can react/reconnect.
      throw new Error("cannot send on a closed connection");
    }
  }

  close() {
    if (
      this.ws.readyState === WebSocket.OPEN ||
      this.ws.readyState === WebSocket.CONNECTING
    ) {
      this.ws.close();
    }
  }

  waitForOpen(): Promise<void> {
    if (this.ws.readyState === WebSocket.OPEN) return Promise.resolve();
    if (
      this.ws.readyState === WebSocket.CLOSING ||
      this.ws.readyState === WebSocket.CLOSED
    ) {
      return Promise.reject(new Error("connection closed before opening"));
    }
    // Settle on close/error too, otherwise a connection that never opens
    // (server down, bad token, network blip) leaves this promise hanging and
    // the start command is never sent.
    return new Promise((resolve, reject) => {
      this.ws.addEventListener("open", () => resolve(), { once: true });
      this.ws.addEventListener(
        "error",
        () => reject(new Error("connection failed before opening")),
        { once: true },
      );
      this.ws.addEventListener(
        "close",
        () => reject(new Error("connection closed before opening")),
        { once: true },
      );
    });
  }
}
