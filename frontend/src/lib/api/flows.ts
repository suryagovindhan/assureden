/**
 * lib/api/flows.ts — Phase 3: Flows & Flow Steps API client
 */
import api from "../api";

async function apiRequest<T>(url: string, opts?: { method?: string; body?: unknown }): Promise<T> {
  const method = (opts?.method ?? "GET").toUpperCase();
  const res = method === "GET" || method === "DELETE"
    ? await api.request<T>({ method, url })
    : await api.request<T>({ method, url, data: opts?.body });
  return res.data;
}

export interface FlowStep {
  id: string;
  flow_id: string;
  position: number;
  version: number;
  action: string;
  input_value: string | null;
  target_url: string | null;
  description: string | null;
  timeout_ms: number;
  is_optional: boolean;
  is_enabled: boolean;
  page_object_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface Flow {
  id: string;
  org_id: string;
  name: string;
  description: string | null;
  tags: string[];
  version: number;
  checksum: string;
  created_from_flow_id: string | null;
  created_from_version: number | null;
  created_at: string;
  updated_at: string;
  created_by: string | null;
  steps?: FlowStep[];
}

export interface PaginatedFlows {
  items: Flow[];
  total: number;
}

// ── Flows ─────────────────────────────────────────────────────────────────────

export const listFlows = (params?: { search?: string; offset?: number; limit?: number }) => {
  const qs = new URLSearchParams();
  if (params?.search) qs.set("search", params.search);
  if (params?.offset !== undefined) qs.set("offset", String(params.offset));
  if (params?.limit !== undefined) qs.set("limit", String(params.limit));
  return apiRequest<PaginatedFlows>(`/flows?${qs.toString()}`);
};

export const getFlow = (id: string) => apiRequest<Flow>(`/flows/${id}`);

export const createFlow = (body: { name: string; description?: string; tags?: string[] }) =>
  apiRequest<Flow>("/flows", { method: "POST", body });

export const updateFlow = (
  id: string,
  body: { expected_version: number; name?: string; description?: string; tags?: string[] }
) => apiRequest<Flow>(`/flows/${id}`, { method: "PUT", body });

export const deleteFlow = (id: string) =>
  apiRequest<void>(`/flows/${id}`, { method: "DELETE" });

export const duplicateFlow = (id: string, new_name: string) =>
  apiRequest<Flow>(`/flows/${id}/duplicate`, { method: "POST", body: { new_name } });

// ── Flow Steps ────────────────────────────────────────────────────────────────

export const createFlowStep = (
  flowId: string,
  body: {
    action: string;
    input_value?: string;
    target_url?: string;
    description?: string;
    timeout_ms?: number;
    is_optional?: boolean;
    is_enabled?: boolean;
    page_object_id?: string;
  }
) => apiRequest<FlowStep>(`/flows/${flowId}/steps`, { method: "POST", body });

export const updateFlowStep = (
  stepId: string,
  body: Partial<{
    action: string;
    input_value: string;
    target_url: string;
    description: string;
    timeout_ms: number;
    is_optional: boolean;
    is_enabled: boolean;
    page_object_id: string;
  }>
) => apiRequest<FlowStep>(`/flows/steps/${stepId}`, { method: "PUT", body });

export const deleteFlowStep = (stepId: string) =>
  apiRequest<void>(`/flows/steps/${stepId}`, { method: "DELETE" });

export const reorderFlowSteps = (flowId: string, step_ids: string[]) =>
  apiRequest<FlowStep[]>(`/flows/${flowId}/steps/reorder`, { method: "PUT", body: { step_ids } });
