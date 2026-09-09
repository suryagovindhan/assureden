import { useQuery } from "@tanstack/react-query";
import { Box, Typography, Stack, LinearProgress, Paper, Chip, Tooltip } from "@mui/material";
import type { ReportParams } from "../../../lib/api/reports";
import { getAgentsReport } from "../../../lib/api/reports";

function fmtDur(s: number | null): string {
  if (s == null) return "—";
  if (s < 60)  return `${s.toFixed(1)}s`;
  return `${(s / 60).toFixed(1)}m`;
}

export default function AgentsReportView({ params }: { params: ReportParams }) {
  const { data, isLoading } = useQuery({
    queryKey: ["report-agents", params],
    queryFn: () => getAgentsReport(params),
    staleTime: 60_000,
  });

  if (isLoading) return <LinearProgress sx={{ mt: 2 }} />;

  const rows = data?.data ?? [];

  return (
    <Box>
      <Typography sx={{ fontSize: 13, fontWeight: 600, color: "rgba(255,255,255,0.6)", mb: 0.5 }}>
        Agent Execution Statistics
      </Typography>
      <Typography sx={{ fontSize: 12, color: "rgba(255,255,255,0.3)", mb: 2 }}>
        Run counts and duration metrics for the selected period. Sorted by run count descending.
      </Typography>

      {!rows.length ? (
        <Typography sx={{ color: "rgba(255,255,255,0.4)" }}>No agent activity in this period.</Typography>
      ) : (
        <Paper sx={{ bgcolor: "#0d0d1a", border: "1px solid rgba(255,255,255,0.06)", borderRadius: 2, overflow: "hidden" }}>
          {/* Header */}
          <Stack direction="row" spacing={2} sx={{
            px: 2, py: 1.25, borderBottom: "1px solid rgba(255,255,255,0.06)",
            bgcolor: "rgba(255,255,255,0.02)",
          }}>
            <Typography sx={{ fontSize: 11, color: "rgba(255,255,255,0.35)", flex: 2 }}>Agent</Typography>
            <Typography sx={{ fontSize: 11, color: "rgba(255,255,255,0.35)", minWidth: 70, textAlign: "right" }}>Runs</Typography>
            <Typography sx={{ fontSize: 11, color: "rgba(255,255,255,0.35)", minWidth: 70, textAlign: "right" }}>Passed</Typography>
            <Typography sx={{ fontSize: 11, color: "rgba(255,255,255,0.35)", minWidth: 70, textAlign: "right" }}>Failed</Typography>
            <Typography sx={{ fontSize: 11, color: "rgba(255,255,255,0.35)", minWidth: 90, textAlign: "right" }}>Avg dur</Typography>
            <Tooltip title="95th percentile duration — nearest-rank method">
              <Typography sx={{ fontSize: 11, color: "rgba(255,255,255,0.35)", minWidth: 90, textAlign: "right", cursor: "help", borderBottom: "1px dashed rgba(255,255,255,0.2)" }}>
                P95 dur
              </Typography>
            </Tooltip>
            <Typography sx={{ fontSize: 11, color: "rgba(255,255,255,0.35)", minWidth: 80, textAlign: "right" }}>Pass rate</Typography>
          </Stack>

          {rows.map((row, i) => {
            const passRate = row.run_count > 0 ? ((row.passed / row.run_count) * 100).toFixed(1) : "—";
            const passColor = Number(passRate) >= 90 ? "#4caf50"
              : Number(passRate) >= 70 ? "#ff9800" : "#f44336";
            return (
              <Stack key={row.agent_id} direction="row" alignItems="center" spacing={2} sx={{
                px: 2, py: 1.5,
                borderBottom: i < rows.length - 1 ? "1px solid rgba(255,255,255,0.04)" : "none",
                "&:hover": { bgcolor: "rgba(255,255,255,0.02)" },
              }}>
                <Box sx={{ flex: 2 }}>
                  <Typography sx={{ fontSize: 13, color: "#fff", fontWeight: 500 }}>
                    {row.agent_name ?? "Unknown"}
                  </Typography>
                  <Typography sx={{ fontSize: 10, color: "rgba(255,255,255,0.25)", fontFamily: "monospace" }}>
                    {row.agent_id.slice(0, 8)}…
                  </Typography>
                </Box>
                <Typography sx={{ fontSize: 13, color: "#667eea", fontWeight: 600, minWidth: 70, textAlign: "right" }}>
                  {row.run_count}
                </Typography>
                <Typography sx={{ fontSize: 13, color: "#4caf50", minWidth: 70, textAlign: "right" }}>
                  {row.passed}
                </Typography>
                <Typography sx={{ fontSize: 13, color: "#f44336", minWidth: 70, textAlign: "right" }}>
                  {row.failed}
                </Typography>
                <Typography sx={{ fontSize: 13, color: "rgba(255,255,255,0.65)", minWidth: 90, textAlign: "right" }}>
                  {fmtDur(row.avg_duration_seconds)}
                </Typography>
                <Typography sx={{ fontSize: 13, color: "rgba(255,255,255,0.5)", minWidth: 90, textAlign: "right" }}>
                  {fmtDur(row.p95_duration_seconds)}
                </Typography>
                <Typography sx={{ fontSize: 13, color: passColor, fontWeight: 600, minWidth: 80, textAlign: "right" }}>
                  {passRate}{passRate !== "—" ? "%" : ""}
                </Typography>
              </Stack>
            );
          })}
        </Paper>
      )}
    </Box>
  );
}
