import { useQuery } from "@tanstack/react-query";
import { Box, Typography, Stack, LinearProgress, Paper } from "@mui/material";
import type { ReportParams } from "../../../lib/api/reports";
import { getQueueReport } from "../../../lib/api/reports";

function StatCard({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <Paper sx={{ bgcolor: "#0d0d1a", border: "1px solid rgba(255,255,255,0.06)", borderRadius: 2, p: 2, flex: 1 }}>
      <Typography sx={{ fontSize: 11, color: "rgba(255,255,255,0.4)", textTransform: "uppercase", letterSpacing: 1 }}>
        {label}
      </Typography>
      <Typography sx={{ fontSize: 26, fontWeight: 700, color: "#667eea", mt: 0.5 }}>{value}</Typography>
      {sub && <Typography sx={{ fontSize: 11, color: "rgba(255,255,255,0.3)", mt: 0.25 }}>{sub}</Typography>}
    </Paper>
  );
}

export default function QueueReportView({ params }: { params: ReportParams }) {
  const { data, isLoading } = useQuery({
    queryKey: ["report-queue", params],
    queryFn: () => getQueueReport(params),
    staleTime: 60_000,
  });

  if (isLoading) return <LinearProgress sx={{ mt: 2 }} />;
  if (!data || !data.data.length) return (
    <Typography sx={{ color: "rgba(255,255,255,0.4)", mt: 2 }}>No queue data for this period.</Typography>
  );

  const points = data.data;
  const dispatched = points.filter((p) => p.avg_wait_seconds !== null);
  const overallAvg = dispatched.length > 0
    ? dispatched.reduce((s, p) => s + (p.avg_wait_seconds ?? 0), 0) / dispatched.length
    : null;
  const overallMax = dispatched.length > 0
    ? Math.max(...dispatched.map((p) => p.max_wait_seconds ?? 0))
    : null;
  const totalRuns = points.reduce((s, p) => s + p.total_runs, 0);
  const maxWait = overallMax ?? 0;

  return (
    <Box>
      <Stack direction="row" spacing={2} sx={{ flexWrap: "wrap", mb: 3 }} >
        <StatCard
          label="Avg Queue Wait"
          value={overallAvg != null ? `${overallAvg.toFixed(1)}s` : "—"}
          sub="across dispatched runs"
        />
        <StatCard
          label="Max Queue Wait"
          value={overallMax != null ? `${overallMax.toFixed(1)}s` : "—"}
          sub="peak in period"
        />
        <StatCard label="Total Runs" value={String(totalRuns)} />
      </Stack>

      <Paper sx={{ bgcolor: "#0d0d1a", border: "1px solid rgba(255,255,255,0.06)", borderRadius: 2, p: 2.5 }}>
        <Typography sx={{ fontSize: 13, fontWeight: 600, color: "rgba(255,255,255,0.7)", mb: 2 }}>
          Queue Wait Over Time · {data.granularity} buckets
        </Typography>
        <Stack spacing={0.75}>
          {/* Header */}
          <Stack direction="row" spacing={1} sx={{ px: 1, pb: 1, borderBottom: "1px solid rgba(255,255,255,0.06)" }}>
            <Typography sx={{ fontSize: 11, color: "rgba(255,255,255,0.3)", minWidth: 140 }}>Bucket</Typography>
            <Typography sx={{ fontSize: 11, color: "rgba(255,255,255,0.3)", minWidth: 80, textAlign: "right" }}>Runs</Typography>
            <Typography sx={{ fontSize: 11, color: "rgba(255,255,255,0.3)", flex: 1 }}>Avg wait (s)</Typography>
            <Typography sx={{ fontSize: 11, color: "rgba(255,255,255,0.3)", minWidth: 90, textAlign: "right" }}>Max wait (s)</Typography>
          </Stack>
          {points.map((pt) => {
            const barPct = maxWait > 0 && pt.avg_wait_seconds != null
              ? Math.min((pt.avg_wait_seconds / maxWait) * 100, 100)
              : 0;
            return (
              <Stack key={pt.date} direction="row"  spacing={1} sx={{ alignItems: "center", ...({ px: 1, py: 0.5 }) }}>
                <Typography sx={{ fontSize: 11, color: "rgba(255,255,255,0.35)", minWidth: 140 }}>{pt.date}</Typography>
                <Typography sx={{ fontSize: 11, color: "rgba(255,255,255,0.5)", minWidth: 80, textAlign: "right" }}>{pt.total_runs}</Typography>
                <Box sx={{ flex: 1, height: 8, borderRadius: 2, bgcolor: "rgba(255,255,255,0.04)" }}>
                  {barPct > 0 && (
                    <Box sx={{ width: `${barPct}%`, height: "100%", borderRadius: 2, bgcolor: "#667eea" }} />
                  )}
                </Box>
                <Typography sx={{ fontSize: 11, color: "#667eea", minWidth: 90, textAlign: "right" }}>
                  {pt.max_wait_seconds != null ? pt.max_wait_seconds.toFixed(1) : "—"}
                </Typography>
              </Stack>
            );
          })}
        </Stack>
      </Paper>
    </Box>
  );
}
