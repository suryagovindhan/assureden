import { useQuery } from "@tanstack/react-query";
import { Box, Typography, Stack, LinearProgress, Paper } from "@mui/material";
import type { PassRateParams } from "../../../lib/api/reports";
import { getPassRateReport } from "../../../lib/api/reports";

function PassRateBar({ rate }: { rate: number | null }) {
  if (rate == null) return <Typography sx={{ fontSize: 12, color: "rgba(255,255,255,0.3)" }}>—</Typography>;
  const pct = rate * 100;
  const color = pct >= 90 ? "#4caf50" : pct >= 70 ? "#ff9800" : "#f44336";
  return (
    <Stack direction="row" sx={{ flex: 1, ...({ alignItems: "center" }) }} spacing={1} >
      <Box sx={{ flex: 1, height: 8, borderRadius: 2, bgcolor: "rgba(255,255,255,0.06)" }}>
        <Box sx={{ width: `${pct}%`, height: "100%", borderRadius: 2, bgcolor: color, transition: "width 0.5s" }} />
      </Box>
      <Typography sx={{ fontSize: 12, fontWeight: 700, color, minWidth: 48, textAlign: "right" }}>
        {pct.toFixed(1)}%
      </Typography>
    </Stack>
  );
}

export default function PassRateReportView({ params }: { params: PassRateParams }) {
  const { data, isLoading } = useQuery({
    queryKey: ["report-pass-rate", params],
    queryFn: () => getPassRateReport(params),
    staleTime: 60_000,
  });

  if (isLoading) return <LinearProgress sx={{ mt: 2 }} />;

  const points = data?.data ?? [];

  if (!points.length) return (
    <Typography sx={{ color: "rgba(255,255,255,0.4)", mt: 2 }}>
      No terminal runs for this period.
    </Typography>
  );

  // Overall stats
  const totalPassed = points.reduce((s, p) => s + p.passed, 0);
  const totalFailed = points.reduce((s, p) => s + p.failed, 0);
  const totalAll = totalPassed + totalFailed;
  const overallRate = totalAll > 0 ? totalPassed / totalAll : null;

  return (
    <Box>
      {/* Summary */}
      <Stack direction="row" spacing={2} sx={{ mb: 3, flexWrap: "wrap" }} >
        {[
          { label: "Overall Pass Rate", value: overallRate != null ? `${(overallRate * 100).toFixed(1)}%` : "—", color: overallRate != null && overallRate >= 0.9 ? "#4caf50" : "#ff9800" },
          { label: "Total Passed", value: String(totalPassed), color: "#4caf50" },
          { label: "Total Failed", value: String(totalFailed), color: "#f44336" },
        ].map((c) => (
          <Paper key={c.label} sx={{ bgcolor: "#0d0d1a", border: "1px solid rgba(255,255,255,0.06)", borderRadius: 2, p: 2.5, flex: 1, minWidth: 120 }}>
            <Typography sx={{ fontSize: 11, color: "rgba(255,255,255,0.4)", textTransform: "uppercase", letterSpacing: 1 }}>{c.label}</Typography>
            <Typography sx={{ fontSize: 26, fontWeight: 700, color: c.color, mt: 0.5 }}>{c.value}</Typography>
          </Paper>
        ))}
      </Stack>

      {/* Trend table */}
      <Paper sx={{ bgcolor: "#0d0d1a", border: "1px solid rgba(255,255,255,0.06)", borderRadius: 2, overflow: "hidden" }}>
        <Typography sx={{ px: 2.5, pt: 2, pb: 1, fontSize: 13, fontWeight: 600, color: "rgba(255,255,255,0.7)" }}>
          Pass Rate Trend · {data?.granularity} buckets
        </Typography>

        {/* Header row */}
        <Stack direction="row" spacing={2} sx={{ px: 2, py: 1, borderBottom: "1px solid rgba(255,255,255,0.06)", bgcolor: "rgba(255,255,255,0.02)" }}>
          <Typography sx={{ fontSize: 11, color: "rgba(255,255,255,0.35)", minWidth: 140 }}>Bucket</Typography>
          <Typography sx={{ fontSize: 11, color: "rgba(255,255,255,0.35)", minWidth: 60, textAlign: "right" }}>Total</Typography>
          <Typography sx={{ fontSize: 11, color: "rgba(255,255,255,0.35)", minWidth: 60, textAlign: "right" }}>Passed</Typography>
          <Typography sx={{ fontSize: 11, color: "rgba(255,255,255,0.35)", minWidth: 60, textAlign: "right" }}>Failed</Typography>
          <Typography sx={{ fontSize: 11, color: "rgba(255,255,255,0.35)", flex: 1 }}>Pass rate</Typography>
        </Stack>

        {points.map((pt, i) => (
          <Stack key={pt.date} direction="row"  spacing={2} sx={{ alignItems: "center", ...({
            px: 2, py: 1.25,
            borderBottom: i < points.length - 1 ? "1px solid rgba(255,255,255,0.04)" : "none",
            "&:hover": { bgcolor: "rgba(255,255,255,0.02)" },
          }) }}>
            <Typography sx={{ fontSize: 12, color: "rgba(255,255,255,0.5)", minWidth: 140 }}>{pt.date}</Typography>
            <Typography sx={{ fontSize: 12, color: "rgba(255,255,255,0.6)", minWidth: 60, textAlign: "right" }}>{pt.total}</Typography>
            <Typography sx={{ fontSize: 12, color: "#4caf50", minWidth: 60, textAlign: "right" }}>{pt.passed}</Typography>
            <Typography sx={{ fontSize: 12, color: "#f44336", minWidth: 60, textAlign: "right" }}>{pt.failed}</Typography>
            <PassRateBar rate={pt.pass_rate} />
          </Stack>
        ))}
      </Paper>
    </Box>
  );
}
