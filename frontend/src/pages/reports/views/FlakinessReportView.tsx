import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Box, Typography, Stack, LinearProgress, Paper, Chip,
  Slider, Tooltip, TextField,
} from "@mui/material";
import type { FlakinessParams } from "../../../lib/api/reports";
import { getFlakinessReport } from "../../../lib/api/reports";

function scoreColor(score: number): string {
  if (score >= 0.4) return "#f44336";
  if (score >= 0.1) return "#ff9800";
  return "#4caf50";
}

function ScoreBadge({ score }: { score: number }) {
  const color = scoreColor(score);
  return (
    <Tooltip title={`${(score * 100).toFixed(1)}% — adjacent flip rate`}>
      <Box sx={{
        px: 1.5, py: 0.5, borderRadius: 1.5,
        bgcolor: `${color}18`, border: `1px solid ${color}44`,
        display: "inline-flex", alignItems: "center", gap: 0.5,
      }}>
        <Box sx={{ width: 6, height: 6, borderRadius: "50%", bgcolor: color }} />
        <Typography sx={{ fontSize: 12, fontWeight: 700, color }}>
          {(score * 100).toFixed(1)}%
        </Typography>
      </Box>
    </Tooltip>
  );
}

export default function FlakinessReportView({ params }: { params: FlakinessParams }) {
  const [minScore, setMinScore] = useState<number | undefined>(undefined);

  const queryParams: FlakinessParams = {
    ...params,
    ...(minScore !== undefined ? { min_score: minScore } : {}),
  };

  const { data, isLoading } = useQuery({
    queryKey: ["report-flakiness", queryParams],
    queryFn: () => getFlakinessReport(queryParams),
    staleTime: 60_000,
  });

  const rows = data?.data ?? [];

  return (
    <Box>
      {/* Filter controls */}
      <Paper sx={{ bgcolor: "#0d0d1a", border: "1px solid rgba(255,255,255,0.06)", borderRadius: 2, p: 2, mb: 2.5 }}>
        <Stack direction="row" alignItems="center" spacing={3} flexWrap="wrap">
          <Typography sx={{ fontSize: 12, color: "rgba(255,255,255,0.5)", minWidth: 120 }}>
            Min flakiness score
          </Typography>
          <Box sx={{ flex: 1, minWidth: 200, maxWidth: 400 }}>
            <Slider
              value={minScore ?? 0}
              onChange={(_, v) => setMinScore(v as number === 0 ? undefined : v as number)}
              min={0} max={1} step={0.05}
              valueLabelDisplay="auto"
              valueLabelFormat={(v) => `${(v * 100).toFixed(0)}%`}
              sx={{
                color: "#667eea",
                "& .MuiSlider-thumb": { bgcolor: "#667eea" },
                "& .MuiSlider-rail": { bgcolor: "rgba(255,255,255,0.1)" },
              }}
            />
          </Box>
          <Typography sx={{ fontSize: 12, color: "#667eea", minWidth: 50 }}>
            {minScore !== undefined ? `≥ ${(minScore * 100).toFixed(0)}%` : "Any"}
          </Typography>
        </Stack>
      </Paper>

      {/* Legend */}
      <Stack direction="row" spacing={2} mb={2} alignItems="center">
        <Typography sx={{ fontSize: 11, color: "rgba(255,255,255,0.3)" }}>Score bands:</Typography>
        {[
          { label: "< 10% (stable)",   color: "#4caf50" },
          { label: "10–40% (flaky)",   color: "#ff9800" },
          { label: "> 40% (very flaky)", color: "#f44336" },
        ].map((b) => (
          <Chip key={b.label} label={b.label} size="small"
            sx={{ fontSize: 10, bgcolor: `${b.color}18`, color: b.color }} />
        ))}
      </Stack>

      {isLoading && <LinearProgress sx={{ mb: 2 }} />}

      {!rows.length && !isLoading ? (
        <Box sx={{
          textAlign: "center", py: 6,
          border: "1px dashed rgba(255,255,255,0.08)", borderRadius: 2,
        }}>
          <Typography sx={{ color: "rgba(255,255,255,0.4)", fontSize: 13 }}>
            No flaky tests found.
          </Typography>
          <Typography sx={{ color: "rgba(255,255,255,0.25)", fontSize: 12, mt: 0.5 }}>
            Tests need ≥ 3 terminal runs with at least 1 flip to appear here.
          </Typography>
        </Box>
      ) : (
        <Paper sx={{ bgcolor: "#0d0d1a", border: "1px solid rgba(255,255,255,0.06)", borderRadius: 2, overflow: "hidden" }}>
          {/* Header */}
          <Stack direction="row" spacing={2} sx={{
            px: 2, py: 1.25,
            borderBottom: "1px solid rgba(255,255,255,0.06)",
            bgcolor: "rgba(255,255,255,0.02)",
          }}>
            <Typography sx={{ fontSize: 11, color: "rgba(255,255,255,0.35)", flex: 3 }}>Test Case</Typography>
            <Typography sx={{ fontSize: 11, color: "rgba(255,255,255,0.35)", minWidth: 60, textAlign: "right" }}>Runs</Typography>
            <Typography sx={{ fontSize: 11, color: "rgba(255,255,255,0.35)", minWidth: 60, textAlign: "right" }}>Passed</Typography>
            <Typography sx={{ fontSize: 11, color: "rgba(255,255,255,0.35)", minWidth: 60, textAlign: "right" }}>Failed</Typography>
            <Typography sx={{ fontSize: 11, color: "rgba(255,255,255,0.35)", minWidth: 60, textAlign: "right" }}>Flips</Typography>
            <Typography sx={{ fontSize: 11, color: "rgba(255,255,255,0.35)", minWidth: 100, textAlign: "right" }}>Score</Typography>
          </Stack>

          {rows.map((row, i) => (
            <Stack key={row.test_case_id} direction="row" alignItems="center" spacing={2} sx={{
              px: 2, py: 1.5,
              borderBottom: i < rows.length - 1 ? "1px solid rgba(255,255,255,0.04)" : "none",
              "&:hover": { bgcolor: "rgba(255,255,255,0.02)" },
            }}>
              <Box sx={{ flex: 3, minWidth: 0 }}>
                <Typography sx={{ fontSize: 13, color: "#fff", fontWeight: 500, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {row.test_case_name ?? "Unnamed"}
                </Typography>
                <Typography sx={{ fontSize: 10, color: "rgba(255,255,255,0.25)", fontFamily: "monospace" }}>
                  {row.test_case_id.slice(0, 8)}…
                </Typography>
              </Box>
              <Typography sx={{ fontSize: 13, color: "rgba(255,255,255,0.6)", minWidth: 60, textAlign: "right" }}>{row.runs}</Typography>
              <Typography sx={{ fontSize: 13, color: "#4caf50", minWidth: 60, textAlign: "right" }}>{row.passed}</Typography>
              <Typography sx={{ fontSize: 13, color: "#f44336", minWidth: 60, textAlign: "right" }}>{row.failed}</Typography>
              <Typography sx={{ fontSize: 13, color: "#ff9800", minWidth: 60, textAlign: "right" }}>{row.flip_count}</Typography>
              <Box sx={{ minWidth: 100, display: "flex", justifyContent: "flex-end" }}>
                <ScoreBadge score={row.flakiness_score} />
              </Box>
            </Stack>
          ))}
        </Paper>
      )}
    </Box>
  );
}
