/**
 * lib/api/schedules.ts — Phase 5: Schedule management API client
 */
import api from "../api";

async function apiRequest<T>(url: string, opts?: { method?: string; body?: unknown }): Promise<T> {
  const method = (opts?.method ?? "GET").toUpperCase();
  const res =
    method === "GET" || method === "DELETE"
      ? await api.request<T>({ method, url })
      : await api.request<T>({ method, url, data: opts?.body });
  return res.data;
}

// ── Types ────────────────────────────────────────────────────────────────────

export interface ScheduledJob {
  id: string;
  name: string;
  cron_expression: string;
  timezone: string;
  test_case_id: string;
  environment_id: string | null;
  priority: string;
  is_enabled: boolean;
  next_run_at: string | null;
  last_run_status: string | null;
  max_retries: number;
  retry_delay_seconds: number;
  backoff_multiplier: number;
  max_retry_delay: number;
  retry_on_timeout: boolean;
  retry_on_failure: boolean;
  retry_on_network_error: boolean;
  miss_threshold_minutes: number;
  created_at: string | null;
  next_occurrences?: string[];
}

export interface ScheduleHistoryRow {
  id: string;
  triggered_at: string | null;
  status: string;
  run_id: string | null;
  trigger_error: string | null;
}

export interface ScheduleHistory {
  schedule: ScheduledJob;
  count: number;
  history: ScheduleHistoryRow[];
}

export interface PaginatedSchedules {
  total: number;
  items: ScheduledJob[];
}

export interface CreateScheduleBody {
  name: string;
  cron_expression: string;
  timezone: string;
  test_case_id: string;
  environment_id?: string;
  priority?: string;
  run_variables?: Record<string, string>;
  max_retries?: number;
  retry_delay_seconds?: number;
  backoff_multiplier?: number;
  max_retry_delay?: number;
  retry_on_timeout?: boolean;
  retry_on_failure?: boolean;
  retry_on_network_error?: boolean;
  miss_threshold_minutes?: number;
}

export interface PatchScheduleBody {
  name?: string;
  cron_expression?: string;
  timezone?: string;
  environment_id?: string | null;
  priority?: string;
  run_variables?: Record<string, string>;
  max_retries?: number;
  retry_delay_seconds?: number;
  backoff_multiplier?: number;
  max_retry_delay?: number;
  retry_on_timeout?: boolean;
  retry_on_failure?: boolean;
  retry_on_network_error?: boolean;
  miss_threshold_minutes?: number;
}

// ── API calls ─────────────────────────────────────────────────────────────────

export const listSchedules = (params?: {
  enabled_only?: boolean;
  offset?: number;
  limit?: number;
}) => {
  const qs = new URLSearchParams();
  if (params?.enabled_only) qs.set("enabled_only", "true");
  if (params?.offset !== undefined) qs.set("offset", String(params.offset));
  if (params?.limit !== undefined) qs.set("limit", String(params.limit));
  return apiRequest<PaginatedSchedules>(`/schedules?${qs.toString()}`);
};

export const getSchedule = (id: string) =>
  apiRequest<ScheduledJob>(`/schedules/${id}`);

export const createSchedule = (body: CreateScheduleBody) =>
  apiRequest<ScheduledJob>("/schedules", { method: "POST", body });

export const patchSchedule = (id: string, body: PatchScheduleBody) =>
  apiRequest<ScheduledJob>(`/schedules/${id}`, { method: "PATCH", body });

export const deleteSchedule = (id: string) =>
  apiRequest<void>(`/schedules/${id}`, { method: "DELETE" });

export const enableSchedule = (id: string) =>
  apiRequest<ScheduledJob>(`/schedules/${id}/enable`, { method: "POST" });

export const disableSchedule = (id: string) =>
  apiRequest<ScheduledJob>(`/schedules/${id}/disable`, { method: "POST" });

export const triggerNow = (id: string) =>
  apiRequest<{ run_id: string; status: string; triggered_at: string; test_case_id: string; priority: string }>(
    `/schedules/${id}/trigger-now`,
    { method: "POST" }
  );

export const getScheduleHistory = (id: string, limit?: number) => {
  const qs = limit ? `?limit=${limit}` : "";
  return apiRequest<ScheduleHistory>(`/schedules/${id}/history${qs}`);
};
