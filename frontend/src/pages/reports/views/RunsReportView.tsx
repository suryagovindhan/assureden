import { useQuery } from "@tanstack/react-query";
import {
  Box, Typography, Stack, Chip, LinearProgress,
  Grid, Paper,
} from "@mui/material";
import {
  CheckCircle as PassIcon,
  Cancel as FailIcon,
  HourglassEmpty as PendingIcon,
} from "@mui/icons-material";
import type { ReportParams } from "../../../lib/api/reports";
import { getRunsReport } from "../../../lib/api/reports";

const STATUS_COLORS: Record<string, string> = {
  COMPLETED:  "#4caf50",
  FAILED:     "#f44336",
  ABORTED:    "#e91e63",
  CANCELLED:  "#ff9800",
  TIMED_OUT:  "#9c27b0",
  RUNNING:    "#2196f3",
  DISPATCHED: "#00bcd4",
  QUEUED:     "#607d8b",
};

const PRIORITY_COLORS: Record<string, string> = {
  URGENT: "#f44336",
  HIGH:   "#ff9800",
  NORMAL: "#667eea",
  LOW:    "#607d8b",
};

function SummaryCard({ label, value, color }: { label: string; value: number | string; color: string }) {
  return (
    <Paper sx={{
      bgcolor: "#0d0d1a", border: "1px solid rgba(255,255,255,0.06)",
      borderRadius: 2, p: 2.5, flex: 1, minWidth: 120,
    }}>
      <Typography sx={{ fontSize: 11, color: "rgba(255,255,255,0.4)", textTransform: "uppercase", letterSpacing: 1 }}>
        {label}
      </Typography>
      <Typography sx={{ fontSize: 28, fontWeight: 700, color, mt: 0.5 }}>
        {value}
      </Typography>
    </Paper>
  );
}

function MiniBar({ label, value, total, color }: { label: string; value: number; total: number; color: string }) {
  const pct = total > 0 ? (value / total) * 100 : 0;
  return (
    <Box>
      <Stack direction="row" justifyContent="space-between" mb={0.5}>
        <Typography sx={{ fontSize: 12, color: "rgba(255,255,255,0.65)" }}>{label}</Typography>
        <Typography sx={{ fontSize: 12, color }}>
          {value} <Typography component="span" sx={{ fontSize: 11, color: "rgba(255,255,255,0.3)" }}>
            ({pct.toFixed(1)}%)
          </Typography>
        </Typography>
      </Stack>
      <Box sx={{ height: 6, borderRadius: 3, bgcolor: "rgba(255,255,255,0.06)" }}>
        <Box sx={{ width: `${pct}%`, height: "100%", borderRadius: 3, bgcolor: color, transition: "width 0.5s" }} />
      </Box>
    </Box>
  );
}

export default function RunsReportView({ params }: { params: ReportParams }) {
  const { data, isLoading } = useQuery({
    queryKey: ["report-runs", params],
    queryFn: () => getRunsReport(params),
    staleTime: 60_000,
  });

  if (isLoading) return <LinearProgress sx={{ mt: 2 }} />;
  if (!data) return null;

  const { total, by_status, by_priority } = data.data;

  return (
    <Box>
      {/* Summary cards */}
      <Stack direction="row" spacing={2} flexWrap="wrap" mb={3}>
        <SummaryCard label="Total Runs" value={total} color="#667eea" />
        <SummaryCard label="Passed" value={by_status["COMPLETED"] ?? 0} color="#4caf50" />
        <SummaryCard label="Failed" value={by_status["FAILED"] ?? 0} color="#f44336" />
        <SummaryCard label="Aborted/Cancelled" value={(by_status["ABORTED"] ?? 0) + (by_status["CANCELLED"] ?? 0)} color="#ff9800" />
      </Stack>

      <Grid container spacing={2}>
        {/* Status breakdown */}
        <Grid item xs={12} md={6}>
          <Paper sx={{ bgcolor: "#0d0d1a", border: "1px solid rgba(255,255,255,0.06)", borderRadius: 2, p: 2.5 }}>
            <Typography sx={{ fontSize: 13, fontWeight: 600, color: "rgba(255,255,255,0.7)", mb: 2 }}>
              By Status
            </Typography>
            <Stack spacing={1.5}>
              {Object.entries(by_status).map(([status, count]) => (
                <MiniBar
                  key={status}
                  label={status}
                  value={count}
                  total={total}
                  color={STATUS_COLORS[status] ?? "#9e9e9e"}
                />
              ))}
            </Stack>
          </Paper>
        </Grid>

        {/* Priority breakdown */}
        <Grid item xs={12} md={6}>
          <Paper sx={{ bgcolor: "#0d0d1a", border: "1px solid rgba(255,255,255,0.06)", borderRadius: 2, p: 2.5 }}>
            <Typography sx={{ fontSize: 13, fontWeight: 600, color: "rgba(255,255,255,0.7)", mb: 2 }}>
              By Priority
            </Typography>
            <Stack spacing={1.5}>
              {Object.entries(by_priority).map(([priority, count]) => (
                <MiniBar
                  key={priority}
                  label={priority}
                  value={count}
                  total={total}
                  color={PRIORITY_COLORS[priority] ?? "#9e9e9e"}
                />
              ))}
            </Stack>
          </Paper>
        </Grid>

        {/* Trend */}
        <Grid item xs={12}>
          <Paper sx={{ bgcolor: "#0d0d1a", border: "1px solid rgba(255,255,255,0.06)", borderRadius: 2, p: 2.5 }}>
            <Typography sx={{ fontSize: 13, fontWeight: 600, color: "rgba(255,255,255,0.7)", mb: 2 }}>
              Run Volume · {data.granularity} buckets
            </Typography>
            {data.data.trend.length === 0 ? (
              <Typography sx={{ color: "rgba(255,255,255,0.3)", fontSize: 13 }}>No runs in this period.</Typography>
            ) : (
              <Stack spacing={0.5}>
                {data.data.trend.map((pt) => {
                  const barPct = total > 0 ? (pt.count / Math.max(...data.data.trend.map((p) => p.count))) * 100 : 0;
                  return (
                    <Stack key={pt.date} direction="row" alignItems="center" spacing={1.5}>
                      <Typography sx={{ fontSize: 11, color: "rgba(255,255,255,0.35)", minWidth: 140 }}>
                        {pt.date}
                      </Typography>
                      <Box sx={{ flex: 1, height: 8, borderRadius: 2, bgcolor: "rgba(255,255,255,0.04)" }}>
                        <Box sx={{ width: `${barPct}%`, height: "100%", borderRadius: 2, bgcolor: "#667eea", transition: "width 0.5s" }} />
                      </Box>
                      <Typography sx={{ fontSize: 11, color: "#667eea", minWidth: 30, textAlign: "right" }}>
                        {pt.count}
                      </Typography>
                    </Stack>
                  );
                })}
              </Stack>
            )}
          </Paper>
        </Grid>
      </Grid>
    </Box>
  );
}
