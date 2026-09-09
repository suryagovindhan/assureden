/**
 * lib/hooks/useRunStream.ts — Phase 5: SSE live run event streaming.
 *
 * ## Auth flow (JWT Bearer → SSE ticket)
 *
 * Browser EventSource cannot send Authorization headers, so we use a
 * two-step pattern:
 *
 *   1. POST /api/realtime/token?run_id=<id>   — exchange Bearer token for a
 *      60-second SSE ticket scoped to this run.
 *
 *   2. new EventSource(`/api/sse/runs/<id>?token=<ticket>&last_sequence=<n>`)
 *
 * The hook handles:
 *   - Ticket acquisition (one POST per hook mount)
 *   - Reconnection with exponential back-off on error
 *   - Resumption via last_sequence so duplicate events are never shown
 *   - Auto-close when the SSE_CLOSED sentinel event is received
 *   - Cleanup on component unmount
 *
 * ## Usage
 *
 *   const { events, connected, error } = useRunStream(runId, {
 *     enabled: run.status === "RUNNING",
 *   });
 */

import { useState, useEffect, useRef, useCallback } from "react";
import api, { getAccessToken } from "../api";
import type { RunEvent } from "../api/executions";

export interface UseRunStreamOptions {
  /** When false, the stream is not opened. Defaults to true. */
  enabled?: boolean;
  /** Initial sequence to resume from (exclusive). Defaults to 0. */
  initialSequence?: number;
}

export interface UseRunStreamResult {
  events: RunEvent[];
  connected: boolean;
  error: string | null;
  /** Clear accumulated events */
  clearEvents: () => void;
}

const RECONNECT_BASE_MS = 1_000;
const RECONNECT_MAX_MS  = 30_000;
const RECONNECT_FACTOR  = 2;

async function fetchSseTicket(runId: string): Promise<string> {
  const res = await api.post<{ token: string; expires_in: number }>(
    `/realtime/token?run_id=${runId}`
  );
  return res.data.token;
}

export function useRunStream(
  runId: string | undefined,
  options: UseRunStreamOptions = {}
): UseRunStreamResult {
  const { enabled = true, initialSequence = 0 } = options;

  const [events, setEvents]       = useState<RunEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const [error, setError]         = useState<string | null>(null);

  // Refs that survive re-renders without triggering effects
  const esRef          = useRef<EventSource | null>(null);
  const lastSeqRef     = useRef(initialSequence);
  const reconnectMs    = useRef(RECONNECT_BASE_MS);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const unmountedRef   = useRef(false);

  const clearEvents = useCallback(() => setEvents([]), []);

  const connect = useCallback(async () => {
    if (!runId || unmountedRef.current) return;

    // Close any existing connection before opening a new one
    if (esRef.current) {
      esRef.current.close();
      esRef.current = null;
    }

    let ticket: string;
    try {
      ticket = await fetchSseTicket(runId);
    } catch {
      if (!unmountedRef.current) {
        setError("Failed to obtain SSE ticket — retrying…");
        scheduleReconnect();
      }
      return;
    }

    const url = `/api/sse/runs/${runId}?token=${encodeURIComponent(ticket)}&last_sequence=${lastSeqRef.current}`;
    const es = new EventSource(url);
    esRef.current = es;

    es.onopen = () => {
      if (unmountedRef.current) return;
      setConnected(true);
      setError(null);
      reconnectMs.current = RECONNECT_BASE_MS; // reset back-off on success
    };

    es.onmessage = (ev) => {
      if (unmountedRef.current) return;
      try {
        const data = JSON.parse(ev.data);

        // SSE_CONNECTED and SSE_CLOSED are meta-events — don't add to log
        if (data.event === "SSE_CONNECTED") return;
        if (data.event === "SSE_CLOSED") {
          setConnected(false);
          es.close();
          esRef.current = null;
          return;
        }

        if (typeof data.sequence === "number") {
          lastSeqRef.current = Math.max(lastSeqRef.current, data.sequence);
        }

        // Cast to RunEvent — the stable backend schema guarantees these fields
        const event: RunEvent = {
          id:       data.sequence?.toString() ?? crypto.randomUUID(),
          run_id:   runId,
          sequence: data.sequence ?? 0,
          timestamp: data.timestamp ?? new Date().toISOString(),
          event:    data.event,
          severity: data.severity ?? "INFO",
          message:  data.message ?? "",
          metadata: data.metadata ?? {},
        };

        setEvents((prev) => [...prev, event]);
      } catch {
        // Malformed SSE data — ignore
      }
    };

    es.onerror = () => {
      if (unmountedRef.current) return;
      setConnected(false);
      es.close();
      esRef.current = null;
      scheduleReconnect();
    };
  }, [runId]); // eslint-disable-line react-hooks/exhaustive-deps

  function scheduleReconnect() {
    if (unmountedRef.current) return;
    const delay = reconnectMs.current;
    reconnectMs.current = Math.min(reconnectMs.current * RECONNECT_FACTOR, RECONNECT_MAX_MS);
    reconnectTimer.current = setTimeout(() => {
      if (!unmountedRef.current) connect();
    }, delay);
  }

  useEffect(() => {
    unmountedRef.current = false;

    if (enabled && runId) {
      connect();
    }

    return () => {
      unmountedRef.current = true;
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      if (esRef.current) {
        esRef.current.close();
        esRef.current = null;
      }
      setConnected(false);
    };
  }, [runId, enabled, connect]);

  return { events, connected, error, clearEvents };
}
