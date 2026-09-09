import { useQuery } from "@tanstack/react-query";
import { Box, Typography, Stack, LinearProgress, Paper, Tooltip } from "@mui/material";
import type { DurationParams } from "../../../lib/api/reports";
import { getDurationReport } from "../../../lib/api/reports";

function fmtSec(s: number | null): string {
  if (s == null) return "—";
  if (s < 60)   return `${s.toFixed(1)}s`;
  if (s < 3600) return `${(s / 60).toFixed(1)}m`;
  return `${(s / 3600).toFixed(2)}h`;
}

export default function DurationReportView({ params }: { params: DurationParams }) {
  const { data, isLoading } = useQuery({
    queryKey: ["report-duration", params],
    queryFn: () => getDurationReport(params),
    staleTime: 60_000,
  });

  if (isLoading) return <LinearProgress sx={{ mt: 2 }} />;

  const points = data?.data ?? [];

  if (!points.length) return (
    <Typography sx={{ color: "rgba(255,255,255,0.4)", mt: 2 }}>
      No completed runs with duration data for this period.
    </Typography>
  );

  // Global max for bar scaling
  const maxP95 = Math.max(...points.map((p) => p.p95_duration_seconds ?? 0), 1);

  // Overall averages
  const withAvg = points.filter((p) => p.avg_duration_seconds != null);
  const overallAvg = withAvg.length > 0
    ? withAvg.reduce((s, p) => s + (p.avg_duration_seconds ?? 0), 0) / withAvg.length
    : null;
  const withP95 = points.filter((p) => p.p95_duration_seconds != null);
  const overallP95 = withP95.length > 0
    ? Math.max(...withP95.map((p) => p.p95_duration_seconds ?? 0))
    : null;

  return (
    <Box>
      {/* Summary */}
      <Stack direction="row" spacing={2} sx={{ mb: 3, flexWrap: "wrap" }} >
        {[
          { label: "Avg Duration (overall)", value: fmtSec(overallAvg), color: "#667eea" },
          { label: "Max P95 Duration", value: fmtSec(overallP95), color: "#9c27b0" },
          { label: "Buckets with data", value: String(withAvg.length), color: "rgba(255,255,255,0.6)" },
        ].map((c) => (
          <Paper key={c.label} sx={{ bgcolor: "#0d0d1a", border: "1px solid rgba(255,255,255,0.06)", borderRadius: 2, p: 2.5, flex: 1, minWidth: 130 }}>
            <Typography sx={{ fontSize: 11, color: "rgba(255,255,255,0.4)", textTransform: "uppercase", letterSpacing: 1 }}>{c.label}</Typography>
            <Typography sx={{ fontSize: 26, fontWeight: 700, color: c.color, mt: 0.5 }}>{c.value}</Typography>
          </Paper>
        ))}
      </Stack>

      <Paper sx={{ bgcolor: "#0d0d1a", border: "1px solid rgba(255,255,255,0.06)", borderRadius: 2, overflow: "hidden" }}>
        <Stack direction="row" sx={{ alignItems: "center", px: 2.5, pt: 2, pb: 1 }}    spacing={2}>
          <Typography sx={{ fontSize: 13, fontWeight: 600, color: "rgba(255,255,255,0.7)" }}>
            Duration Trend · {data?.granularity} buckets
          </Typography>
          <Stack direction="row" spacing={1.5} sx={{ ml: "auto !important" }}>
            <Stack direction="row" sx={{ alignItems: "center" }} spacing={0.5}>
              <Box sx={{ width: 16, height: 4, borderRadius: 1, bgcolor: "#667eea" }} />
              <Typography sx={{ fontSize: 11, color: "rgba(255,255,255,0.4)" }}>Avg</Typography>
            </Stack>
            <Stack direction="row" sx={{ alignItems: "center" }} spacing={0.5}>
              <Box sx={{ width: 16, height: 4, borderRadius: 1, bgcolor: "#9c27b0", borderStyle: "dashed", border: "2px dashed #9c27b0" }} />
              <Typography sx={{ fontSize: 11, color: "rgba(255,255,255,0.4)" }}>P95</Typography>
            </Stack>
          </Stack>
        </Stack>

        {/* Header */}
        <Stack direction="row" spacing={2} sx={{ px: 2, py: 1, borderBottom: "1px solid rgba(255,255,255,0.06)", bgcolor: "rgba(255,255,255,0.02)" }}>
          <Typography sx={{ fontSize: 11, color: "rgba(255,255,255,0.35)", minWidth: 140 }}>Bucket</Typography>
          <Typography sx={{ fontSize: 11, color: "rgba(255,255,255,0.35)", minWidth: 60, textAlign: "right" }}>Runs</Typography>
          <Typography sx={{ fontSize: 11, color: "rgba(255,255,255,0.35)", minWidth: 80, textAlign: "right" }}>Avg</Typography>
          <Typography sx={{ fontSize: 11, color: "rgba(255,255,255,0.35)", flex: 1 }}>Duration (relative to max P95)</Typography>
          <Tooltip title="95th percentile — nearest-rank method">
            <Typography sx={{ fontSize: 11, color: "rgba(255,255,255,0.35)", minWidth: 80, textAlign: "right", cursor: "help", borderBottom: "1px dashed rgba(255,255,255,0.2)" }}>
              P95
            </Typography>
          </Tooltip>
        </Stack>

        {points.map((pt, i) => {
          const avgPct = maxP95 > 0 && pt.avg_duration_seconds != null ? Math.min((pt.avg_duration_seconds / maxP95) * 100, 100) : 0;
          const p95Pct = maxP95 > 0 && pt.p95_duration_seconds != null ? Math.min((pt.p95_duration_seconds / maxP95) * 100, 100) : 0;
          return (
            <Stack key={pt.date} direction="row"  spacing={2} sx={{ alignItems: "center", ...({
              px: 2, py: 1.25,
              borderBottom: i < points.length - 1 ? "1px solid rgba(255,255,255,0.04)" : "none",
              "&:hover": { bgcolor: "rgba(255,255,255,0.02)" },
            }) }}>
              <Typography sx={{ fontSize: 12, color: "rgba(255,255,255,0.5)", minWidth: 140 }}>{pt.date}</Typography>
              <Typography sx={{ fontSize: 12, color: "rgba(255,255,255,0.4)", minWidth: 60, textAlign: "right" }}>{pt.run_count}</Typography>
              <Typography sx={{ fontSize: 12, color: "#667eea", minWidth: 80, textAlign: "right" }}>{fmtSec(pt.avg_duration_seconds)}</Typography>
              {/* Stacked bar: avg (solid) + p95 (dashed overlay) */}
              <Box sx={{ flex: 1, height: 12, borderRadius: 3, bgcolor: "rgba(255,255,255,0.04)", position: "relative" }}>
                {p95Pct > 0 && (
                  <Box sx={{ position: "absolute", left: 0, top: 0, width: `${p95Pct}%`, height: "100%", borderRadius: 3, bgcolor: "rgba(156,39,176,0.25)", border: "1px dashed #9c27b0" }} />
                )}
                {avgPct > 0 && (
                  <Box sx={{ position: "absolute", left: 0, top: 2, height: 8, width: `${avgPct}%`, borderRadius: 2, bgcolor: "#667eea" }} />
                )}
              </Box>
              <Typography sx={{ fontSize: 12, color: "#9c27b0", minWidth: 80, textAlign: "right" }}>{fmtSec(pt.p95_duration_seconds)}</Typography>
            </Stack>
          );
        })}
      </Paper>
    </Box>
  );
}
