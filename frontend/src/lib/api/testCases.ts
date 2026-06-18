/**
 * lib/api/testCases.ts — Phase 2 Test Case Management API client
 *
 * Typed Axios wrappers for all 19 endpoints.
 * Re-exports all types used by the UI.
 */

import api from "../api";

// ── Enums (match backend) ─────────────────────────────────────────────────

export type SuiteStatus  = "ACTIVE" | "ARCHIVED";
export type TestStatus   = "DRAFT" | "READY" | "BLOCKED" | "DEPRECATED";
export type TestPriority = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
export type StepAction =
  | "CLICK" | "DOUBLE_CLICK" | "RIGHT_CLICK"
  | "TYPE" | "APPEND" | "CLEAR"
  | "SELECT" | "CHECK" | "UNCHECK"
  | "HOVER" | "SCROLL_TO" | "WAIT_FOR"
  | "NAVIGATE" | "SCREENSHOT" | "EXECUTE_SCRIPT"
  | "DRAG_DROP" | "UPLOAD_FILE" | "PRESS_KEY";

export type AssertionType =
  | "VISIBLE" | "NOT_VISIBLE"
  | "TEXT_EQUALS" | "TEXT_CONTAINS" | "TEXT_MATCHES"
  | "VALUE_EQUALS" | "ATTRIBUTE_EQUALS"
  | "URL_EQUALS" | "URL_CONTAINS" | "TITLE_EQUALS"
  | "ELEMENT_COUNT" | "ENABLED" | "DISABLED"
  | "CHECKED" | "UNCHECKED";

// ── Read types ────────────────────────────────────────────────────────────

export interface TestSuiteRead {
  id: string;
  org_id: string;
  name: string;
  description: string | null;
  status: SuiteStatus;
  tags: string[] | null;
  owner_user_id: string | null;
  owner_team: string | null;
  created_by: string | null;
  created_at: string;
  updated_by: string | null;
  updated_at: string;
  case_count: number;
}

export interface StepAssertionRead {
  id: string;
  org_id: string;
  step_id: string;
  position: number;
  assertion_type: AssertionType;
  target_page_object_id: string | null;
  expected_value: string | null;
  attribute_name: string | null;
  is_negated: boolean;
  is_fatal: boolean;
  is_enabled: boolean;
  created_by: string | null;
  created_at: string;
  updated_by: string | null;
  updated_at: string;
}

export interface TestStepRead {
  id: string;
  org_id: string;
  test_case_id: string;
  position: number;
  action: StepAction;
  version: number;
  page_object_id: string | null;
  input_value: string | null;
  target_url: string | null;
  description: string | null;
  is_optional: boolean;
  is_enabled: boolean;
  timeout_ms: number;
  screenshot_on_failure: boolean;
  execution_hint: Record<string, unknown> | null;
  step_metadata: Record<string, unknown> | null;
  assertions: StepAssertionRead[];
  created_by: string | null;
  created_at: string;
  updated_by: string | null;
  updated_at: string;
}

export interface TestCaseSummary {
  id: string;
  org_id: string;
  suite_id: string | null;
  application_id: string | null;
  name: string;
  priority: TestPriority;
  status: TestStatus;
  version: number;
  tags: string[] | null;
  estimated_duration_secs: number | null;
  owner_user_id: string | null;
  owner_team: string | null;
  created_by: string | null;
  created_at: string;
  updated_by: string | null;
  updated_at: string;
}

export interface TestCaseRead extends TestCaseSummary {
  description: string | null;
  preconditions: string | null;
  postconditions: string | null;
  steps: TestStepRead[];
}

// ── Create / Update payloads ──────────────────────────────────────────────

export interface TestSuiteCreate {
  name: string;
  description?: string;
  status?: SuiteStatus;
  tags?: string[];
  owner_user_id?: string;
  owner_team?: string;
}

export interface TestSuiteUpdate extends Partial<TestSuiteCreate> {}

export interface TestCaseCreate {
  name: string;
  description?: string;
  suite_id?: string;
  application_id?: string;
  priority?: TestPriority;
  status?: TestStatus;
  tags?: string[];
  estimated_duration_secs?: number;
  preconditions?: string;
  postconditions?: string;
  owner_user_id?: string;
  owner_team?: string;
}

export interface TestCaseUpdate extends Partial<Omit<TestCaseCreate, "name">> {
  version: number; // required for optimistic locking
  name?: string;
}

export interface TestStepCreate {
  action: StepAction;
  page_object_id?: string;
  input_value?: string;
  target_url?: string;
  description?: string;
  is_optional?: boolean;
  is_enabled?: boolean;
  timeout_ms?: number;
  screenshot_on_failure?: boolean;
  execution_hint?: Record<string, unknown>;
  step_metadata?: Record<string, unknown>;
}

export interface TestStepUpdate extends Partial<TestStepCreate> {}

export interface StepAssertionCreate {
  assertion_type: AssertionType;
  target_page_object_id?: string;
  expected_value?: string;
  attribute_name?: string;
  is_negated?: boolean;
  is_fatal?: boolean;
  is_enabled?: boolean;
}

export interface StepAssertionUpdate extends Partial<StepAssertionCreate> {}

export interface StepReorderRequest {
  step_ids: string[];
}

// ── API functions ─────────────────────────────────────────────────────────

export const suitesApi = {
  list:   (params?: { status?: string; offset?: number; limit?: number }) =>
    api.get<TestSuiteRead[]>("/suites", { params }),
  get:    (id: string) => api.get<TestSuiteRead>(`/suites/${id}`),
  create: (body: TestSuiteCreate) => api.post<TestSuiteRead>("/suites", body),
  update: (id: string, body: TestSuiteUpdate) => api.put<TestSuiteRead>(`/suites/${id}`, body),
  delete: (id: string) => api.delete(`/suites/${id}`),
  cases:  (id: string, params?: { offset?: number; limit?: number }) =>
    api.get<TestCaseSummary[]>(`/suites/${id}/cases`, { params }),
};

export const casesApi = {
  list:   (params?: {
    status?: string; priority?: string;
    suite_id?: string; application_id?: string;
    offset?: number; limit?: number;
  }) => api.get<TestCaseSummary[]>("/cases", { params }),
  search: (q: string, params?: { offset?: number; limit?: number }) =>
    api.get<TestCaseSummary[]>("/cases/search", { params: { q, ...params } }),
  get:    (id: string) => api.get<TestCaseRead>(`/cases/${id}`),
  create: (body: TestCaseCreate) => api.post<TestCaseSummary>("/cases", body),
  update: (id: string, body: TestCaseUpdate) => api.put<TestCaseSummary>(`/cases/${id}`, body),
  delete: (id: string) => api.delete(`/cases/${id}`),
  addStep:    (caseId: string, body: TestStepCreate) =>
    api.post<TestStepRead>(`/cases/${caseId}/steps`, body),
  reorderSteps: (caseId: string, body: StepReorderRequest) =>
    api.put<TestStepRead[]>(`/cases/${caseId}/steps/reorder`, body),
};

export const stepsApi = {
  update: (id: string, body: TestStepUpdate) => api.put<TestStepRead>(`/steps/${id}`, body),
  delete: (id: string) => api.delete(`/steps/${id}`),
  addAssertion: (stepId: string, body: StepAssertionCreate) =>
    api.post<StepAssertionRead>(`/steps/${stepId}/assertions`, body),
};

export const assertionsApi = {
  update: (id: string, body: StepAssertionUpdate) =>
    api.put<StepAssertionRead>(`/assertions/${id}`, body),
  delete: (id: string) => api.delete(`/assertions/${id}`),
};
