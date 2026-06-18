/**
 * lib/api/objectRepository.ts — Phase 1 Object Repository API client
 *
 * All endpoints are org-scoped server-side. org_id is injected from the JWT.
 * The client never needs to pass org_id explicitly.
 */

import api from "../api"; // existing Axios instance with auth interceptors

// ─── Types ─────────────────────────────────────────────────────────────────

export type ObjectStatus = "ACTIVE" | "DEPRECATED" | "ARCHIVED";
export type POStatus = "DRAFT" | "ACTIVE" | "DEPRECATED" | "ARCHIVED";
export type ObjectType =
  | "INPUT" | "BUTTON" | "LINK" | "DROPDOWN" | "CHECKBOX" | "RADIO"
  | "TABLE" | "CONTAINER" | "TEXT" | "IFRAME" | "DATE_PICKER" | "FILE_UPLOAD";
export type PageArea = "HEADER" | "BODY" | "FOOTER" | "MODAL" | "SIDEBAR" | "NAVIGATION";
export type Criticality = "HIGH" | "MEDIUM" | "LOW";
export type LocatorType = "CSS_SELECTOR" | "XPATH" | "ID" | "ARIA_LABEL" | "TEST_ID" | "TEXT";

export interface Locator {
  type: LocatorType;
  value: string;
  priority: number;
  is_primary: boolean;
  is_active: boolean;
  added_by: "MANUAL" | "RECORDER";
  added_at?: string;
  notes?: string | null;
}

export interface Application {
  id: string;
  org_id: string;
  name: string;
  description?: string;
  status: ObjectStatus;
  tags?: string[];
  owner_user_id?: string;
  owner_team?: string;
  created_by?: string;
  created_at: string;
  updated_at: string;
}

export interface Module {
  id: string;
  org_id: string;
  application_id: string;
  name: string;
  description?: string;
  status: ObjectStatus;
  tags?: string[];
  owner_user_id?: string;
  owner_team?: string;
  created_at: string;
  updated_at: string;
}

export interface Page {
  id: string;
  org_id: string;
  module_id: string;
  name: string;
  description?: string;
  url_pattern?: string;
  status: ObjectStatus;
  tags?: string[];
  owner_user_id?: string;
  owner_team?: string;
  created_at: string;
  updated_at: string;
}

export interface PageObject {
  id: string;
  org_id: string;
  page_id: string;
  name: string;
  description?: string;
  object_type: ObjectType;
  page_area?: PageArea;
  criticality: Criticality;
  status: POStatus;
  locators: Locator[];
  search_keywords?: string[];
  tags?: string[];
  owner_user_id?: string;
  owner_team?: string;
  last_validated_at?: string;
  last_validated_by?: string;
  created_at: string;
  updated_at: string;
}

export interface PageObjectSnapshot {
  id: string;
  org_id: string;
  page_object_id: string;
  storage_provider: string;
  object_key: string;
  snapshot_metadata?: Record<string, unknown>;
  bounding_box?: { x: number; y: number; width: number; height: number };
  capture_url?: string;
  captured_by?: string;
  created_at: string;
}

export interface PageObjectSearchResult {
  id: string;
  name: string;
  object_type: ObjectType;
  page_area?: PageArea;
  criticality: Criticality;
  status: POStatus;
  tags?: string[];
  application_id: string;
  application_name: string;
  module_id: string;
  module_name: string;
  page_id: string;
  page_name: string;
}

export interface Paginated<T> {
  items: T[];
  total: number;
  offset: number;
  limit: number;
}

export interface SearchResponse extends Paginated<PageObjectSearchResult> {
  query: string;
}

// ─── Applications ───────────────────────────────────────────────────────────

export const appsApi = {
  list: (params?: { offset?: number; limit?: number; status?: string }) =>
    api.get<Paginated<Application>>("/object-repository/applications", { params }).then((r) => r.data),

  get: (id: string) =>
    api.get<Application>(`/object-repository/applications/${id}`).then((r) => r.data),

  create: (body: { name: string; description?: string; status?: string; tags?: string[]; owner_team?: string }) =>
    api.post<Application>("/object-repository/applications", body).then((r) => r.data),

  update: (id: string, body: Partial<{ name: string; description: string; status: string; tags: string[]; owner_team: string }>) =>
    api.put<Application>(`/object-repository/applications/${id}`, body).then((r) => r.data),

  delete: (id: string) =>
    api.delete(`/object-repository/applications/${id}`),
};

// ─── Modules ─────────────────────────────────────────────────────────────────

export const modulesApi = {
  listByApp: (appId: string, params?: { offset?: number; limit?: number }) =>
    api.get<Paginated<Module>>(`/object-repository/applications/${appId}/modules`, { params }).then((r) => r.data),

  get: (id: string) =>
    api.get<Module>(`/object-repository/modules/${id}`).then((r) => r.data),

  create: (appId: string, body: { name: string; description?: string; status?: string; tags?: string[] }) =>
    api.post<Module>(`/object-repository/applications/${appId}/modules`, body).then((r) => r.data),

  update: (id: string, body: Partial<{ name: string; description: string; status: string; tags: string[] }>) =>
    api.put<Module>(`/object-repository/modules/${id}`, body).then((r) => r.data),

  delete: (id: string) =>
    api.delete(`/object-repository/modules/${id}`),
};

// ─── Pages ───────────────────────────────────────────────────────────────────

export const pagesApi = {
  listByModule: (moduleId: string, params?: { offset?: number; limit?: number }) =>
    api.get<Paginated<Page>>(`/object-repository/modules/${moduleId}/pages`, { params }).then((r) => r.data),

  get: (id: string) =>
    api.get<Page>(`/object-repository/pages/${id}`).then((r) => r.data),

  create: (moduleId: string, body: { name: string; description?: string; url_pattern?: string; status?: string }) =>
    api.post<Page>(`/object-repository/modules/${moduleId}/pages`, body).then((r) => r.data),

  update: (id: string, body: Partial<{ name: string; description: string; url_pattern: string; status: string }>) =>
    api.put<Page>(`/object-repository/pages/${id}`, body).then((r) => r.data),

  delete: (id: string) =>
    api.delete(`/object-repository/pages/${id}`),
};

// ─── PageObjects ──────────────────────────────────────────────────────────────

export const pageObjectsApi = {
  listByPage: (pageId: string, params?: { offset?: number; limit?: number; status?: string }) =>
    api.get<Paginated<PageObject>>(`/object-repository/pages/${pageId}/objects`, { params }).then((r) => r.data),

  get: (id: string) =>
    api.get<PageObject>(`/object-repository/objects/${id}`).then((r) => r.data),

  create: (
    pageId: string,
    body: {
      name: string;
      object_type: ObjectType;
      description?: string;
      page_area?: PageArea;
      criticality?: Criticality;
      status?: POStatus;
      locators?: Locator[];
      search_keywords?: string[];
      tags?: string[];
    }
  ) =>
    api.post<PageObject>(`/object-repository/pages/${pageId}/objects`, body).then((r) => r.data),

  update: (id: string, body: Partial<PageObject & { locators: Locator[] }>) =>
    api.put<PageObject>(`/object-repository/objects/${id}`, body).then((r) => r.data),

  delete: (id: string) =>
    api.delete(`/object-repository/objects/${id}`),

  search: (q: string, params?: { offset?: number; limit?: number }) =>
    api
      .get<SearchResponse>("/object-repository/objects/search", { params: { q, ...params } })
      .then((r) => r.data),
};

// ─── Snapshots ────────────────────────────────────────────────────────────────

export const snapshotsApi = {
  list: (poId: string, params?: { offset?: number; limit?: number }) =>
    api.get<Paginated<PageObjectSnapshot>>(`/object-repository/objects/${poId}/snapshots`, { params }).then((r) => r.data),

  create: (
    poId: string,
    body: {
      storage_provider: string;
      object_key: string;
      snapshot_metadata?: Record<string, unknown>;
      bounding_box?: { x: number; y: number; width: number; height: number };
      capture_url?: string;
    }
  ) =>
    api.post<PageObjectSnapshot>(`/object-repository/objects/${poId}/snapshots`, body).then((r) => r.data),
};
