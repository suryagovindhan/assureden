/**
 * lib/api/environments.ts — Phase 3: Environments & Variables API client
 */
import api from "../api";

async function apiRequest<T>(url: string, opts?: { method?: string; body?: unknown }): Promise<T> {
  const method = (opts?.method ?? "GET").toUpperCase();
  const res = method === "GET" || method === "DELETE"
    ? await api.request<T>({ method, url })
    : await api.request<T>({ method, url, data: opts?.body });
  return res.data;
}

export interface Environment {
  id: string;
  org_id: string;
  name: string;
  description: string | null;
  base_url: string | null;
  tags: string[];
  version: number;
  is_default: boolean;
  created_at: string;
  updated_at: string;
  created_by: string | null;
  updated_by: string | null;
}

export interface EnvironmentVariable {
  id: string;
  environment_id: string;
  key: string;
  value: string;       // always masked (****) for secrets
  type: string;
  is_secret: boolean;
  description: string | null;
  key_id: string;
  created_at: string;
}

export interface PaginatedEnvironments {
  items: Environment[];
  total: number;
}

// ── Environments ─────────────────────────────────────────────────────────────

export const listEnvironments = (params?: { offset?: number; limit?: number }) =>
  apiRequest<PaginatedEnvironments>(
    `/environments/?offset=${params?.offset ?? 0}&limit=${params?.limit ?? 100}`
  );

export const getEnvironment = (id: string) =>
  apiRequest<Environment & { variables?: EnvironmentVariable[] }>(`/environments/${id}`);

export const createEnvironment = (body: {
  name: string;
  description?: string;
  base_url?: string;
  tags?: string[];
  is_default?: boolean;
}) => apiRequest<Environment>("/environments/", { method: "POST", body });

export const updateEnvironment = (
  id: string,
  body: { expected_version: number; name?: string; description?: string; base_url?: string; tags?: string[]; is_default?: boolean }
) => apiRequest<Environment>(`/environments/${id}`, { method: "PUT", body });

export const deleteEnvironment = (id: string) =>
  apiRequest<void>(`/environments/${id}`, { method: "DELETE" });

// ── Variables ─────────────────────────────────────────────────────────────────

export const listVariables = (envId: string) =>
  apiRequest<EnvironmentVariable[]>(`/environments/${envId}/variables`);

export const createVariable = (
  envId: string,
  body: { key: string; value: string; type?: string; is_secret?: boolean; description?: string }
) => apiRequest<EnvironmentVariable>(`/environments/${envId}/variables`, { method: "POST", body });

export const updateVariable = (
  envId: string,
  varId: string,
  body: { value?: string; type?: string; is_secret?: boolean; description?: string }
) => apiRequest<EnvironmentVariable>(`/environments/${envId}/variables/${varId}`, { method: "PUT", body });

export const deleteVariable = (envId: string, varId: string) =>
  apiRequest<void>(`/environments/${envId}/variables/${varId}`, { method: "DELETE" });
