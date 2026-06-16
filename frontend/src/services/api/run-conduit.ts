import { API_TOKEN, BASE_URL, USE_MOCK } from "@/config/env";
import { toCamelCase, toSnakeCase } from "@/services/transforms";
import { MockWebSocket } from "@/services/mock/ws";
import type { ClientWsMessage, ServerWsMessage } from "@/types/ws";

const WS_URL = BASE_URL.replace(/^http/, "ws");
const WS_TOKEN_PARAM = API_TOKEN
  ? `?token=${encodeURIComponent(API_TOKEN)}`
  : "";

export class RunConduitSocket {
  private ws: WebSocket;
  onMessage: (msg: ServerWsMessage) => void = () => {};
  onError: (ev: Event) => void = () => {};
  onClose: (code: number, reason: string) => void = () => {};

  constructor() {
    if (USE_MOCK) {
      this.ws = new MockWebSocket() as unknown as WebSocket;
    } else {
      this.ws = new WebSocket(`${WS_URL}/ws/run-conduit${WS_TOKEN_PARAM}`);
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
    return new Promise((resolve) => {
      this.ws.addEventListener("open", () => resolve(), { once: true });
    });
  }
}
