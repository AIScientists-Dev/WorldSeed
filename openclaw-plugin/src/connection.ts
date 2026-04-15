/**
 * Per-account WebSocket connection bridge.
 *
 * Gateway owns the WebSocket lifecycle. Tools need to send
 * perceive/act requests through the same connection and wait
 * for responses. Each account gets its own ConnectionBridge
 * instance — safe for multi-agent scenarios.
 */

import WebSocket from "ws";

type PendingRequest = {
  resolve: (msg: any) => void;
  reject: (err: Error) => void;
  timer: ReturnType<typeof setTimeout>;
};

export class ConnectionBridge {
  private ws: WebSocket | null = null;
  private pending = new Map<string, PendingRequest>();
  private requestCounter = 0;

  setConnection(ws: WebSocket | null): void {
    this.ws = ws;
    if (ws === null) {
      for (const [, req] of this.pending) {
        clearTimeout(req.timer);
        req.reject(new Error("WebSocket disconnected"));
      }
      this.pending.clear();
    }
  }

  handleResponse(msg: any): boolean {
    const requestId = msg.request_id;
    if (!requestId) return false;

    const req = this.pending.get(requestId);
    if (!req) return false;

    clearTimeout(req.timer);
    this.pending.delete(requestId);

    if (msg.type === "error") {
      req.reject(new Error(msg.detail ?? "unknown error"));
    } else {
      req.resolve(msg);
    }
    return true;
  }

  /** Fire-and-forget send (no request_id, no response expected). */
  sendRaw(msg: Record<string, unknown>): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(msg));
    }
  }

  sendRequest(msg: Record<string, unknown>, timeoutMs = 30000): Promise<any> {
    return new Promise((resolve, reject) => {
      if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
        reject(new Error("Not connected to WorldSeed"));
        return;
      }

      const requestId = `req_${++this.requestCounter}_${Date.now()}`;
      const timer = setTimeout(() => {
        this.pending.delete(requestId);
        reject(new Error(`Request timed out: ${msg.type}`));
      }, timeoutMs);

      this.pending.set(requestId, { resolve, reject, timer });

      try {
        this.ws.send(JSON.stringify({ ...msg, request_id: requestId }));
      } catch (err: any) {
        clearTimeout(timer);
        this.pending.delete(requestId);
        reject(new Error(`Send failed: ${err.message}`));
      }
    });
  }
}
