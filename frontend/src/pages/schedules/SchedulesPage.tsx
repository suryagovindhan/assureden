import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Box, Typography, Button, Chip, IconButton, Tooltip, Switch,
  Dialog, DialogTitle, DialogContent, DialogActions,
  TextField, MenuItem, Collapse, Table, TableBody, TableCell,
  TableContainer, TableHead, TableRow, Paper, CircularProgress,
  Alert, Snackbar, Stack, Divider, LinearProgress,
} from "@mui/material";
import {
  Add as AddIcon,
  PlayArrow as TriggerIcon,
  Edit as EditIcon,
  Delete as DeleteIcon,
  History as HistoryIcon,
  ExpandMore as ExpandMoreIcon,
  ExpandLess as ExpandLessIcon,
  Schedule as ScheduleIcon,
  CheckCircle as OkIcon,
  Cancel as SkipIcon,
  Error as ErrorIcon,
} from "@mui/icons-material";
import { useQuery as useTestCasesQuery } from "@tanstack/react-query";
import {
  listSchedules, createSchedule, patchSchedule, deleteSchedule,
  enableSchedule, disableSchedule, triggerNow, getScheduleHistory,
  type ScheduledJob, type CreateScheduleBody,
} from "../../lib/api/schedules";

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtDate(s: string | null): string {
  if (!s) return "—";
  return new Date(s).toLocaleString();
}

function fmtWait(isoTs: string | null): string {
  if (!isoTs) return "—";
  const secs = Math.max(0, Math.floor((Date.now() - new Date(isoTs).getTime()) / 1000));
  if (secs < 60) return `${secs}s`;
  if (secs < 3600) return `${Math.floor(secs / 60)}m ${secs % 60}s`;
  return `${Math.floor(secs / 3600)}h ${Math.floor((secs % 3600) / 60)}m`;
}

const STATUS_COLORS: Record<string, string> = {
  TRIGGERED: "#4caf50",
  SKIPPED:   "#ff9800",
  FAILED:    "#f44336",
};

const TIMEZONES = [
  "UTC", "America/New_York", "America/Chicago", "America/Los_Angeles",
  "America/Denver", "Europe/London", "Europe/Paris", "Europe/Berlin",
  "Asia/Kolkata", "Asia/Singapore", "Asia/Tokyo", "Australia/Sydney",
];

// ── Create/Edit Drawer ────────────────────────────────────────────────────────

interface ScheduleFormProps {
  open: boolean;
  onClose: () => void;
  initial?: ScheduledJob | null;
  testCases: Array<{ id: string; name: string }>;
}

function ScheduleFormDialog({ open, onClose, initial, testCases }: ScheduleFormProps) {
  const qc = useQueryClient();
  const isEdit = Boolean(initial);

  const [form, setForm] = useState({
    name:            initial?.name ?? "",
    cron_expression: initial?.cron_expression ?? "0 * * * *",
    timezone:        initial?.timezone ?? "UTC",
    test_case_id:    initial?.test_case_id ?? "",
    priority:        initial?.priority ?? "NORMAL",
    max_retries:     String(initial?.max_retries ?? 0),
    retry_on_timeout: initial?.retry_on_timeout ?? true,
    retry_on_failure: initial?.retry_on_failure ?? false,
    miss_threshold_minutes: String(initial?.miss_threshold_minutes ?? 10),
  });

  const [error, setError] = useState<string | null>(null);

  const create = useMutation({
    mutationFn: (body: CreateScheduleBody) => createSchedule(body),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["schedules"] }); onClose(); },
    onError: (e: any) => setError(e?.response?.data?.detail ?? "Create failed"),
  });

  const patch = useMutation({
    mutationFn: (body: any) => patchSchedule(initial!.id, body),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["schedules"] }); onClose(); },
    onError: (e: any) => setError(e?.response?.data?.detail ?? "Update failed"),
  });

  const handleSubmit = () => {
    setError(null);
    if (!form.name || !form.cron_expression || !form.test_case_id) {
      setError("Name, cron expression, and test case are required.");
      return;
    }
    const payload = {
      name:            form.name,
      cron_expression: form.cron_expression,
      timezone:        form.timezone,
      test_case_id:    form.test_case_id,
      priority:        form.priority,
      max_retries:     parseInt(form.max_retries) || 0,
      retry_on_timeout: form.retry_on_timeout,
      retry_on_failure: form.retry_on_failure,
      miss_threshold_minutes: parseInt(form.miss_threshold_minutes) || 10,
    };
    if (isEdit) patch.mutate(payload);
    else create.mutate(payload as CreateScheduleBody);
  };

  const f = (k: string) => (e: any) => setForm((p) => ({ ...p, [k]: e.target.value }));

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth
      slotProps={{ paper: { sx: { bgcolor: "#1a1a2e", border: "1px solid rgba(255,255,255,0.1)" } } }}>
      <DialogTitle sx={{ color: "#fff", fontWeight: 700 }}>
        {isEdit ? "Edit Schedule" : "New Schedule"}
      </DialogTitle>
      <DialogContent sx={{ display: "flex", flexDirection: "column", gap: 2, pt: 2 }}>
        {error && <Alert severity="error" sx={{ mb: 1 }}>{error}</Alert>}

        <TextField label="Name" value={form.name} onChange={f("name")}
          fullWidth size="small" slotProps={{ inputLabel: { sx: { color: "rgba(255,255,255,0.5)" } }, input: { sx: { color: "#fff" } } }}
           />

        <Stack direction="row" spacing={2}>
          <TextField label="Cron Expression" value={form.cron_expression}
            onChange={f("cron_expression")} fullWidth size="small"
            helperText="5-field cron: min hour day month weekday"
            slotProps={{ inputLabel: { sx: { color: "rgba(255,255,255,0.5)" } }, input: { sx: { color: "#fff", fontFamily: "monospace" } } }}
             />
          <TextField select label="Timezone" value={form.timezone}
            onChange={f("timezone")} sx={{ minWidth: 160 }} size="small"
            slotProps={{ select: { MenuProps: { slotProps: { paper: { sx: { bgcolor: "#1a1a2e" } } } } }, ...({ inputLabel: { sx: { color: "rgba(255,255,255,0.5)" } } }) }}
            >
            {TIMEZONES.map((tz) => <MenuItem key={tz} value={tz} sx={{ color: "#fff" }}>{tz}</MenuItem>)}
          </TextField>
        </Stack>

        <TextField select label="Test Case" value={form.test_case_id}
          onChange={f("test_case_id")} fullWidth size="small"
          slotProps={{ select: { MenuProps: { slotProps: { paper: { sx: { bgcolor: "#1a1a2e" } } } } }, ...({ inputLabel: { sx: { color: "rgba(255,255,255,0.5)" } } }) }}
          >
          {testCases.map((tc) => (
            <MenuItem key={tc.id} value={tc.id} sx={{ color: "#fff" }}>{tc.name}</MenuItem>
          ))}
        </TextField>

        <Stack direction="row" spacing={2}>
          <TextField select label="Priority" value={form.priority}
            onChange={f("priority")} sx={{ minWidth: 130 }} size="small"
            slotProps={{ select: { MenuProps: { slotProps: { paper: { sx: { bgcolor: "#1a1a2e" } } } } }, ...({ inputLabel: { sx: { color: "rgba(255,255,255,0.5)" } } }) }}
            >
            {["URGENT", "HIGH", "NORMAL", "LOW"].map((p) => (
              <MenuItem key={p} value={p} sx={{ color: "#fff" }}>{p}</MenuItem>
            ))}
          </TextField>
          <TextField label="Max Retries" value={form.max_retries}
            onChange={f("max_retries")} type="number" sx={{ maxWidth: 120 }} size="small"
            slotProps={{ inputLabel: { sx: { color: "rgba(255,255,255,0.5)" } }, input: { sx: { color: "#fff" } } }}
             />
          <TextField label="Miss Threshold (min)" value={form.miss_threshold_minutes}
            onChange={f("miss_threshold_minutes")} type="number" size="small"
            slotProps={{ inputLabel: { sx: { color: "rgba(255,255,255,0.5)" } }, input: { sx: { color: "#fff" } } }}
             />
        </Stack>
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button onClick={onClose} sx={{ color: "rgba(255,255,255,0.5)" }}>Cancel</Button>
        <Button variant="contained" onClick={handleSubmit}
          disabled={create.isPending || patch.isPending}
          sx={{ background: "linear-gradient(135deg, #667eea, #764ba2)" }}>
          {isEdit ? "Save Changes" : "Create"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

// ── Delete confirm dialog ─────────────────────────────────────────────────────

function DeleteDialog({ job, onClose }: { job: ScheduledJob | null; onClose: () => void }) {
  const qc = useQueryClient();
  const del = useMutation({
    mutationFn: () => deleteSchedule(job!.id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["schedules"] }); onClose(); },
  });
  return (
    <Dialog open={Boolean(job)} onClose={onClose}
      slotProps={{ paper: { sx: { bgcolor: "#1a1a2e", border: "1px solid rgba(255,255,255,0.1)" } } }}>
      <DialogTitle sx={{ color: "#fff" }}>Delete schedule?</DialogTitle>
      <DialogContent>
        <Typography sx={{ color: "rgba(255,255,255,0.7)" }}>
          <strong style={{ color: "#fff" }}>{job?.name}</strong> will be soft-deleted and
          can no longer be triggered.
        </Typography>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} sx={{ color: "rgba(255,255,255,0.5)" }}>Cancel</Button>
        <Button variant="contained" color="error" onClick={() => del.mutate()}
          disabled={del.isPending}>Delete</Button>
      </DialogActions>
    </Dialog>
  );
}

// ── History panel ─────────────────────────────────────────────────────────────

function HistoryPanel({ jobId }: { jobId: string }) {
  const { data, isLoading } = useQuery({
    queryKey: ["schedule-history", jobId],
    queryFn: () => getScheduleHistory(jobId, 20),
    staleTime: 30_000,
  });

  if (isLoading) return <Box sx={{ p: 2 }}><LinearProgress /></Box>;

  const rows = data?.history ?? [];
  if (!rows.length) return (
    <Typography sx={{ p: 2, color: "rgba(255,255,255,0.4)", fontSize: 13 }}>
      No history yet.
    </Typography>
  );

  return (
    <Box sx={{ px: 2, pb: 2 }}>
      {rows.map((h) => {
        const Icon = h.status === "TRIGGERED" ? OkIcon : h.status === "SKIPPED" ? SkipIcon : ErrorIcon;
        return (
          <Stack key={h.id} direction="row"  spacing={1.5}
            sx={{ alignItems: "center", ...({ py: 0.75, borderBottom: "1px solid rgba(255,255,255,0.05)" }) }}>
            <Icon sx={{ fontSize: 16, color: STATUS_COLORS[h.status] ?? "#aaa" }} />
            <Typography sx={{ fontSize: 12, color: "rgba(255,255,255,0.6)", minWidth: 140 }}>
              {fmtDate(h.triggered_at)}
            </Typography>
            <Chip label={h.status} size="small"
              sx={{ fontSize: 10, bgcolor: `${STATUS_COLORS[h.status] ?? "#555"}22`,
                    color: STATUS_COLORS[h.status] ?? "#aaa", border: "none" }} />
            {h.run_id && (
              <Typography sx={{ fontSize: 11, color: "#667eea", fontFamily: "monospace" }}>
                {h.run_id.slice(0, 8)}…
              </Typography>
            )}
            {h.trigger_error && (
              <Typography sx={{ fontSize: 11, color: "#f44336" }}>
                {h.trigger_error}
              </Typography>
            )}
          </Stack>
        );
      })}
    </Box>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function SchedulesPage() {
  const qc = useQueryClient();
  const [showCreate, setShowCreate] = useState(false);
  const [editJob, setEditJob] = useState<ScheduledJob | null>(null);
  const [deleteJob, setDeleteJob] = useState<ScheduledJob | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [toast, setToast] = useState<{ msg: string; severity: "success" | "error" } | null>(null);

  const { data, isLoading, isError } = useQuery({
    queryKey: ["schedules"],
    queryFn: () => listSchedules({ limit: 100 }),
    staleTime: 30_000,
  });

  // Load test cases for schedule create/edit form
  const { data: tcData } = useQuery({
    queryKey: ["test-cases-mini"],
    queryFn: () => import("../../lib/api/testCases").then((m) => m.casesApi.list({ limit: 200 }).then(r => r.data)),
    staleTime: 120_000,
  });
  const testCases = (tcData as any) ?? [];

  const toggle = useMutation({
    mutationFn: (job: ScheduledJob) =>
      job.is_enabled ? disableSchedule(job.id) : enableSchedule(job.id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["schedules"] }),
    onError: () => setToast({ msg: "Toggle failed", severity: "error" }),
  });

  const trigger = useMutation({
    mutationFn: (id: string) => triggerNow(id),
    onSuccess: (r) => setToast({ msg: `Run queued: ${r.run_id.slice(0, 8)}…`, severity: "success" }),
    onError: (e: any) => setToast({ msg: e?.response?.data?.detail ?? "Trigger failed", severity: "error" }),
  });

  const schedules = data?.items ?? [];

  return (
    <Box>
      {/* Header */}
      <Stack direction="row" sx={{ alignItems: "center", justifyContent: "space-between", mb: 3 }}  >
        <Stack direction="row" sx={{ alignItems: "center" }} spacing={1.5}>
          <Box sx={{
            width: 40, height: 40, borderRadius: 2,
            background: "linear-gradient(135deg, #667eea, #764ba2)",
            display: "flex", alignItems: "center", justifyContent: "center",
          }}>
            <ScheduleIcon sx={{ color: "#fff", fontSize: 22 }} />
          </Box>
          <Box>
            <Typography variant="h5" sx={{ fontWeight: 700, color: "#fff" }}>
              Schedules
            </Typography>
            <Typography sx={{ fontSize: 13, color: "rgba(255,255,255,0.4)" }}>
              {schedules.length} schedule{schedules.length !== 1 ? "s" : ""}
            </Typography>
          </Box>
        </Stack>
        <Button
          variant="contained"
          startIcon={<AddIcon />}
          onClick={() => setShowCreate(true)}
          sx={{ background: "linear-gradient(135deg, #667eea, #764ba2)", fontWeight: 600 }}
        >
          New Schedule
        </Button>
      </Stack>

      {isLoading && <LinearProgress sx={{ mb: 2, borderRadius: 1 }} />}
      {isError && <Alert severity="error" sx={{ mb: 2 }}>Failed to load schedules.</Alert>}

      {/* Schedule cards */}
      {schedules.length === 0 && !isLoading ? (
        <Box sx={{
          textAlign: "center", py: 8,
          border: "1px dashed rgba(255,255,255,0.1)",
          borderRadius: 3,
        }}>
          <ScheduleIcon sx={{ fontSize: 48, color: "rgba(255,255,255,0.15)", mb: 2 }} />
          <Typography sx={{ color: "rgba(255,255,255,0.4)" }}>No schedules yet.</Typography>
          <Button onClick={() => setShowCreate(true)} sx={{ mt: 2, color: "#667eea" }}>
            Create your first schedule
          </Button>
        </Box>
      ) : (
        <Stack spacing={1.5}>
          {schedules.map((job) => {
            const expanded = expandedId === job.id;
            return (
              <Paper key={job.id} sx={{
                bgcolor: "#13132a",
                border: "1px solid rgba(255,255,255,0.07)",
                borderRadius: 2,
                overflow: "hidden",
                transition: "border-color 0.2s",
                "&:hover": { borderColor: "rgba(102,126,234,0.3)" },
              }}>
                {/* Main row */}
                <Stack direction="row"  spacing={2} sx={{ alignItems: "center", ...({ p: 2 }) }}>
                  {/* Enable toggle */}
                  <Tooltip title={job.is_enabled ? "Disable" : "Enable"}>
                    <Switch
                      checked={job.is_enabled}
                      onChange={() => toggle.mutate(job)}
                      size="small"
                      sx={{
                        "& .MuiSwitch-switchBase.Mui-checked + .MuiSwitch-track": {
                          bgcolor: "#667eea",
                        },
                      }}
                    />
                  </Tooltip>

                  {/* Name + cron */}
                  <Box sx={{ flex: 1, minWidth: 0 }}>
                    <Typography sx={{ fontWeight: 600, color: "#fff", fontSize: 14 }}>
                      {job.name}
                    </Typography>
                    <Stack direction="row" spacing={1} sx={{ alignItems: "center", mt: 0.25 }} >
                      <Typography sx={{
                        fontFamily: "monospace", fontSize: 12,
                        color: "#667eea", bgcolor: "rgba(102,126,234,0.1)",
                        px: 0.75, py: 0.25, borderRadius: 1,
                      }}>
                        {job.cron_expression}
                      </Typography>
                      <Typography sx={{ fontSize: 12, color: "rgba(255,255,255,0.4)" }}>
                        {job.timezone}
                      </Typography>
                    </Stack>
                  </Box>

                  {/* Status + next run */}
                  <Box sx={{ textAlign: "right", minWidth: 140 }}>
                    <Chip
                      label={job.is_enabled ? "Enabled" : "Disabled"}
                      size="small"
                      sx={{
                        bgcolor: job.is_enabled ? "rgba(76,175,80,0.15)" : "rgba(255,255,255,0.07)",
                        color: job.is_enabled ? "#4caf50" : "rgba(255,255,255,0.4)",
                        fontWeight: 600, fontSize: 11, mb: 0.5,
                      }}
                    />
                    <Typography sx={{ fontSize: 11, color: "rgba(255,255,255,0.4)" }}>
                      Next: {fmtDate(job.next_run_at)}
                    </Typography>
                  </Box>

                  {/* Priority */}
                  <Chip label={job.priority} size="small" sx={{
                    bgcolor: job.priority === "URGENT" ? "rgba(244,67,54,0.15)"
                           : job.priority === "HIGH"   ? "rgba(255,152,0,0.15)"
                           : "rgba(255,255,255,0.07)",
                    color: job.priority === "URGENT" ? "#f44336"
                         : job.priority === "HIGH"   ? "#ff9800"
                         : "rgba(255,255,255,0.5)",
                    fontWeight: 600, fontSize: 11,
                  }} />

                  {/* Actions */}
                  <Stack direction="row" spacing={0.5}>
                    <Tooltip title="Trigger now">
                      <IconButton size="small"
                        onClick={() => trigger.mutate(job.id)}
                        disabled={trigger.isPending}
                        sx={{ color: "#4caf50", "&:hover": { bgcolor: "rgba(76,175,80,0.1)" } }}>
                        <TriggerIcon fontSize="small" />
                      </IconButton>
                    </Tooltip>
                    <Tooltip title="Edit">
                      <IconButton size="small" onClick={() => setEditJob(job)}
                        sx={{ color: "#667eea", "&:hover": { bgcolor: "rgba(102,126,234,0.1)" } }}>
                        <EditIcon fontSize="small" />
                      </IconButton>
                    </Tooltip>
                    <Tooltip title={expanded ? "Hide history" : "Show history"}>
                      <IconButton size="small"
                        onClick={() => setExpandedId(expanded ? null : job.id)}
                        sx={{ color: "rgba(255,255,255,0.4)", "&:hover": { color: "#fff" } }}>
                        {expanded ? <ExpandLessIcon fontSize="small" /> : <HistoryIcon fontSize="small" />}
                      </IconButton>
                    </Tooltip>
                    <Tooltip title="Delete">
                      <IconButton size="small" onClick={() => setDeleteJob(job)}
                        sx={{ color: "#f44336", "&:hover": { bgcolor: "rgba(244,67,54,0.1)" } }}>
                        <DeleteIcon fontSize="small" />
                      </IconButton>
                    </Tooltip>
                  </Stack>
                </Stack>

                {/* Expandable history */}
                <Collapse in={expanded}>
                  <Divider sx={{ borderColor: "rgba(255,255,255,0.06)" }} />
                  <HistoryPanel jobId={job.id} />
                </Collapse>
              </Paper>
            );
          })}
        </Stack>
      )}

      {/* Dialogs */}
      <ScheduleFormDialog
        open={showCreate || Boolean(editJob)}
        onClose={() => { setShowCreate(false); setEditJob(null); }}
        initial={editJob}
        testCases={testCases}
      />
      <DeleteDialog job={deleteJob} onClose={() => setDeleteJob(null)} />

      {/* Toast */}
      <Snackbar open={Boolean(toast)} autoHideDuration={4000} onClose={() => setToast(null)}
        anchorOrigin={{ vertical: "bottom", horizontal: "right" }}>
        <Alert severity={toast?.severity ?? "info"} onClose={() => setToast(null)}>
          {toast?.msg}
        </Alert>
      </Snackbar>
    </Box>
  );
}
