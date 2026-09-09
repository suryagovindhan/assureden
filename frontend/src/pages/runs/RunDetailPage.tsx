import { useState, useMemo } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Box, Typography, Chip, Stack, Button, Tabs, Tab,
  LinearProgress, Alert, Paper, Divider, Tooltip,
  IconButton, CircularProgress, Collapse, Badge,
} from "@mui/material";
import {
  ArrowBack as BackIcon,
  Replay as RetryIcon,
  Cancel as CancelIcon,
  Block as AbortIcon,
  ContentCopy as CopyIcon,
  CheckCircle as CheckIcon,
  Cancel as FailIcon,
  RadioButtonUnchecked as QueuedIcon,
  PlayArrow as RunningIcon,
  AccessTime as WaitIcon,
  ErrorOutline as ErrorIcon,
  Download as DownloadIcon,
  Image as ScreenshotIcon,
  VideoFile as VideoIcon,
  Description as LogIcon,
  FiberManualRecord as LiveIcon,
} from "@mui/icons-material";
import {
  getRun, getRunSteps, getRunEvents, cancelRun, abortRun,
  type TestRun, type StepResult, type RunEvent,
} from "../../lib/api/executions";
import { getRetryHistory } from "../../lib/api/metrics";
import { useRunStream } from "../../lib/hooks/useRunStream";

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtTs(s: string | null) {
  if (!s) return "—";
  return new Date(s).toLocaleString();
}

function fmtDuration(startedAt: string | null, completedAt: string | null): string {
  if (!startedAt) return "—";
  const end = completedAt ? new Date(completedAt) : new Date();
  const ms = end.getTime() - new Date(startedAt).getTime();
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`;
  return `${Math.floor(ms / 60_000)}m ${Math.floor((ms % 60_000) / 1000)}s`;
}

const STATUS_CONFIG: Record<string, { color: string; bg: string; Icon: any }> = {
  QUEUED:      { color: "#9e9e9e",  bg: "rgba(158,158,158,0.12)",  Icon: QueuedIcon },
  DISPATCHED:  { color: "#2196f3",  bg: "rgba(33,150,243,0.12)",   Icon: WaitIcon },
  RUNNING:     { color: "#ff9800",  bg: "rgba(255,152,0,0.12)",    Icon: RunningIcon },
  COMPLETED:   { color: "#4caf50",  bg: "rgba(76,175,80,0.12)",    Icon: CheckIcon },
  FAILED:      { color: "#f44336",  bg: "rgba(244,67,54,0.12)",    Icon: FailIcon },
  ABORTED:     { color: "#f44336",  bg: "rgba(244,67,54,0.12)",    Icon: AbortIcon },
  CANCELLED:   { color: "#9e9e9e",  bg: "rgba(158,158,158,0.12)",  Icon: CancelIcon },
  TIMED_OUT:   { color: "#ff5722",  bg: "rgba(255,87,34,0.12)",    Icon: ErrorIcon },
};

const PRIORITY_CONFIG: Record<string, { color: string }> = {
  URGENT: { color: "#f44336" },
  HIGH:   { color: "#ff9800" },
  NORMAL: { color: "#667eea" },
  LOW:    { color: "#9e9e9e" },
};

const SEVERITY_COLORS: Record<string, string> = {
  INFO:    "#4caf50",
  WARNING: "#ff9800",
  ERROR:   "#f44336",
  DEBUG:   "#9e9e9e",
};

// ── Overview Tab ─────────────────────────────────────────────────────────────

function OverviewTab({ run }: { run: TestRun }) {
  const stat = STATUS_CONFIG[run.status] ?? STATUS_CONFIG.QUEUED;
  const StatIcon = stat.Icon;
  const priorColor = PRIORITY_CONFIG[run.priority]?.color ?? "#667eea";

  const pct = run.total_steps
    ? Math.round(((run.passed_steps + run.failed_steps + run.skipped_steps) / run.total_steps) * 100)
    : 0;

  const rows: [string, React.ReactNode][] = [
    ["Status",       <Chip label={run.status} size="small" icon={<StatIcon sx={{ fontSize: 14 }} />}
                       sx={{ bgcolor: stat.bg, color: stat.color, fontWeight: 700 }} />],
    ["Priority",     <Chip label={run.priority} size="small"
                       sx={{ bgcolor: `${priorColor}22`, color: priorColor, fontWeight: 600 }} />],
    ["Test Case",    <Typography sx={{ fontSize: 13, color: "#667eea", fontFamily: "monospace" }}>
                       {run.test_case_id.slice(0, 8)}…
                     </Typography>],
    ["Environment",  run.environment_id
                       ? <Typography sx={{ fontSize: 13, fontFamily: "monospace", color: "rgba(255,255,255,0.7)" }}>
                           {run.environment_id.slice(0, 8)}…
                         </Typography>
                       : <Typography sx={{ fontSize: 13, color: "rgba(255,255,255,0.3)" }}>none</Typography>],
    ["Agent",        run.agent_id
                       ? <Typography sx={{ fontSize: 13, fontFamily: "monospace", color: "rgba(255,255,255,0.7)" }}>
                           {run.agent_id.slice(0, 8)}…
                         </Typography>
                       : <Typography sx={{ fontSize: 13, color: "rgba(255,255,255,0.3)" }}>unassigned</Typography>],
    ["Triggered",    <Typography sx={{ fontSize: 13, color: "rgba(255,255,255,0.7)" }}>
                       {fmtTs(run.triggered_at)}
                     </Typography>],
    ["Started",      <Typography sx={{ fontSize: 13, color: "rgba(255,255,255,0.7)" }}>
                       {fmtTs(run.started_at)}
                     </Typography>],
    ["Completed",    <Typography sx={{ fontSize: 13, color: "rgba(255,255,255,0.7)" }}>
                       {fmtTs(run.completed_at)}
                     </Typography>],
    ["Duration",     <Typography sx={{ fontSize: 13, color: "rgba(255,255,255,0.7)" }}>
                       {fmtDuration(run.started_at, run.completed_at)}
                     </Typography>],
    ["Retry",        <Typography sx={{ fontSize: 13, color: "rgba(255,255,255,0.7)" }}>
                       {run.retry_count} attempt{run.retry_count !== 1 ? "s" : ""}
                     </Typography>],
    ["Timeout",      <Typography sx={{ fontSize: 13, color: "rgba(255,255,255,0.7)" }}>
                       {run.timeout_seconds}s
                     </Typography>],
  ];

  return (
    <Box>
      {/* Progress bar */}
      {run.total_steps !== null && (
        <Paper sx={{ bgcolor: "#0d0d1a", p: 2, mb: 2, borderRadius: 2 }}>
          <Stack direction="row" justifyContent="space-between" mb={1}>
            <Typography sx={{ fontSize: 13, color: "rgba(255,255,255,0.6)" }}>
              Step Progress
            </Typography>
            <Typography sx={{ fontSize: 13, color: "#fff" }}>
              {run.passed_steps + run.failed_steps + run.skipped_steps} / {run.total_steps} ({pct}%)
            </Typography>
          </Stack>
          <LinearProgress variant="determinate" value={pct}
            sx={{ height: 6, borderRadius: 3,
                  "& .MuiLinearProgress-bar": {
                    background: run.status === "COMPLETED" ? "#4caf50"
                              : run.status === "FAILED" ? "#f44336" : "#667eea",
                  }}} />
          <Stack direction="row" spacing={3} mt={1}>
            {[
              ["Passed",  run.passed_steps,  "#4caf50"],
              ["Failed",  run.failed_steps,  "#f44336"],
              ["Skipped", run.skipped_steps, "#9e9e9e"],
            ].map(([label, count, color]) => (
              <Stack key={String(label)} direction="row" spacing={0.5} alignItems="center">
                <Box sx={{ width: 8, height: 8, borderRadius: "50%", bgcolor: color }} />
                <Typography sx={{ fontSize: 12, color: "rgba(255,255,255,0.5)" }}>
                  {label}: {count}
                </Typography>
              </Stack>
            ))}
          </Stack>
        </Paper>
      )}

      {/* Field table */}
      <Paper sx={{ bgcolor: "#0d0d1a", borderRadius: 2, overflow: "hidden" }}>
        {rows.map(([label, value], i) => (
          <Box key={String(label)} sx={{
            display: "flex", px: 2, py: 1.5, alignItems: "center",
            bgcolor: i % 2 === 0 ? "transparent" : "rgba(255,255,255,0.02)",
          }}>
            <Typography sx={{ width: 130, fontSize: 12, color: "rgba(255,255,255,0.4)", fontWeight: 600 }}>
              {label}
            </Typography>
            {value}
          </Box>
        ))}
        {run.error_message && (
          <Box sx={{ px: 2, py: 1.5, bgcolor: "rgba(244,67,54,0.05)" }}>
            <Typography sx={{ fontSize: 12, color: "rgba(255,255,255,0.4)", fontWeight: 600, mb: 0.5 }}>
              Error
            </Typography>
            <Typography sx={{ fontSize: 13, color: "#f44336", fontFamily: "monospace", wordBreak: "break-all" }}>
              {run.error_message}
            </Typography>
          </Box>
        )}
      </Paper>
    </Box>
  );
}

// ── Steps Tab ────────────────────────────────────────────────────────────────

function StepsTab({ runId }: { runId: string }) {
  const { data: steps = [], isLoading } = useQuery({
    queryKey: ["run-steps", runId],
    queryFn: () => getRunSteps(runId),
    staleTime: 15_000,
  });

  if (isLoading) return <LinearProgress sx={{ mt: 2 }} />;
  if (!steps.length) return (
    <Typography sx={{ color: "rgba(255,255,255,0.4)", mt: 2 }}>No steps recorded yet.</Typography>
  );

  return (
    <Stack spacing={1} mt={1}>
      {steps.map((s) => {
        const stat = STATUS_CONFIG[s.status] ?? STATUS_CONFIG.QUEUED;
        const StatIcon = stat.Icon;
        return (
          <Paper key={s.id} sx={{ bgcolor: "#0d0d1a", borderRadius: 2, px: 2, py: 1.5,
            borderLeft: `3px solid ${stat.color}` }}>
            <Stack direction="row" alignItems="center" spacing={1.5}>
              <Typography sx={{ fontSize: 12, color: "rgba(255,255,255,0.3)", minWidth: 24, textAlign: "right" }}>
                {s.position}
              </Typography>
              <StatIcon sx={{ fontSize: 16, color: stat.color }} />
              <Box sx={{ flex: 1, minWidth: 0 }}>
                <Typography sx={{ fontSize: 13, color: "#fff", fontWeight: 500 }}>
                  {s.action}
                </Typography>
                {s.display_value && (
                  <Typography sx={{ fontSize: 12, color: "rgba(255,255,255,0.5)", mt: 0.25 }}>
                    {s.display_value}
                  </Typography>
                )}
                {s.error_message && (
                  <Typography sx={{ fontSize: 12, color: "#f44336", mt: 0.25, fontFamily: "monospace" }}>
                    {s.error_message}
                  </Typography>
                )}
              </Box>
              <Stack direction="row" spacing={2} alignItems="center">
                {s.duration_ms !== null && (
                  <Typography sx={{ fontSize: 12, color: "rgba(255,255,255,0.4)" }}>
                    {s.duration_ms < 1000 ? `${s.duration_ms}ms` : `${(s.duration_ms / 1000).toFixed(2)}s`}
                  </Typography>
                )}
                <Chip label={s.status} size="small"
                  sx={{ bgcolor: stat.bg, color: stat.color, fontWeight: 600, fontSize: 11 }} />
              </Stack>
            </Stack>
          </Paper>
        );
      })}
    </Stack>
  );
}

// ── Events Tab — live SSE + historic poll ────────────────────────────────────

function EventsTab({ runId, runStatus }: { runId: string; runStatus: string }) {
  const isActive = ["QUEUED", "DISPATCHED", "RUNNING"].includes(runStatus);

  // Historic events from REST (always fetched, used as the baseline)
  const { data: historicEvents = [], isLoading } = useQuery({
    queryKey: ["run-events", runId],
    queryFn: () => getRunEvents(runId),
    staleTime: isActive ? 0 : 60_000,
    refetchInterval: isActive ? 5_000 : false,
  });

  // Live SSE events (only opened while run is active)
  const { events: liveEvents, connected } = useRunStream(runId, {
    enabled: isActive,
    initialSequence: historicEvents.length > 0
      ? Math.max(...historicEvents.map((e) => e.sequence))
      : 0,
  });

  // Merge: start with historic, append live events that aren't already present
  const allEvents = useMemo(() => {
    const seen = new Set(historicEvents.map((e) => e.sequence));
    const newLive = liveEvents.filter((e) => !seen.has(e.sequence));
    return [...historicEvents, ...newLive].sort((a, b) => a.sequence - b.sequence);
  }, [historicEvents, liveEvents]);

  if (isLoading) return <LinearProgress sx={{ mt: 2 }} />;

  return (
    <Box mt={1}>
      {/* Live indicator */}
      {isActive && (
        <Stack direction="row" alignItems="center" spacing={1} mb={1.5}>
          <Box sx={{
            width: 8, height: 8, borderRadius: "50%",
            bgcolor: connected ? "#4caf50" : "#ff9800",
            animation: connected ? "pulse 1.5s ease-in-out infinite" : "none",
            "@keyframes pulse": {
              "0%, 100%": { opacity: 1 },
              "50%": { opacity: 0.3 },
            },
          }} />
          <Typography sx={{ fontSize: 12, color: connected ? "#4caf50" : "#ff9800" }}>
            {connected ? "Live stream connected" : "Connecting to live stream…"}
          </Typography>
          {liveEvents.length > 0 && (
            <Chip label={`+${liveEvents.length} live`} size="small"
              sx={{ fontSize: 10, bgcolor: "rgba(76,175,80,0.12)", color: "#4caf50" }} />
          )}
        </Stack>
      )}

      {!allEvents.length && (
        <Typography sx={{ color: "rgba(255,255,255,0.4)" }}>No events recorded yet.</Typography>
      )}

      <Stack spacing={0.25}>
        {allEvents.map((ev) => {
          const sev = SEVERITY_COLORS[ev.severity] ?? "#9e9e9e";
          const isNew = liveEvents.some((l) => l.sequence === ev.sequence);
          return (
            <Box key={ev.id ?? ev.sequence} sx={{
              display: "flex", gap: 2, px: 2, py: 1.25, borderRadius: 1.5,
              bgcolor: isNew ? "rgba(76,175,80,0.04)" : "rgba(255,255,255,0.02)",
              borderLeft: isNew ? "2px solid rgba(76,175,80,0.3)" : "2px solid transparent",
              "&:hover": { bgcolor: "rgba(255,255,255,0.04)" },
              transition: "background-color 0.3s",
            }}>
              <Typography sx={{ fontSize: 11, color: "rgba(255,255,255,0.3)", minWidth: 28, textAlign: "right" }}>
                #{ev.sequence}
              </Typography>
              <Typography sx={{ fontSize: 11, color: "rgba(255,255,255,0.35)", minWidth: 160, flexShrink: 0 }}>
                {new Date(ev.timestamp).toLocaleTimeString()}
              </Typography>
              <Chip label={ev.severity} size="small" sx={{
                fontSize: 10, fontWeight: 700, height: 18,
                bgcolor: `${sev}22`, color: sev, flexShrink: 0,
              }} />
              <Chip label={ev.event} size="small" sx={{
                fontSize: 10, fontFamily: "monospace",
                bgcolor: "rgba(102,126,234,0.1)", color: "#667eea", flexShrink: 0,
              }} />
              <Typography sx={{ fontSize: 12, color: "rgba(255,255,255,0.65)", flex: 1, wordBreak: "break-word" }}>
                {ev.message}
              </Typography>
            </Box>
          );
        })}
      </Stack>
    </Box>
  );
}

// ── Retries Tab ───────────────────────────────────────────────────────────────

function RetriesTab({ runId }: { runId: string }) {
  const navigate = useNavigate();
  const { data, isLoading } = useQuery({
    queryKey: ["retry-history", runId],
    queryFn: () => getRetryHistory(runId),
    staleTime: 30_000,
  });

  if (isLoading) return <LinearProgress sx={{ mt: 2 }} />;
  const retries = data?.retries ?? [];

  return (
    <Box mt={2}>
      {data && (
        <Typography sx={{ fontSize: 12, color: "rgba(255,255,255,0.4)", mb: 2 }}>
          Root run: <span style={{ color: "#667eea", fontFamily: "monospace" }}>
            {data.original_run_id.slice(0, 16)}…
          </span>
        </Typography>
      )}

      {/* Origin run */}
      <Stack direction="row" alignItems="center" spacing={1.5} sx={{ mb: 1 }}>
        <Box sx={{
          width: 28, height: 28, borderRadius: "50%",
          bgcolor: "rgba(102,126,234,0.15)", border: "1px solid #667eea",
          display: "flex", alignItems: "center", justifyContent: "center",
          fontSize: 11, color: "#667eea", fontWeight: 700,
        }}>
          0
        </Box>
        <Paper sx={{ flex: 1, bgcolor: "#0d0d1a", px: 2, py: 1, borderRadius: 2,
          border: data?.original_run_id === runId ? "1px solid #667eea" : "1px solid rgba(255,255,255,0.06)" }}>
          <Typography sx={{ fontSize: 13, color: "#fff" }}>
            Original run{" "}
            <span style={{ fontSize: 11, color: "#667eea", fontFamily: "monospace" }}>
              {data?.original_run_id?.slice(0, 12)}…
            </span>
          </Typography>
        </Paper>
      </Stack>

      {retries.map((r, i) => (
        <Stack key={r.run_id} direction="row" alignItems="center" spacing={1.5} sx={{ mb: 1 }}>
          {/* Connector line */}
          <Box sx={{ display: "flex", flexDirection: "column", alignItems: "center" }}>
            <Box sx={{ width: 1, height: 8, bgcolor: "rgba(255,255,255,0.1)" }} />
            <Box sx={{
              width: 28, height: 28, borderRadius: "50%",
              bgcolor: r.reason === "MANUAL" ? "rgba(76,175,80,0.15)" : "rgba(255,152,0,0.15)",
              border: `1px solid ${r.reason === "MANUAL" ? "#4caf50" : "#ff9800"}`,
              display: "flex", alignItems: "center", justifyContent: "center",
              fontSize: 11, fontWeight: 700,
              color: r.reason === "MANUAL" ? "#4caf50" : "#ff9800",
            }}>
              {r.attempt}
            </Box>
          </Box>
          <Paper sx={{ flex: 1, bgcolor: "#0d0d1a", px: 2, py: 1, borderRadius: 2,
            border: r.run_id === runId ? "1px solid #667eea" : "1px solid rgba(255,255,255,0.06)",
            cursor: "pointer", "&:hover": { borderColor: "#667eea" },
          }} onClick={() => navigate(`/runs/${r.run_id}`)}>
            <Stack direction="row" alignItems="center" spacing={1}>
              <Typography sx={{ fontSize: 13, color: "#fff", flex: 1 }}>
                Retry {r.attempt}
                {r.run_id === runId && (
                  <Chip label="current" size="small" sx={{ ml: 1, fontSize: 10,
                    bgcolor: "rgba(102,126,234,0.15)", color: "#667eea" }} />
                )}
              </Typography>
              <Chip label={r.reason} size="small" sx={{
                fontSize: 10, fontWeight: 600,
                bgcolor: r.reason === "MANUAL" ? "rgba(76,175,80,0.1)" : "rgba(255,152,0,0.1)",
                color: r.reason === "MANUAL" ? "#4caf50" : "#ff9800",
              }} />
              {r.delay_seconds > 0 && (
                <Typography sx={{ fontSize: 11, color: "rgba(255,255,255,0.4)" }}>
                  +{r.delay_seconds}s delay
                </Typography>
              )}
              <Typography sx={{ fontSize: 11, color: "#667eea", fontFamily: "monospace" }}>
                {r.run_id.slice(0, 8)}…
              </Typography>
            </Stack>
          </Paper>
        </Stack>
      ))}

      {!retries.length && (
        <Typography sx={{ color: "rgba(255,255,255,0.4)", mt: 2, fontSize: 13 }}>
          No retries for this run.
        </Typography>
      )}
    </Box>
  );
}

// ── Artifacts Tab ─────────────────────────────────────────────────────────────

const ARTIFACT_ICONS: Record<string, React.ReactNode> = {
  SCREENSHOT: <ScreenshotIcon sx={{ fontSize: 16 }} />,
  VIDEO:      <VideoIcon      sx={{ fontSize: 16 }} />,
  LOG:        <LogIcon        sx={{ fontSize: 16 }} />,
};

const ARTIFACT_COLORS: Record<string, string> = {
  SCREENSHOT: "#667eea",
  VIDEO:      "#e91e63",
  LOG:        "#4caf50",
  HAR:        "#ff9800",
  TRACE:      "#9c27b0",
};

function fmtBytes(n: number): string {
  if (n < 1024)        return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

function ArtifactsTab({ runId }: { runId: string }) {
  const { data, isLoading } = useQuery({
    queryKey: ["run-artifacts", runId],
    queryFn: () =>
      import("../../lib/api").then((m) =>
        m.default.get<{ total: number; items: any[] }>(`/runs/${runId}/artifacts`)
          .then((r) => r.data)
      ),
    staleTime: 30_000,
  });

  const artifacts = data?.items ?? [];

  if (isLoading) return <LinearProgress sx={{ mt: 2 }} />;

  if (!artifacts.length) return (
    <Box sx={{
      textAlign: "center", py: 6,
      border: "1px dashed rgba(255,255,255,0.08)",
      borderRadius: 2, mt: 1,
    }}>
      <Typography sx={{ color: "rgba(255,255,255,0.3)", fontSize: 13 }}>
        No artifacts have been uploaded for this run yet.
      </Typography>
      <Typography sx={{ color: "rgba(255,255,255,0.2)", fontSize: 12, mt: 0.5 }}>
        Agents upload screenshots, videos, logs and traces automatically.
      </Typography>
    </Box>
  );

  return (
    <Stack spacing={1} mt={1}>
      {artifacts.map((a: any) => {
        const color = ARTIFACT_COLORS[a.artifact_type] ?? "#9e9e9e";
        const icon = ARTIFACT_ICONS[a.artifact_type] ?? <LogIcon sx={{ fontSize: 16 }} />;
        return (
          <Paper key={a.id} sx={{
            bgcolor: "#0d0d1a",
            border: "1px solid rgba(255,255,255,0.06)",
            borderRadius: 2, px: 2, py: 1.5,
            "&:hover": { borderColor: `${color}44` },
            transition: "border-color 0.2s",
          }}>
            <Stack direction="row" alignItems="center" spacing={1.5}>
              <Box sx={{
                width: 32, height: 32, borderRadius: 1.5,
                bgcolor: `${color}18`,
                display: "flex", alignItems: "center", justifyContent: "center",
                color,
              }}>
                {icon}
              </Box>
              <Box sx={{ flex: 1, minWidth: 0 }}>
                <Typography sx={{ fontSize: 13, color: "#fff", fontWeight: 500 }}>
                  {a.filename}
                </Typography>
                <Stack direction="row" spacing={1.5} mt={0.25} alignItems="center">
                  <Chip label={a.artifact_type} size="small" sx={{
                    fontSize: 10, fontWeight: 600,
                    bgcolor: `${color}18`, color, border: "none",
                  }} />
                  <Typography sx={{ fontSize: 11, color: "rgba(255,255,255,0.35)" }}>
                    {fmtBytes(a.size_bytes)}
                  </Typography>
                  <Typography sx={{ fontSize: 11, color: "rgba(255,255,255,0.25)" }}>
                    {a.content_type}
                  </Typography>
                </Stack>
              </Box>
              <Tooltip title="Download">
                <IconButton
                  size="small"
                  component="a"
                  href={a.url}
                  download={a.filename}
                  sx={{ color, "&:hover": { bgcolor: `${color}14` } }}
                >
                  <DownloadIcon fontSize="small" />
                </IconButton>
              </Tooltip>
            </Stack>
          </Paper>
        );
      })}
    </Stack>
  );
}

// ── Raw JSON Tab ──────────────────────────────────────────────────────────────

function RawJsonTab({ run }: { run: TestRun }) {
  const [copied, setCopied] = useState(false);
  const json = JSON.stringify(run, null, 2);

  const copy = () => {
    navigator.clipboard.writeText(json).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  return (
    <Box sx={{ position: "relative", mt: 1 }}>
      <Tooltip title={copied ? "Copied!" : "Copy JSON"}>
        <IconButton onClick={copy} size="small"
          sx={{ position: "absolute", top: 8, right: 8, color: "#667eea", zIndex: 1 }}>
          <CopyIcon fontSize="small" />
        </IconButton>
      </Tooltip>
      <Box component="pre" sx={{
        bgcolor: "#0d0d1a", borderRadius: 2, p: 2,
        color: "rgba(255,255,255,0.75)", fontSize: 12,
        fontFamily: "monospace", overflowX: "auto",
        maxHeight: 600, border: "1px solid rgba(255,255,255,0.06)",
      }}>
        {json}
      </Box>
    </Box>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────

const TABS = ["Overview", "Steps", "Events", "Retries", "Artifacts", "Raw JSON"];

export default function RunDetailPage() {
  const { run_id } = useParams<{ run_id: string }>();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [tab, setTab] = useState(0);

  const { data: run, isLoading, isError } = useQuery({
    queryKey: ["run", run_id],
    queryFn: () => getRun(run_id!),
    staleTime: 15_000,
    refetchInterval: (q) => {
      const status = (q.state.data as TestRun | undefined)?.status;
      return status && ["QUEUED", "DISPATCHED", "RUNNING"].includes(status) ? 10_000 : false;
    },
  });

  const cancel = useMutation({
    mutationFn: () => cancelRun(run_id!),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["run", run_id] }),
  });
  const abort = useMutation({
    mutationFn: () => abortRun(run_id!),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["run", run_id] }),
  });

  if (isLoading) return (
    <Box sx={{ display: "flex", justifyContent: "center", mt: 8 }}>
      <CircularProgress sx={{ color: "#667eea" }} />
    </Box>
  );
  if (isError || !run) return (
    <Alert severity="error">Run not found or failed to load.</Alert>
  );

  const stat = STATUS_CONFIG[run.status] ?? STATUS_CONFIG.QUEUED;
  const StatIcon = stat.Icon;
  const priorColor = PRIORITY_CONFIG[run.priority]?.color ?? "#667eea";
  const isActive = ["QUEUED", "DISPATCHED", "RUNNING"].includes(run.status);

  return (
    <Box>
      {/* Back + header */}
      <Stack direction="row" alignItems="flex-start" spacing={2} mb={3}>
        <IconButton onClick={() => navigate("/runs")}
          sx={{ color: "rgba(255,255,255,0.5)", "&:hover": { color: "#fff" }, mt: 0.5 }}>
          <BackIcon />
        </IconButton>
        <Box sx={{ flex: 1 }}>
          <Stack direction="row" alignItems="center" spacing={1.5} flexWrap="wrap" gap={1}>
            <Chip
              label={run.status}
              icon={<StatIcon sx={{ fontSize: 14 }} />}
              sx={{ bgcolor: stat.bg, color: stat.color, fontWeight: 700 }}
            />
            <Chip label={run.priority}
              sx={{ bgcolor: `${priorColor}22`, color: priorColor, fontWeight: 600 }} />
            {run.retry_count > 0 && (
              <Chip label={`Retry #${run.retry_count}`} size="small"
                sx={{ bgcolor: "rgba(255,152,0,0.1)", color: "#ff9800", fontWeight: 600 }} />
            )}
            <Typography sx={{ fontSize: 12, color: "rgba(255,255,255,0.35)", fontFamily: "monospace" }}>
              {run.id}
            </Typography>
          </Stack>
          <Typography sx={{ fontSize: 13, color: "rgba(255,255,255,0.4)", mt: 0.5 }}>
            {fmtTs(run.triggered_at)}
            {run.started_at && ` · ${fmtDuration(run.started_at, run.completed_at)}`}
          </Typography>
        </Box>

        {/* Actions */}
        <Stack direction="row" spacing={1}>
          {["QUEUED", "DISPATCHED"].includes(run.status) && (
            <Button variant="outlined" size="small" startIcon={<CancelIcon />}
              onClick={() => cancel.mutate()} disabled={cancel.isPending}
              sx={{ color: "#ff9800", borderColor: "rgba(255,152,0,0.4)",
                    "&:hover": { borderColor: "#ff9800" } }}>
              Cancel
            </Button>
          )}
          {run.status === "RUNNING" && (
            <Button variant="outlined" size="small" startIcon={<AbortIcon />}
              onClick={() => abort.mutate()} disabled={abort.isPending}
              sx={{ color: "#f44336", borderColor: "rgba(244,67,54,0.4)",
                    "&:hover": { borderColor: "#f44336" } }}>
              Abort
            </Button>
          )}
          {["FAILED", "TIMED_OUT", "ABORTED", "COMPLETED"].includes(run.status) && (
            <Button variant="contained" size="small" startIcon={<RetryIcon />}
              onClick={() => navigate(`/runs/${run.id}/retry`)}
              sx={{ background: "linear-gradient(135deg, #667eea, #764ba2)" }}>
              Retry
            </Button>
          )}
        </Stack>
      </Stack>

      {/* Active indicator */}
      {isActive && <LinearProgress sx={{ mb: 2, borderRadius: 1,
        "& .MuiLinearProgress-bar": { background: "linear-gradient(90deg, #667eea, #764ba2)" } }} />}

      {/* Tabs */}
      <Box sx={{ borderBottom: "1px solid rgba(255,255,255,0.08)", mb: 3 }}>
        <Tabs value={tab} onChange={(_, v) => setTab(v)}
          sx={{
            "& .MuiTab-root": { color: "rgba(255,255,255,0.5)", textTransform: "none", fontWeight: 500 },
            "& .Mui-selected": { color: "#667eea" },
            "& .MuiTabs-indicator": { bgcolor: "#667eea" },
          }}>
          {TABS.map((t) => <Tab key={t} label={t} />)}
        </Tabs>
      </Box>

      {tab === 0 && <OverviewTab run={run} />}
      {tab === 1 && <StepsTab runId={run.id} />}
      {tab === 2 && <EventsTab runId={run.id} runStatus={run.status} />}
      {tab === 3 && <RetriesTab runId={run.id} />}
      {tab === 4 && <ArtifactsTab runId={run.id} />}
      {tab === 5 && <RawJsonTab run={run} />}
    </Box>
  );
}
