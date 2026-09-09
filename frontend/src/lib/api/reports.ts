/**
 * lib/api/reports.ts — Phase 8: Typed API client for all 7 report endpoints.
 *
 * ## Time range params (shared by all endpoints)
 *
 *   period?: "1d" | "7d" | "30d" | "90d"   relative shorthand
 *   since?:  string                          ISO-8601 explicit start
 *   until?:  string                          ISO-8601 explicit end
 *
 * ## Response envelope (all endpoints)
 *
 *   { since, until, granularity, data }
 *
 *   granularity is null for non-trend reports (flakiness, agents, schedules).
 */

import api from "../api";

// ── Shared types ──────────────────────────────────────────────────────────────

export type Period = "1d" | "7d" | "30d" | "90d";
export type Granularity = "hour" | "day" | "week" | null;

export interface ReportParams {
  period?: Period;
  since?: string;
  until?: string;
}

export interface ReportEnvelope<T> {
  since: string;
  until: string;
  granularity: Granularity;
  data: T;
}

// ── Runs report ───────────────────────────────────────────────────────────────

export interface RunTrendPoint {
  date: string;
  count: number;
}

export interface RunsData {
  total: number;
  by_status: Record<string, number>;
  by_priority: Record<string, number>;
  trend: RunTrendPoint[];
}

export type RunsReport = ReportEnvelope<RunsData>;

export const getRunsReport = (params: ReportParams): Promise<RunsReport> =>
  api.get<RunsReport>("/reports/runs", { params }).then((r) => r.data);

// ── Queue report ──────────────────────────────────────────────────────────────

export interface QueuePoint {
  date: string;
  total_runs: number;
  dispatched: number;
  avg_wait_seconds: number | null;
  max_wait_seconds: number | null;
}

export type QueueReport = ReportEnvelope<QueuePoint[]>;

export const getQueueReport = (params: ReportParams): Promise<QueueReport> =>
  api.get<QueueReport>("/reports/queue", { params }).then((r) => r.data);

// ── Schedules report ──────────────────────────────────────────────────────────

export interface ScheduleReliability {
  job_id: string;
  job_name: string;
  total_fires: number;
  triggered: number;
  skipped: number;
  trigger_failed: number;
  missed: number;
  hit_rate: number;   // 0–1
  miss_rate: number;  // 0–1
}

export type SchedulesReport = ReportEnvelope<ScheduleReliability[]>;

export const getSchedulesReport = (params: ReportParams): Promise<SchedulesReport> =>
  api.get<SchedulesReport>("/reports/schedules", { params }).then((r) => r.data);

// ── Agents report ─────────────────────────────────────────────────────────────

export interface AgentStats {
  agent_id: string;
  agent_name: string | null;
  run_count: number;
  passed: number;
  failed: number;
  avg_duration_seconds: number | null;
  p95_duration_seconds: number | null;
  // NOTE: utilization_percent intentionally absent — insufficient heartbeat data
}

export type AgentsReport = ReportEnvelope<AgentStats[]>;

export const getAgentsReport = (params: ReportParams): Promise<AgentsReport> =>
  api.get<AgentsReport>("/reports/agents", { params }).then((r) => r.data);

// ── Flakiness report ──────────────────────────────────────────────────────────

export interface FlakyTest {
  test_case_id: string;
  test_case_name: string | null;
  runs: number;
  passed: number;
  failed: number;
  flip_count: number;
  flakiness_score: number;   // 0–1 float
}

export interface FlakinessParams extends ReportParams {
  min_score?: number;
}

export type FlakinessReport = ReportEnvelope<FlakyTest[]>;

export const getFlakinessReport = (params: FlakinessParams): Promise<FlakinessReport> =>
  api.get<FlakinessReport>("/reports/flakiness", { params }).then((r) => r.data);

// ── Pass rate report ──────────────────────────────────────────────────────────

export interface PassRatePoint {
  date: string;
  total: number;
  passed: number;
  failed: number;
  pass_rate: number | null;  // 0–1 float, null if no terminal runs
}

export interface PassRateParams extends ReportParams {
  test_case_id?: string;
}

export type PassRateReport = ReportEnvelope<PassRatePoint[]>;

export const getPassRateReport = (params: PassRateParams): Promise<PassRateReport> =>
  api.get<PassRateReport>("/reports/pass-rate", { params }).then((r) => r.data);

// ── Duration report ───────────────────────────────────────────────────────────

export interface DurationPoint {
  date: string;
  run_count: number;
  avg_duration_seconds: number | null;
  p95_duration_seconds: number | null;
}

export interface DurationParams extends ReportParams {
  test_case_id?: string;
}

export type DurationReport = ReportEnvelope<DurationPoint[]>;

export const getDurationReport = (params: DurationParams): Promise<DurationReport> =>
  api.get<DurationReport>("/reports/duration", { params }).then((r) => r.data);
