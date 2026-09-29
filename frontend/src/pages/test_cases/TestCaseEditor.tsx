/**
 * TestCaseEditor.tsx — /test-cases/:case_id
 *
 * Three-panel layout:
 *   Left:   Step list (ordered, move up/down, is_enabled toggle, delete)
 *   Center: Step detail form (action, PO picker, input, metadata)
 *   Right:  Assertion panel for selected step
 *
 * Version tracked — 409 conflicts show inline alert with reload prompt.
 */

import { useState, useEffect, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  Box, Typography, Chip, Button, IconButton, TextField,
  Select, MenuItem, FormControl, InputLabel, Switch, FormControlLabel,
  Tooltip, CircularProgress, Alert, Skeleton,
} from "@mui/material";
import {
  ArrowUpward, ArrowDownward, Delete as DeleteIcon, Add as AddIcon,
  Save as SaveIcon, ArrowBack, ToggleOn, ToggleOff, DragIndicator,
} from "@mui/icons-material";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  casesApi, stepsApi, assertionsApi,
  type TestCaseRead, type TestStepRead, type StepAssertionRead,
  type StepAction, type AssertionType,
} from "../../lib/api/testCases";
import PageObjectPicker, { type PickedPageObject } from "./PageObjectPicker";
import { listFlows, listFlowRevisions } from "../../lib/api/flows";
import RunTestButton from "../../components/RunTestButton";

const ACTIONS: StepAction[] = [
  "FLOW",
  "CLICK", "DOUBLE_CLICK", "RIGHT_CLICK", "TYPE", "APPEND", "CLEAR",
  "SELECT", "CHECK", "UNCHECK", "HOVER", "SCROLL_TO", "WAIT_FOR",
  "NAVIGATE", "SCREENSHOT", "EXECUTE_SCRIPT", "DRAG_DROP", "UPLOAD_FILE", "PRESS_KEY",
];

const ASSERTION_TYPES: AssertionType[] = [
  "VISIBLE", "NOT_VISIBLE", "TEXT_EQUALS", "TEXT_CONTAINS", "TEXT_MATCHES",
  "VALUE_EQUALS", "ATTRIBUTE_EQUALS", "URL_EQUALS", "URL_CONTAINS",
  "TITLE_EQUALS", "ELEMENT_COUNT", "ENABLED", "DISABLED", "CHECKED", "UNCHECKED",
];

const STATUS_COLORS: Record<string, string> = {
  DRAFT: "#64748b", READY: "#22c55e", BLOCKED: "#ef4444", DEPRECATED: "#94a3b8",
};
const PRIORITY_COLORS: Record<string, string> = {
  CRITICAL: "#ef4444", HIGH: "#f97316", MEDIUM: "#f59e0b", LOW: "#22c55e",
};

// ─── Step list panel ─────────────────────────────────────────────────────────

function StepListPanel({
  steps,
  selectedId,
  onSelect,
  onMoveUp,
  onMoveDown,
  onDelete,
  onAdd,
  reordering,
}: {
  steps: TestStepRead[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  onMoveUp: (id: string) => void;
  onMoveDown: (id: string) => void;
  onDelete: (id: string) => void;
  onAdd: () => void;
  reordering: boolean;
}) {
  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <Box sx={{ p: 1.5, borderBottom: "1px solid rgba(255,255,255,0.06)" }}>
        <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <Typography variant="caption" sx={{ color: "#94a3b8", textTransform: "uppercase", letterSpacing: 1, fontSize: 10 }}>
            Steps ({steps.length})
          </Typography>
          <IconButton size="small" onClick={onAdd} sx={{ color: "#818cf8" }}>
            <AddIcon fontSize="small" />
          </IconButton>
        </Box>
      </Box>

      <Box sx={{ flex: 1, overflowY: "auto" }}>
        {steps.length === 0 && (
          <Box sx={{ p: 2, textAlign: "center" }}>
            <Typography variant="caption" sx={{ color: "#475569" }}>No steps yet</Typography>
            <br />
            <Button size="small" onClick={onAdd} sx={{ color: "#818cf8", mt: 0.5 }}>+ Add First Step</Button>
          </Box>
        )}
        {steps.map((step, idx) => (
          <Box
            key={step.id}
            onClick={() => onSelect(step.id)}
            sx={{
              px: 1.5, py: 1, borderBottom: "1px solid rgba(255,255,255,0.04)",
              cursor: "pointer", display: "flex", alignItems: "center", gap: 0.5,
              bgcolor: selectedId === step.id ? "rgba(99,102,241,0.14)" : "transparent",
              opacity: step.is_enabled ? 1 : 0.45,
              "&:hover": { bgcolor: selectedId === step.id ? "rgba(99,102,241,0.18)" : "rgba(255,255,255,0.03)" },
              transition: "background 0.12s",
            }}
          >
            <DragIndicator sx={{ fontSize: 14, color: "#334155", flexShrink: 0 }} />
            <Chip
              label={idx + 1}
              size="small"
              sx={{ bgcolor: "rgba(255,255,255,0.06)", color: "#94a3b8", fontSize: 9, height: 16, minWidth: 20, flexShrink: 0 }}
            />
            <Box sx={{ flex: 1, minWidth: 0 }}>
              <Typography variant="caption" sx={{ color: "#e2e8f0", fontWeight: selectedId === step.id ? 700 : 400 }} noWrap>
                {step.action}
              </Typography>
              {step.description && (
                <Typography variant="caption" sx={{ color: "#64748b", display: "block" }} noWrap>
                  {step.description}
                </Typography>
              )}
            </Box>
            <Box sx={{ display: "flex", flexDirection: "column" }}>
              <IconButton size="small" disabled={idx === 0 || reordering}
                onClick={(e) => { e.stopPropagation(); onMoveUp(step.id); }}
                sx={{ p: 0.2, color: "#334155", "&:hover": { color: "#818cf8" } }}>
                <ArrowUpward sx={{ fontSize: 12 }} />
              </IconButton>
              <IconButton size="small" disabled={idx === steps.length - 1 || reordering}
                onClick={(e) => { e.stopPropagation(); onMoveDown(step.id); }}
                sx={{ p: 0.2, color: "#334155", "&:hover": { color: "#818cf8" } }}>
                <ArrowDownward sx={{ fontSize: 12 }} />
              </IconButton>
            </Box>
          </Box>
        ))}
      </Box>
    </Box>
  );
}

// ─── Assertion panel ──────────────────────────────────────────────────────────

function AssertionPanel({
  step, onRefresh,
}: {
  step: TestStepRead;
  onRefresh: () => void;
}) {
  const [addOpen, setAddOpen] = useState(false);
  const [newType, setNewType] = useState<AssertionType>("VISIBLE");
  const [newValue, setNewValue] = useState("");
  const [newAttr, setNewAttr] = useState("");
  const [isNegated, setIsNegated] = useState(false);
  const [isFatal, setIsFatal] = useState(true);

  const { mutate: addAssertion, isPending: adding } = useMutation({
    mutationFn: () =>
      stepsApi.addAssertion(step.id, {
        assertion_type: newType,
        expected_value: newValue || undefined,
        attribute_name: newAttr || undefined,
        is_negated: isNegated,
        is_fatal: isFatal,
      }),
    onSuccess: () => {
      onRefresh();
      setAddOpen(false);
      setNewValue("");
      setNewAttr("");
      setIsNegated(false);
      setIsFatal(true);
    },
  });

  const { mutate: disableAssertion } = useMutation({
    mutationFn: (a: StepAssertionRead) => assertionsApi.update(a.id, { is_enabled: !a.is_enabled }),
    onSuccess: onRefresh,
  });

  const { mutate: deleteAssertion } = useMutation({
    mutationFn: (id: string) => assertionsApi.delete(id),
    onSuccess: onRefresh,
  });

  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%", p: 1.5 }}>
      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 1 }}>
        <Typography variant="caption" sx={{ color: "#94a3b8", textTransform: "uppercase", letterSpacing: 1, fontSize: 10 }}>
          Assertions ({step.assertions.length})
        </Typography>
        <IconButton size="small" onClick={() => setAddOpen(true)} sx={{ color: "#818cf8" }}>
          <AddIcon fontSize="small" />
        </IconButton>
      </Box>

      {step.assertions.length === 0 && !addOpen && (
        <Box sx={{ textAlign: "center", pt: 3 }}>
          <Typography variant="caption" sx={{ color: "#475569" }}>No assertions for this step</Typography>
          <br />
          <Button size="small" onClick={() => setAddOpen(true)} sx={{ color: "#818cf8", mt: 0.5 }}>+ Add Assertion</Button>
        </Box>
      )}

      {addOpen && (
        <Box sx={{ mb: 1.5, p: 1.5, border: "1px solid rgba(99,102,241,0.3)", borderRadius: 2, bgcolor: "rgba(99,102,241,0.05)" }}>
          <FormControl fullWidth size="small" sx={{ mb: 1 }}>
            <InputLabel sx={{ color: "#64748b" }}>Type</InputLabel>
            <Select value={newType} onChange={(e) => setNewType(e.target.value as AssertionType)} label="Type"
              sx={{ color: "#e2e8f0", "& .MuiOutlinedInput-notchedOutline": { borderColor: "rgba(255,255,255,0.12)" } }}>
              {ASSERTION_TYPES.map((t) => <MenuItem key={t} value={t} sx={{ color: "#e2e8f0" }}>{t}</MenuItem>)}
            </Select>
          </FormControl>
          {!["VISIBLE", "NOT_VISIBLE", "ENABLED", "DISABLED", "CHECKED", "UNCHECKED"].includes(newType) && (
            <TextField fullWidth size="small" label="Expected value" value={newValue} onChange={(e) => setNewValue(e.target.value)} placeholder="{{VARIABLE}} supported"
              sx={{ mb: 1, input: { color: "#e2e8f0" }, "& .MuiInputLabel-root": { color: "#64748b" }, "& .MuiOutlinedInput-notchedOutline": { borderColor: "rgba(255,255,255,0.12)" } }} />
          )}
          {newType === "ATTRIBUTE_EQUALS" && (
            <TextField fullWidth size="small" label="Attribute name" value={newAttr} onChange={(e) => setNewAttr(e.target.value)}
              sx={{ mb: 1, input: { color: "#e2e8f0" }, "& .MuiInputLabel-root": { color: "#64748b" }, "& .MuiOutlinedInput-notchedOutline": { borderColor: "rgba(255,255,255,0.12)" } }} />
          )}
          <Box sx={{ display: "flex", gap: 1, mb: 1 }}>
            <FormControlLabel
              control={<Switch size="small" checked={isNegated} onChange={(e) => setIsNegated(e.target.checked)} />}
              label={<Typography variant="caption" sx={{ color: "#94a3b8" }}>Negate</Typography>}
            />
            <FormControlLabel
              control={<Switch size="small" checked={isFatal} onChange={(e) => setIsFatal(e.target.checked)} />}
              label={<Typography variant="caption" sx={{ color: "#94a3b8" }}>Fatal</Typography>}
            />
          </Box>
          <Box sx={{ display: "flex", gap: 1 }}>
            <Button size="small" onClick={() => setAddOpen(false)} sx={{ color: "#64748b" }}>Cancel</Button>
            <Button size="small" variant="contained" disabled={adding} onClick={() => addAssertion()}
              sx={{ background: "linear-gradient(135deg,#6366f1,#8b5cf6)" }}>
              {adding ? "Adding…" : "Add"}
            </Button>
          </Box>
        </Box>
      )}

      <Box sx={{ flex: 1, overflowY: "auto" }}>
        {step.assertions.map((a) => (
          <Box key={a.id} sx={{
            mb: 0.75, p: 1.25, borderRadius: 1.5, border: "1px solid rgba(255,255,255,0.06)",
            bgcolor: a.is_enabled ? "rgba(255,255,255,0.02)" : "rgba(255,255,255,0.01)",
            opacity: a.is_enabled ? 1 : 0.5,
          }}>
            <Box sx={{ display: "flex", alignItems: "flex-start", gap: 0.5 }}>
              <Box sx={{ flex: 1 }}>
                <Box sx={{ display: "flex", gap: 0.5, flexWrap: "wrap", alignItems: "center" }}>
                  <Chip label={a.is_negated ? `NOT ${a.assertion_type}` : a.assertion_type} size="small"
                    sx={{ bgcolor: "rgba(99,102,241,0.15)", color: "#a5b4fc", fontSize: 10, height: 18 }} />
                  {!a.is_fatal && <Chip label="warn" size="small" sx={{ bgcolor: "rgba(245,158,11,0.15)", color: "#f59e0b", fontSize: 10, height: 18 }} />}
                  {!a.is_enabled && <Chip label="disabled" size="small" sx={{ bgcolor: "rgba(100,116,139,0.15)", color: "#64748b", fontSize: 10, height: 18 }} />}
                </Box>
                {a.expected_value && (
                  <Typography variant="caption" sx={{ color: "#64748b", mt: 0.3, display: "block", fontFamily: "monospace" }}>
                    = {a.expected_value}
                  </Typography>
                )}
              </Box>
              <Tooltip title={a.is_enabled ? "Disable assertion" : "Enable assertion"}>
                <IconButton size="small" onClick={() => disableAssertion(a)}
                  sx={{ color: a.is_enabled ? "#22c55e" : "#475569", p: 0.3 }}>
                  {a.is_enabled ? <ToggleOn sx={{ fontSize: 18 }} /> : <ToggleOff sx={{ fontSize: 18 }} />}
                </IconButton>
              </Tooltip>
              <Tooltip title="Soft-delete assertion">
                <IconButton size="small" onClick={() => deleteAssertion(a.id)} sx={{ color: "#475569", p: 0.3, "&:hover": { color: "#ef4444" } }}>
                  <DeleteIcon sx={{ fontSize: 14 }} />
                </IconButton>
              </Tooltip>
            </Box>
          </Box>
        ))}
      </Box>
    </Box>
  );
}

// ─── Main Editor ──────────────────────────────────────────────────────────────

type StepForm = {
  flow_id: string | null;
  flow_version: number | null;
  action: StepAction;
  input_value: string;
  target_url: string;
  description: string;
  is_optional: boolean;
  is_enabled: boolean;
  timeout_ms: number;
  page_object: PickedPageObject | null;
};

export default function TestCaseEditor() {
  const { case_id } = useParams<{ case_id: string }>();
  const navigate = useNavigate();
  const qc = useQueryClient();

  const [selectedStepId, setSelectedStepId] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [stepForm, setStepForm] = useState<Partial<StepForm>>({});
  const [versionError, setVersionError] = useState<{ current: number; submitted: number } | null>(null);
  const { data: flows, isError: flowsError } = useQuery({
    queryKey: ["flow-picker"], queryFn: () => listFlows({ limit: 200 }),
    enabled: stepForm.action === "FLOW",
  });
  const { data: revisions, isError: revisionsError } = useQuery({
    queryKey: ["flow-revisions", stepForm.flow_id],
    queryFn: () => listFlowRevisions(stepForm.flow_id!),
    enabled: stepForm.action === "FLOW" && !!stepForm.flow_id,
  });

  const { data: tc, isLoading, error } = useQuery({
    queryKey: ["test-case", case_id],
    queryFn: () => casesApi.get(case_id!).then((r) => r.data),
    enabled: !!case_id,
    refetchOnWindowFocus: false,
  });

  const refresh = useCallback(() => qc.invalidateQueries({ queryKey: ["test-case", case_id] }), [qc, case_id]);

  // Populate step form when selection changes
  useEffect(() => {
    if (!tc || !selectedStepId) return;
    const step = tc.steps.find((s) => s.id === selectedStepId);
    if (step) {
      setStepForm({
        flow_id: step.flow_id,
        flow_version: step.flow_version,
        action: step.action as StepAction,
        input_value: step.input_value ?? "",
        target_url: step.target_url ?? "",
        description: step.description ?? "",
        is_optional: step.is_optional,
        is_enabled: step.is_enabled,
        timeout_ms: step.timeout_ms,
        page_object: step.page_object_id ? { id: step.page_object_id } as PickedPageObject : null,
      });
    }
  }, [selectedStepId, tc]);

  const { mutate: saveStep, isPending: savingStep } = useMutation({
    mutationFn: () => {
      setSaveError(null);
      if (!selectedStepId) return Promise.reject(new Error("No step selected"));
      return stepsApi.update(selectedStepId, {
        flow_id: stepForm.action === "FLOW" ? stepForm.flow_id : null,
        flow_version: stepForm.action === "FLOW" ? stepForm.flow_version : null,
        action: stepForm.action,
        input_value: stepForm.action === "FLOW" ? null : stepForm.input_value || null,
        target_url: stepForm.action === "FLOW" ? null : stepForm.target_url || null,
        description: stepForm.description || undefined,
        is_optional: stepForm.action === "FLOW" ? false : stepForm.is_optional,
        is_enabled: stepForm.is_enabled,
        timeout_ms: stepForm.action === "FLOW" ? 30000 : stepForm.timeout_ms,
        page_object_id: stepForm.action === "FLOW" ? null : stepForm.page_object?.id || null,
      });
    },
    onSuccess: refresh,
    onError: (err: any) => {
      const message = err?.response?.data?.detail;
      setSaveError(typeof message === "string" ? message : "Could not save this step. Check the selected flow and revision.");
      // Surface 409 VERSION_CONFLICT inline — prevents silent overwrite
      if (err?.response?.status === 409) {
        const detail = err.response.data?.detail ?? {};
        setVersionError({
          current: detail.current_version ?? 0,
          submitted: detail.submitted_version ?? 0,
        });
      }
    },
  });

  const { mutate: addStep } = useMutation({
    mutationFn: () => casesApi.addStep(case_id!, { action: "CLICK" }),
    onSuccess: (res) => { refresh(); setSelectedStepId(res.data.id); },
  });

  const { mutate: deleteStep } = useMutation({
    mutationFn: (id: string) => stepsApi.delete(id),
    onSuccess: () => { setSelectedStepId(null); refresh(); },
  });

  const { mutate: reorder, isPending: reordering } = useMutation({
    mutationFn: (ids: string[]) => casesApi.reorderSteps(case_id!, { step_ids: ids }),
    onSuccess: refresh,
  });

  const moveStep = (stepId: string, direction: "up" | "down") => {
    if (!tc) return;
    const ids = tc.steps.map((s) => s.id);
    const idx = ids.indexOf(stepId);
    if (direction === "up" && idx === 0) return;
    if (direction === "down" && idx === ids.length - 1) return;
    const newIds = [...ids];
    const swap = direction === "up" ? idx - 1 : idx + 1;
    [newIds[idx], newIds[swap]] = [newIds[swap], newIds[idx]];
    reorder(newIds);
  };

  const selectedStep = tc?.steps.find((s) => s.id === selectedStepId) ?? null;

  if (isLoading) return (
    <Box sx={{ p: 3 }}>
      <Skeleton height={40} sx={{ mb: 1, bgcolor: "rgba(255,255,255,0.05)" }} />
      <Skeleton height={300} sx={{ bgcolor: "rgba(255,255,255,0.05)" }} />
    </Box>
  );

  if (error || !tc) return (
    <Box sx={{ p: 3 }}>
      <Alert severity="error" sx={{ bgcolor: "rgba(239,68,68,0.1)", color: "#fca5a5" }}>
        Failed to load test case.
      </Alert>
    </Box>
  );

  const currentAction = stepForm.action ?? (selectedStep?.action as StepAction | undefined);

  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "calc(100vh - 64px)", bgcolor: "#0d0d1a" }}>
      {/* Top bar */}
      <Box sx={{ px: 2.5, py: 1.5, borderBottom: "1px solid rgba(255,255,255,0.06)", display: "flex", alignItems: "center", gap: 1.5 }}>
        <RunTestButton caseId={tc.id} />
        <IconButton size="small" onClick={() => navigate("/test-cases")} sx={{ color: "#64748b" }}>
          <ArrowBack fontSize="small" />
        </IconButton>
        <Box sx={{ flex: 1 }}>
          <Box sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap" }}>
            <Typography variant="h6" sx={{ color: "#e2e8f0", fontWeight: 700 }}>{tc.name}</Typography>
            <Chip label={`v${tc.version}`} size="small" sx={{ bgcolor: "rgba(255,255,255,0.06)", color: "#64748b", fontSize: 10 }} />
            <Chip label={tc.status} size="small" sx={{ bgcolor: `${STATUS_COLORS[tc.status]}22`, color: STATUS_COLORS[tc.status], fontSize: 10 }} />
            <Chip label={tc.priority} size="small" sx={{ bgcolor: `${PRIORITY_COLORS[tc.priority]}22`, color: PRIORITY_COLORS[tc.priority], fontSize: 10 }} />
          </Box>
          <Typography variant="caption" sx={{ color: "#475569" }}>
            {tc.steps.length} step{tc.steps.length !== 1 ? "s" : ""} · Updated {new Date(tc.updated_at).toLocaleDateString()}
          </Typography>
        </Box>
      </Box>

      {versionError && (
        <Alert
          severity="warning"
          sx={{ mx: 2, mt: 1, bgcolor: "rgba(245,158,11,0.1)", color: "#fcd34d" }}
          onClose={() => setVersionError(null)}
          action={<Button size="small" sx={{ color: "#fcd34d" }} onClick={() => { setVersionError(null); refresh(); }}>Reload</Button>}
        >
          This test case was modified by another user (version {versionError.current}). Reload to see latest version before editing.
        </Alert>
      )}

      {/* Three-panel body */}
      {saveError && <Alert severity="error" onClose={() => setSaveError(null)}>{saveError}</Alert>}
      <Box sx={{ flex: 1, display: "flex", overflow: "hidden" }}>
        {/* Panel 1: Steps */}
        <Box sx={{ width: 200, borderRight: "1px solid rgba(255,255,255,0.06)", overflow: "hidden" }}>
          <StepListPanel
            steps={tc.steps}
            selectedId={selectedStepId}
            onSelect={setSelectedStepId}
            onMoveUp={(id) => moveStep(id, "up")}
            onMoveDown={(id) => moveStep(id, "down")}
            onDelete={deleteStep}
            onAdd={() => addStep()}
            reordering={reordering}
          />
        </Box>

        {/* Panel 2: Step detail */}
        <Box sx={{ flex: 1, p: 2, overflowY: "auto" }}>
          {!selectedStep ? (
            <Box sx={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100%", flexDirection: "column", gap: 1 }}>
              <Typography sx={{ color: "#334155" }}>Select a step to edit, or</Typography>
              <Button onClick={() => addStep()} startIcon={<AddIcon />} sx={{ color: "#818cf8" }}>Add a step</Button>
            </Box>
          ) : (
            <Box>
              <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 2 }}>
                <Typography variant="subtitle2" sx={{ color: "#94a3b8", textTransform: "uppercase", letterSpacing: 1, fontSize: 11 }}>
                  Step {tc.steps.findIndex((s) => s.id === selectedStep.id) + 1} — v{selectedStep.version}
                </Typography>
                <Box sx={{ display: "flex", gap: 1 }}>
                  <Button size="small" color="error" startIcon={<DeleteIcon />}
                    onClick={() => deleteStep(selectedStep.id)}
                    sx={{ color: "#ef4444", "&:hover": { bgcolor: "rgba(239,68,68,0.1)" } }}>
                    Delete
                  </Button>
                  <Button size="small" variant="contained" startIcon={savingStep ? <CircularProgress size={12} color="inherit" /> : <SaveIcon />}
                    disabled={savingStep} onClick={() => saveStep()}
                    sx={{ background: "linear-gradient(135deg,#6366f1,#8b5cf6)" }}>
                    {savingStep ? "Saving…" : "Save Step"}
                  </Button>
                </Box>
              </Box>

              <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
                {/* Action */}
                <FormControl fullWidth size="small">
                  <InputLabel sx={{ color: "#64748b" }}>Action</InputLabel>
                  <Select value={currentAction ?? "CLICK"} label="Action"
                    onChange={(e) => setStepForm((f) => ({ ...f, action: e.target.value as StepAction }))}
                    sx={{ color: "#e2e8f0", bgcolor: "rgba(255,255,255,0.03)", "& .MuiOutlinedInput-notchedOutline": { borderColor: "rgba(255,255,255,0.12)" } }}>
                    {ACTIONS.map((a) => <MenuItem key={a} value={a} sx={{ color: "#e2e8f0" }}>{a}</MenuItem>)}
                  </Select>
                </FormControl>

                {/* PageObject picker */}
                {currentAction === "FLOW" && <>
                  <TextField select fullWidth size="small" label="Reusable flow"
                    value={stepForm.flow_id ?? ""}
                    onChange={(e) => {
                      const flow = flows?.items.find((f) => f.id === e.target.value);
                      setStepForm((f) => ({ ...f, flow_id: flow?.id ?? null, flow_version: flow?.version ?? null }));
                    }}>
                    {stepForm.flow_id && !flows?.items.some((f) => f.id === stepForm.flow_id) &&
                      <MenuItem value={stepForm.flow_id}>Selected flow ({stepForm.flow_id})</MenuItem>}
                    {(flows?.items ?? []).map((f) => <MenuItem key={f.id} value={f.id}>{f.name} ({f.kind === "BUSINESS_ACTION" ? "Business action" : "Flow"})</MenuItem>)}
                  </TextField>
                  <TextField select fullWidth size="small" label="Pinned revision"
                    value={stepForm.flow_version ?? ""} disabled={!stepForm.flow_id}
                    onChange={(e) => setStepForm((f) => ({ ...f, flow_version: Number(e.target.value) }))}>
                    {stepForm.flow_version && !revisions?.some((r) => r.version === stepForm.flow_version) &&
                      <MenuItem value={stepForm.flow_version}>v{stepForm.flow_version} (loading or unavailable)</MenuItem>}
                    {(revisions ?? []).map((r) => <MenuItem key={r.version} value={r.version}>
                      v{r.version} · {r.step_count} steps
                    </MenuItem>)}
                  </TextField>
                  {(flowsError || revisionsError) && <Alert severity="error">Could not load flows or revision history.</Alert>}
                  <Alert severity="info">Flow edits preserve this revision. Locators are frozen when a run is queued.
                    Timeouts and optional behavior come from the flow's own steps. Use a separate test step for assertions.</Alert>
                </>}
                {!["FLOW", "NAVIGATE", "EXECUTE_SCRIPT", "SCREENSHOT"].includes(currentAction ?? "") && (
                  <PageObjectPicker
                    label="PageObject"
                    value={stepForm.page_object ?? null}
                    onChange={(po) => setStepForm((f) => ({ ...f, page_object: po }))}
                  />
                )}

                {/* Input value */}
                {["TYPE", "APPEND", "EXECUTE_SCRIPT", "PRESS_KEY", "SELECT"].includes(currentAction ?? "") && (
                  <TextField fullWidth size="small" label="Input value / Script"
                    value={stepForm.input_value ?? ""}
                    onChange={(e) => setStepForm((f) => ({ ...f, input_value: e.target.value }))}
                    multiline rows={2}
                    placeholder="{{VARIABLE}} supported"
                    sx={{ "& .MuiOutlinedInput-root": { bgcolor: "rgba(255,255,255,0.03)", "& fieldset": { borderColor: "rgba(255,255,255,0.12)" } }, textarea: { color: "#e2e8f0" }, "& .MuiInputLabel-root": { color: "#64748b" } }} />
                )}

                {/* Target URL (for NAVIGATE) */}
                {currentAction === "NAVIGATE" && (
                  <TextField fullWidth size="small" label="Target URL"
                    value={stepForm.target_url ?? ""}
                    onChange={(e) => setStepForm((f) => ({ ...f, target_url: e.target.value }))}
                    placeholder="https://example.com or {{BASE_URL}}/path"
                    sx={{ "& .MuiOutlinedInput-root": { bgcolor: "rgba(255,255,255,0.03)", "& fieldset": { borderColor: "rgba(255,255,255,0.12)" } }, input: { color: "#e2e8f0" }, "& .MuiInputLabel-root": { color: "#64748b" } }} />
                )}

                {/* Description */}
                <TextField fullWidth size="small" label="Step description"
                  value={stepForm.description ?? ""}
                  onChange={(e) => setStepForm((f) => ({ ...f, description: e.target.value }))}
                  sx={{ "& .MuiOutlinedInput-root": { bgcolor: "rgba(255,255,255,0.03)", "& fieldset": { borderColor: "rgba(255,255,255,0.12)" } }, input: { color: "#e2e8f0" }, "& .MuiInputLabel-root": { color: "#64748b" } }} />

                {/* Timeout */}
                <TextField fullWidth size="small" label="Timeout (ms)" type="number"
                  disabled={currentAction === "FLOW"}
                  value={stepForm.timeout_ms ?? 30000}
                  onChange={(e) => setStepForm((f) => ({ ...f, timeout_ms: Number(e.target.value) }))}
                  sx={{ "& .MuiOutlinedInput-root": { bgcolor: "rgba(255,255,255,0.03)", "& fieldset": { borderColor: "rgba(255,255,255,0.12)" } }, input: { color: "#e2e8f0" }, "& .MuiInputLabel-root": { color: "#64748b" } }} />

                {/* Flags */}
                <Box sx={{ display: "flex", gap: 2, flexWrap: "wrap" }}>
                  <FormControlLabel
                    control={<Switch disabled={currentAction === "FLOW"} size="small" checked={currentAction === "FLOW" ? false : stepForm.is_optional ?? false} onChange={(e) => setStepForm((f) => ({ ...f, is_optional: e.target.checked }))} />}
                    label={<Typography variant="caption" sx={{ color: "#94a3b8" }}>Optional</Typography>}
                  />
                  <FormControlLabel
                    control={<Switch size="small" checked={stepForm.is_enabled ?? true} onChange={(e) => setStepForm((f) => ({ ...f, is_enabled: e.target.checked }))} />}
                    label={<Typography variant="caption" sx={{ color: "#94a3b8" }}>Enabled</Typography>}
                  />
                </Box>
              </Box>
            </Box>
          )}
        </Box>

        {/* Panel 3: Assertions */}
        <Box sx={{ width: 260, borderLeft: "1px solid rgba(255,255,255,0.06)", overflow: "hidden" }}>
          {selectedStep && currentAction !== "FLOW" ? (
            <AssertionPanel step={selectedStep} onRefresh={refresh} />
          ) : (
            <Box sx={{ p: 2, textAlign: "center", pt: 6 }}>
              <Typography variant="caption" sx={{ color: "#334155" }}>
                Select a step to manage assertions
              </Typography>
            </Box>
          )}
        </Box>
      </Box>
    </Box>
  );
}
