/**
 * lib/api/metrics.ts — Phase 5: Dashboard metrics API client
 */
import api from "../api";

async function apiRequest<T>(url: string): Promise<T> {
  const res = await api.request<T>({ method: "GET", url });
  return res.data;
}

// ── Types ────────────────────────────────────────────────────────────────────

export interface RunMetrics {
  total: number;
  queued: number;
  running: number;
  today: number;
  passed_today: number;
  failed_today: number;
}

export interface QueueHealth {
  queued: number;
  oldest_wait_seconds: number;
  average_wait_seconds: number;
  longest_wait_seconds: number;
}

export interface AgentMetrics {
  total: number;
  online: number;
  idle: number;
  offline: number;
  running: number;
}

export interface TestCaseMetrics {
  total: number;
  active: number;
}

export interface ScheduledJobMetrics {
  total: number;
  enabled: number;
}

export interface SchedulerHealth {
  enabled: number;
  disabled: number;
  due_now: number;
  missed_today: number;
}

export interface TrendDay {
  date: string;
  passed: number;
  failed: number;
  total: number;
}

export interface DashboardMetrics {
  runs: RunMetrics;
  queue_health: QueueHealth;
  agents: AgentMetrics;
  test_cases: TestCaseMetrics;
  scheduled_jobs: ScheduledJobMetrics;
  scheduler_health: SchedulerHealth;
  recent_trend: TrendDay[];
}

export interface RetryAttempt {
  attempt: number;
  run_id: string;
  reason: string;
  delay_seconds: number;
}

export interface RetryHistory {
  original_run_id: string;
  retries: RetryAttempt[];
}

export interface QueuedRun {
  run_id: string;
  test_case_id: string;
  priority: string;
  triggered_at: string;
  wait_seconds: number;
  queue_position_overall: number;
  queue_position_in_tier: number;
}

// ── API calls ─────────────────────────────────────────────────────────────────

export const getDashboardMetrics = () =>
  apiRequest<DashboardMetrics>("/metrics/dashboard");

export const getRetryHistory = (runId: string) =>
  apiRequest<RetryHistory>(`/runs/${runId}/retry-history`);

export const getQueue = () =>
  apiRequest<QueuedRun[]>("/runs/queue");
