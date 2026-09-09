import { useQuery } from "@tanstack/react-query";
import { Box, Typography, Stack, LinearProgress, Paper, Chip } from "@mui/material";
import type { ReportParams } from "../../../lib/api/reports";
import { getSchedulesReport } from "../../../lib/api/reports";

function RateBar({ value, color }: { value: number; color: string }) {
  return (
    <Box sx={{ display: "flex", alignItems: "center", gap: 1, flex: 1 }}>
      <Box sx={{ flex: 1, height: 6, borderRadius: 3, bgcolor: "rgba(255,255,255,0.06)" }}>
        <Box sx={{
          width: `${(value * 100).toFixed(1)}%`, height: "100%",
          borderRadius: 3, bgcolor: color, transition: "width 0.5s",
        }} />
      </Box>
      <Typography sx={{ fontSize: 11, color, minWidth: 44, textAlign: "right" }}>
        {(value * 100).toFixed(1)}%
      </Typography>
    </Box>
  );
}

export default function SchedulesReportView({ params }: { params: ReportParams }) {
  const { data, isLoading } = useQuery({
    queryKey: ["report-schedules", params],
    queryFn: () => getSchedulesReport(params),
    staleTime: 60_000,
  });

  if (isLoading) return <LinearProgress sx={{ mt: 2 }} />;

  const rows = data?.data ?? [];

  if (!rows.length) return (
    <Typography sx={{ color: "rgba(255,255,255,0.4)", mt: 2 }}>
      No schedule activity for this period.
    </Typography>
  );

  return (
    <Box>
      <Typography sx={{ fontSize: 12, color: "rgba(255,255,255,0.3)", mb: 2 }}>
        Sorted by miss rate — most unreliable first. Miss = SKIPPED + TRIGGER_FAILED.
      </Typography>

      <Stack spacing={1.5}>
        {rows.map((row) => {
          const hitColor = row.hit_rate >= 0.9 ? "#4caf50" : row.hit_rate >= 0.7 ? "#ff9800" : "#f44336";
          return (
            <Paper key={row.job_id} sx={{
              bgcolor: "#0d0d1a",
              border: `1px solid ${row.miss_rate > 0.3 ? "rgba(244,67,54,0.2)" : "rgba(255,255,255,0.06)"}`,
              borderRadius: 2, p: 2,
            }}>
              <Stack direction="row" alignItems="flex-start" spacing={2} mb={1.5}>
                <Box sx={{ flex: 1 }}>
                  <Typography sx={{ fontSize: 13, fontWeight: 600, color: "#fff" }}>{row.job_name}</Typography>
                  <Typography sx={{ fontSize: 11, color: "rgba(255,255,255,0.3)", fontFamily: "monospace" }}>
                    {row.job_id.slice(0, 8)}…
                  </Typography>
                </Box>
                <Stack direction="row" spacing={0.75}>
                  <Chip label={`${row.triggered} fired`} size="small" sx={{ fontSize: 10, bgcolor: "rgba(76,175,80,0.1)", color: "#4caf50" }} />
                  {row.skipped > 0 && (
                    <Chip label={`${row.skipped} skipped`} size="small" sx={{ fontSize: 10, bgcolor: "rgba(255,152,0,0.1)", color: "#ff9800" }} />
                  )}
                  {row.trigger_failed > 0 && (
                    <Chip label={`${row.trigger_failed} failed`} size="small" sx={{ fontSize: 10, bgcolor: "rgba(244,67,54,0.1)", color: "#f44336" }} />
                  )}
                </Stack>
              </Stack>

              <Stack spacing={0.75}>
                <Stack direction="row" alignItems="center" spacing={2}>
                  <Typography sx={{ fontSize: 11, color: "rgba(255,255,255,0.4)", minWidth: 60 }}>Hit rate</Typography>
                  <RateBar value={row.hit_rate} color={hitColor} />
                </Stack>
                <Stack direction="row" alignItems="center" spacing={2}>
                  <Typography sx={{ fontSize: 11, color: "rgba(255,255,255,0.4)", minWidth: 60 }}>Miss rate</Typography>
                  <RateBar value={row.miss_rate} color={row.miss_rate > 0 ? "#f44336" : "#4caf50"} />
                </Stack>
              </Stack>
            </Paper>
          );
        })}
      </Stack>
    </Box>
  );
}
