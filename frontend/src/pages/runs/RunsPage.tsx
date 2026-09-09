import { useState, useEffect, useCallback } from "react";
import {
  Box, Typography, Button, Chip, IconButton, Tooltip,
  Dialog, DialogTitle, DialogContent, DialogActions,
  Alert, CircularProgress, LinearProgress,
  Table, TableBody, TableCell, TableHead, TableRow,
  TableContainer, Paper, Select, MenuItem, FormControl,
  InputLabel, Tabs, Tab,
} from "@mui/material";
import {
  Cancel, Stop, Refresh, PlayArrow, CheckCircle,
  Error as ErrorIcon, Schedule, RunningWithErrors,
} from "@mui/icons-material";
import {
  listRuns, getRun, getRunSteps, getRunEvents,
  cancelRun, abortRun,
  type TestRun, type StepResult, type RunEvent, type RunStatus,
} from "../../lib/api/executions";

// ── Status helpers ────────────────────────────────────────────────────────────
const STATUS_COLOR: Record<string, string> = {
  QUEUED: "#f39c12", DISPATCHED: "#3498db", RUNNING: "#2ecc71",
  COMPLETED: "#27ae60", FAILED: "#e74c3c", ABORTED: "#e67e22",
  CANCELLED: "#95a5a6", TIMED_OUT: "#c0392b",
};

function StatusBadge({ status }: { status: string }) {
  const color = STATUS_COLOR[status] ?? "#aaa";
  return (
    <Chip label={status} size="small"
      sx={{ bgcolor: `${color}22`, color, border: `1px solid ${color}`, fontWeight: 600, fontSize: 11 }} />
  );
}

function PriorityBadge({ priority }: { priority: string }) {
  const colors: Record<string, string> = {
    URGENT: "#e74c3c", HIGH: "#e67e22", NORMAL: "#3498db", LOW: "#95a5a6",
  };
  const c = colors[priority] ?? "#aaa";
  return <Chip label={priority} size="small" sx={{ bgcolor: `${c}22`, color: c, fontSize: 10 }} />;
}

function RunProgress({ run }: { run: TestRun }) {
  if (!run.total_steps) return null;
  const pct = (run.passed_steps / run.total_steps) * 100;
  return (
    <Box sx={{ minWidth: 110 }}>
      <LinearProgress variant="determinate" value={pct}
        sx={{ height: 6, borderRadius: 3, bgcolor: "#1e1e3a",
          "& .MuiLinearProgress-bar": { bgcolor: "#27ae60" } }} />
      <Typography variant="caption" sx={{ color: "#666", fontSize: 10 }}>
        {run.passed_steps}✓ {run.failed_steps}✗ / {run.total_steps}
      </Typography>
    </Box>
  );
}

// ── Run Detail Dialog ─────────────────────────────────────────────────────────
function RunDetailDialog({ runId, open, onClose }: { runId: string; open: boolean; onClose: () => void }) {
  const [run, setRun] = useState<TestRun | null>(null);
  const [steps, setSteps] = useState<StepResult[]>([]);
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [tab, setTab] = useState(0);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [r, s, e] = await Promise.all([getRun(runId), getRunSteps(runId), getRunEvents(runId)]);
      setRun(r); setSteps(s); setEvents(e);
    } finally { setLoading(false); }
  }, [runId]);

  useEffect(() => { if (open) load(); }, [open, load]);

  const STEP_CLR: Record<string, string> = {
    PASSED: "#27ae60", FAILED: "#e74c3c", PENDING: "#666", RUNNING: "#3498db", SKIPPED: "#95a5a6",
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="lg" fullWidth
      slotProps={{ paper: { sx: { bgcolor: "#13132a", color: "#fff", minHeight: 600 } } }}>
      {loading || !run ? (
        <DialogContent>
          <Box sx={{ display: "flex", justifyContent: "center", pt: 6 }}><CircularProgress /></Box>
        </DialogContent>
      ) : (
        <>
          <DialogTitle sx={{ borderBottom: "1px solid #1e1e3a" }}>
            <Box sx={{ display: "flex", gap: 2, alignItems: "center", flexWrap: "wrap" }}>
              <Typography sx={{ fontWeight: 700, fontFamily: "monospace", fontSize: 13, color: "#8b8bff" }}>
                {run.id.slice(0, 8)}…
              </Typography>
              <StatusBadge status={run.status} />
              <PriorityBadge priority={run.priority} />
              {run.error_message && (
                <Typography variant="caption" sx={{ color: "#e74c3c" }}>{run.error_message}</Typography>
              )}
            </Box>
            <Typography variant="caption" sx={{ color: "#555", display: "block", mt: 0.5 }}>
              Triggered: {new Date(run.triggered_at).toLocaleString()}
              {run.started_at && ` · Started: ${new Date(run.started_at).toLocaleString()}`}
              {run.completed_at && ` · Completed: ${new Date(run.completed_at).toLocaleString()}`}
            </Typography>
            {run.execution_snapshot_sha256 && (
              <Typography variant="caption" sx={{ fontFamily: "monospace", color: "#444", display: "block" }}>
                sha256: {run.execution_snapshot_sha256.slice(0, 16)}…
              </Typography>
            )}
          </DialogTitle>
          <Box sx={{ borderBottom: 1, borderColor: "#1e1e3a" }}>
            <Tabs value={tab} onChange={(_, v) => setTab(v)} textColor="inherit">
              <Tab label={`Steps (${steps.length})`} />
              <Tab label={`Events (${events.length})`} />
            </Tabs>
          </Box>
          <DialogContent>
            {tab === 0 && (
              <TableContainer>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      {["#", "Action", "Status", "Duration", "Value", "Error"].map((h) => (
                        <TableCell key={h} sx={{ color: "#666", borderBottom: "1px solid #1e1e3a", fontSize: 11 }}>{h}</TableCell>
                      ))}
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {steps.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={6} sx={{ color: "#555", textAlign: "center", py: 4 }}>
                          No step results yet
                        </TableCell>
                      </TableRow>
                    ) : steps.map((s) => (
                      <TableRow key={s.id}>
                        <TableCell sx={{ color: "#555", borderBottom: "1px solid #1e1e3a" }}>{s.position}</TableCell>
                        <TableCell sx={{ borderBottom: "1px solid #1e1e3a" }}>
                          <Chip label={s.action} size="small" sx={{ bgcolor: "#1e1e3a", color: "#8b8bff", fontSize: 10 }} />
                        </TableCell>
                        <TableCell sx={{ borderBottom: "1px solid #1e1e3a" }}>
                          <Chip label={s.status} size="small"
                            sx={{ bgcolor: `${STEP_CLR[s.status] ?? "#555"}22`, color: STEP_CLR[s.status] ?? "#aaa", fontSize: 10 }} />
                        </TableCell>
                        <TableCell sx={{ color: "#666", borderBottom: "1px solid #1e1e3a", fontSize: 11 }}>
                          {s.duration_ms != null ? `${s.duration_ms}ms` : "—"}
                        </TableCell>
                        <TableCell sx={{ color: "#48cae4", fontFamily: "monospace", fontSize: 11, borderBottom: "1px solid #1e1e3a" }}>
                          {s.display_value ?? "—"}
                        </TableCell>
                        <TableCell sx={{ color: "#e74c3c", fontSize: 11, borderBottom: "1px solid #1e1e3a" }}>
                          {s.error_message ?? "—"}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            )}
            {tab === 1 && (
              <TableContainer>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      {["Seq", "Timestamp", "Event", "Severity", "Message"].map((h) => (
                        <TableCell key={h} sx={{ color: "#666", borderBottom: "1px solid #1e1e3a", fontSize: 11 }}>{h}</TableCell>
                      ))}
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {events.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={5} sx={{ color: "#555", textAlign: "center", py: 4 }}>No events</TableCell>
                      </TableRow>
                    ) : events.map((e) => {
                      const sc = e.severity === "ERROR" ? "#e74c3c" : e.severity === "WARNING" ? "#f39c12" : "#3498db";
                      return (
                        <TableRow key={e.id}>
                          <TableCell sx={{ color: "#555", borderBottom: "1px solid #1e1e3a", fontSize: 11 }}>{e.sequence}</TableCell>
                          <TableCell sx={{ color: "#666", borderBottom: "1px solid #1e1e3a", fontSize: 10 }}>
                            {new Date(e.timestamp).toLocaleTimeString()}
                          </TableCell>
                          <TableCell sx={{ borderBottom: "1px solid #1e1e3a" }}>
                            <Chip label={e.event} size="small" sx={{ bgcolor: "#1e1e3a", color: "#8b8bff", fontSize: 10 }} />
                          </TableCell>
                          <TableCell sx={{ borderBottom: "1px solid #1e1e3a" }}>
                            <Chip label={e.severity} size="small"
                              sx={{ bgcolor: `${sc}22`, color: sc, fontSize: 10 }} />
                          </TableCell>
                          <TableCell sx={{ color: "#ccc", fontSize: 12, borderBottom: "1px solid #1e1e3a" }}>{e.message}</TableCell>
                        </TableRow>
                      );
                    })}
                  </TableBody>
                </Table>
              </TableContainer>
            )}
          </DialogContent>
          <DialogActions sx={{ borderTop: "1px solid #1e1e3a" }}>
            <Button startIcon={<Refresh />} onClick={load} sx={{ color: "#8b8bff" }}>Refresh</Button>
            {run.status === "QUEUED" && (
              <Button startIcon={<Cancel />} onClick={() => cancelRun(run.id).then(load)} color="warning">Cancel</Button>
            )}
            {["RUNNING", "DISPATCHED"].includes(run.status) && (
              <Button startIcon={<Stop />} onClick={() => abortRun(run.id).then(load)} color="error">Abort</Button>
            )}
            <Button onClick={onClose} sx={{ color: "#aaa" }}>Close</Button>
          </DialogActions>
        </>
      )}
    </Dialog>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────
export default function RunsPage() {
  const [runs, setRuns] = useState<TestRun[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [selected, setSelected] = useState<string | null>(null);

  const load = useCallback(async (status?: string) => {
    setLoading(true); setError("");
    try {
      const data = await listRuns({ status: (status || undefined) as RunStatus | undefined, limit: 100 });
      setRuns(data.items); setTotal(data.total);
    } catch (e: any) {
      setError(e?.message ?? "Failed to load runs");
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(statusFilter); }, [load, statusFilter]);

  // Auto-refresh every 10 s when there are active runs
  useEffect(() => {
    const hasActive = runs.some((r) => ["QUEUED", "DISPATCHED", "RUNNING"].includes(r.status));
    if (!hasActive) return;
    const id = setInterval(() => load(statusFilter), 10000);
    return () => clearInterval(id);
  }, [runs, statusFilter, load]);

  return (
    <Box sx={{ p: 3, color: "#e0e0ff", minHeight: "100vh" }}>
      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 3 }}>
        <Box>
          <Typography variant="h5" sx={{ fontWeight: 700, color: "#fff" }}>Test Runs</Typography>
          <Typography variant="body2" sx={{ color: "#666" }}>
            {total} total · {runs.filter((r) => ["QUEUED", "DISPATCHED", "RUNNING"].includes(r.status)).length} active
          </Typography>
        </Box>
        <Box sx={{ display: "flex", gap: 1 }}>
          <FormControl size="small" sx={{ minWidth: 150 }}>
            <InputLabel sx={{ color: "#aaa" }}>Status</InputLabel>
            <Select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} label="Status"
              sx={{ color: "#fff", bgcolor: "#13132a" }}>
              <MenuItem value="">All</MenuItem>
              {["QUEUED","DISPATCHED","RUNNING","COMPLETED","FAILED","ABORTED","CANCELLED","TIMED_OUT"].map((s) => (
                <MenuItem key={s} value={s}>{s}</MenuItem>
              ))}
            </Select>
          </FormControl>
          <Button startIcon={<Refresh />} onClick={() => load(statusFilter)} sx={{ color: "#8b8bff" }}>Refresh</Button>
        </Box>
      </Box>

      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

      {loading ? (
        <Box sx={{ display: "flex", justifyContent: "center", mt: 6 }}><CircularProgress /></Box>
      ) : (
        <TableContainer component={Paper}
          sx={{ bgcolor: "#13132a", borderRadius: 3, boxShadow: "0 4px 32px rgba(108,99,255,.15)" }}>
          <Table>
            <TableHead>
              <TableRow>
                {["Run ID", "Test Case", "Status", "Priority", "Progress", "Environment", "Triggered", ""].map((h) => (
                  <TableCell key={h} sx={{ color: "#8b8bff", borderBottom: "1px solid #1e1e3a", fontWeight: 600 }}>{h}</TableCell>
                ))}
              </TableRow>
            </TableHead>
            <TableBody>
              {runs.length === 0 && (
                <TableRow>
                  <TableCell colSpan={8} sx={{ textAlign: "center", color: "#666", py: 6 }}>
                    No runs found. Trigger one from a test case.
                  </TableCell>
                </TableRow>
              )}
              {runs.map((run) => (
                <TableRow key={run.id} hover
                  sx={{ cursor: "pointer", "&:hover": { bgcolor: "#1e1e3a" } }}
                  onClick={() => setSelected(run.id)}>
                  <TableCell sx={{ color: "#8b8bff", fontFamily: "monospace", fontSize: 11, borderBottom: "1px solid #1e1e3a" }}>
                    {run.id.slice(0, 8)}…
                  </TableCell>
                  <TableCell sx={{ color: "#e0e0ff", fontSize: 12, borderBottom: "1px solid #1e1e3a" }}>
                    <Typography variant="caption" sx={{ fontFamily: "monospace", color: "#666" }}>
                      {run.test_case_id.slice(0, 8)}…
                    </Typography>
                    <Chip label={`v${run.test_case_version}`} size="small"
                      sx={{ ml: 1, bgcolor: "#1e1e3a", color: "#555", fontSize: 10 }} />
                  </TableCell>
                  <TableCell sx={{ borderBottom: "1px solid #1e1e3a" }}><StatusBadge status={run.status} /></TableCell>
                  <TableCell sx={{ borderBottom: "1px solid #1e1e3a" }}><PriorityBadge priority={run.priority} /></TableCell>
                  <TableCell sx={{ borderBottom: "1px solid #1e1e3a" }}><RunProgress run={run} /></TableCell>
                  <TableCell sx={{ color: "#666", fontSize: 11, borderBottom: "1px solid #1e1e3a" }}>
                    {run.environment_id ? `${run.environment_id.slice(0, 8)}…` : "—"}
                  </TableCell>
                  <TableCell sx={{ color: "#666", fontSize: 11, borderBottom: "1px solid #1e1e3a" }}>
                    {new Date(run.triggered_at).toLocaleString()}
                  </TableCell>
                  <TableCell sx={{ borderBottom: "1px solid #1e1e3a" }} onClick={(e) => e.stopPropagation()}>
                    {run.status === "QUEUED" && (
                      <Tooltip title="Cancel">
                        <IconButton size="small" sx={{ color: "#f39c12" }}
                          onClick={() => cancelRun(run.id).then(() => load(statusFilter))}>
                          <Cancel fontSize="small" />
                        </IconButton>
                      </Tooltip>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      )}

      {selected && (
        <RunDetailDialog runId={selected} open={!!selected}
          onClose={() => { setSelected(null); load(statusFilter); }} />
      )}
    </Box>
  );
}
