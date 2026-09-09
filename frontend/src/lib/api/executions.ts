/**
 * lib/api/executions.ts — Phase 3: Test Runs & Execution Engine API client
 */
import api from "../api";

async function apiRequest<T>(url: string, opts?: { method?: string; body?: unknown }): Promise<T> {
  const method = (opts?.method ?? "GET").toUpperCase();
  const res = method === "GET" || method === "DELETE"
    ? await api.request<T>({ method, url })
    : await api.request<T>({ method, url, data: opts?.body });
  return res.data;
}

export type RunStatus =
  | "QUEUED" | "DISPATCHED" | "RUNNING" | "COMPLETED"
  | "FAILED" | "ABORTED" | "CANCELLED" | "TIMED_OUT";

export type RunPriority = "LOW" | "NORMAL" | "HIGH" | "URGENT";

export interface TestRun {
  id: string;
  org_id: string;
  test_case_id: string;
  test_case_version: number;
  environment_id: string | null;
  environment_version: number | null;
  agent_id: string | null;
  agent_version: string | null;
  triggered_by: string | null;
  triggered_at: string;
  status: RunStatus;
  priority: RunPriority;
  started_at: string | null;
  completed_at: string | null;
  retry_count: number;
  dispatch_attempt_count: number;
  total_steps: number | null;
  passed_steps: number;
  failed_steps: number;
  skipped_steps: number;
  error_message: string | null;
  timeout_seconds: number;
  execution_snapshot_sha256: string | null;
  snapshot_schema_version: number;
  warnings?: Array<{ step: number; field: string; issue: string; message: string }>;
}

export interface StepResult {
  id: string;
  run_id: string;
  execution_step_id: string;
  step_id: string;
  step_version: number;
  position: number;
  attempt: number;
  action: string;
  status: string;
  started_at: string | null;
  completed_at: string | null;
  duration_ms: number | null;
  display_value: string | null;
  screenshot_url: string | null;
  error_message: string | null;
  assertions: object[];
}

export interface RunEvent {
  id: string;
  run_id: string;
  sequence: number;
  timestamp: string;
  event: string;
  severity: string;
  message: string;
  metadata: Record<string, unknown>;
}

export interface PaginatedRuns {
  items: TestRun[];
  total: number;
}

// ── Runs ──────────────────────────────────────────────────────────────────────

export const triggerRun = (body: {
  test_case_id: string;
  environment_id?: string;
  run_variables?: Record<string, string>;
  priority?: RunPriority;
  timeout_seconds?: number;
}) => apiRequest<TestRun>("/runs", { method: "POST", body });

export const listRuns = (params?: {
  test_case_id?: string;
  status?: RunStatus;
  priority?: RunPriority;
  offset?: number;
  limit?: number;
}) => {
  const qs = new URLSearchParams();
  if (params?.test_case_id) qs.set("test_case_id", params.test_case_id);
  if (params?.status) qs.set("status", params.status);
  if (params?.priority) qs.set("priority", params.priority);
  if (params?.offset !== undefined) qs.set("offset", String(params.offset));
  if (params?.limit !== undefined) qs.set("limit", String(params.limit));
  return apiRequest<PaginatedRuns>(`/runs?${qs.toString()}`);
};

export const getRun = (id: string) => apiRequest<TestRun>(`/runs/${id}`);

export const getRunSteps = (runId: string) =>
  apiRequest<StepResult[]>(`/runs/${runId}/steps`);

export const getRunEvents = (runId: string, severity?: string) => {
  const qs = severity ? `?severity=${severity}` : "";
  return apiRequest<RunEvent[]>(`/runs/${runId}/events${qs}`);
};

export const cancelRun = (id: string) =>
  apiRequest<void>(`/runs/${id}/cancel`, { method: "POST" });

export const abortRun = (id: string) =>
  apiRequest<void>(`/runs/${id}/abort`, { method: "POST" });

export const retryRun = (id: string) =>
  apiRequest<TestRun>(`/runs/${id}/retry`, { method: "POST" });
