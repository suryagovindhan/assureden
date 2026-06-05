import {
  Box, Typography, Table, TableBody, TableCell,
  TableContainer, TableHead, TableRow, Paper, Chip,
  IconButton, CircularProgress, Tooltip, Avatar, LinearProgress,
} from "@mui/material";
import { Refresh, Delete, FiberManualRecord } from "@mui/icons-material";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import api from "../../lib/api";

interface Agent {
  id: string;
  org_id: string;
  name: string;
  hostname: string | null;
  os_version: string | null;
  agent_version: string | null;
  protocol_version: number | null;
  payload_versions_supported: number[] | null;
  browser_versions: Record<string, string> | null;
  tags: string[] | null;
  max_parallel_sessions: number;
  current_parallel_sessions: number;
  status: string;
  last_heartbeat: string | null;
}

const STATUS_COLORS: Record<string, string> = {
  ONLINE:  "#66bb6a",
  IDLE:    "#42a5f5",
  RUNNING: "#ffa726",
  OFFLINE: "#757575",
};

export default function AgentsPage() {
  const qc = useQueryClient();

  const { data: agents = [], isLoading } = useQuery<Agent[]>({
    queryKey: ["agents"],
    queryFn: () => api.get("/agents/").then((r) => r.data),
    refetchInterval: 15_000,
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.delete(`/agents/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["agents"] }),
  });

  const capacityPct = (a: Agent) =>
    Math.round((a.current_parallel_sessions / Math.max(a.max_parallel_sessions, 1)) * 100);

  return (
    <Box>
      <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", mb: 3 }}>
        <Box>
          <Typography variant="h5" sx={{ fontWeight: 700, color: "#fff" }}>Agents</Typography>
          <Typography variant="body2" sx={{ color: "rgba(255,255,255,0.4)" }}>
            Real-time agent fleet — auto-refreshes every 15 s
          </Typography>
        </Box>
        <Tooltip title="Refresh now">
          <IconButton
            id="agents-refresh"
            onClick={() => qc.invalidateQueries({ queryKey: ["agents"] })}
            sx={{ color: "rgba(255,255,255,0.5)" }}
          >
            <Refresh />
          </IconButton>
        </Tooltip>
      </Box>

      <TableContainer
        component={Paper}
        sx={{
          background: "rgba(255,255,255,0.03)",
          border: "1px solid rgba(255,255,255,0.07)",
          borderRadius: 3,
        }}
      >
        <Table>
          <TableHead>
            <TableRow
              sx={{
                "& th": {
                  color: "rgba(255,255,255,0.4)", fontSize: 12, fontWeight: 600,
                  borderBottom: "1px solid rgba(255,255,255,0.07)",
                  letterSpacing: "0.05em", textTransform: "uppercase",
                },
              }}
            >
              <TableCell>Agent</TableCell>
              <TableCell>Status</TableCell>
              <TableCell>Version</TableCell>
              <TableCell>Tags</TableCell>
              <TableCell>Capacity</TableCell>
              <TableCell>Last Heartbeat</TableCell>
              <TableCell align="right">Actions</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {isLoading ? (
              <TableRow>
                <TableCell colSpan={7} align="center" sx={{ py: 4 }}>
                  <CircularProgress size={28} sx={{ color: "#667eea" }} />
                </TableCell>
              </TableRow>
            ) : agents.map((agent) => (
              <TableRow
                key={agent.id}
                sx={{
                  "& td": {
                    color: "rgba(255,255,255,0.8)",
                    borderBottom: "1px solid rgba(255,255,255,0.05)",
                  },
                  "&:hover": { background: "rgba(255,255,255,0.02)" },
                }}
              >
                <TableCell>
                  <Box sx={{ display: "flex", alignItems: "center", gap: 1.5 }}>
                    <Avatar sx={{ width: 34, height: 34, bgcolor: "rgba(102,126,234,0.3)", fontSize: 13, color: "#667eea" }}>
                      {agent.name[0].toUpperCase()}
                    </Avatar>
                    <Box>
                      <Typography sx={{ fontWeight: 500, fontSize: 14 }}>{agent.name}</Typography>
                      <Typography sx={{ fontSize: 11, color: "rgba(255,255,255,0.4)" }}>
                        {agent.hostname ?? "—"} · {agent.os_version ?? "—"}
                      </Typography>
                    </Box>
                  </Box>
                </TableCell>

                <TableCell>
                  <Box sx={{ display: "flex", alignItems: "center", gap: 0.8 }}>
                    <FiberManualRecord
                      sx={{ fontSize: 10, color: STATUS_COLORS[agent.status] ?? "#757575" }}
                    />
                    <Typography
                      sx={{ fontSize: 13, fontWeight: 500, color: STATUS_COLORS[agent.status] }}
                    >
                      {agent.status}
                    </Typography>
                  </Box>
                </TableCell>

                <TableCell>
                  <Typography sx={{ fontSize: 12, color: "rgba(255,255,255,0.6)" }}>
                    agent {agent.agent_version ?? "—"}
                  </Typography>
                  <Typography sx={{ fontSize: 11, color: "rgba(255,255,255,0.3)" }}>
                    payload [{(agent.payload_versions_supported ?? []).join(", ")}]
                  </Typography>
                </TableCell>

                <TableCell>
                  <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.5 }}>
                    {(agent.tags ?? []).map((tag) => (
                      <Chip
                        key={tag}
                        label={tag}
                        size="small"
                        sx={{
                          fontSize: 10, height: 20,
                          background: "rgba(102,126,234,0.15)",
                          color: "#667eea",
                          border: "1px solid rgba(102,126,234,0.25)",
                        }}
                      />
                    ))}
                  </Box>
                </TableCell>

                <TableCell sx={{ minWidth: 130 }}>
                  <Typography sx={{ fontSize: 12, color: "rgba(255,255,255,0.5)", mb: 0.5 }}>
                    {agent.current_parallel_sessions} / {agent.max_parallel_sessions} sessions
                  </Typography>
                  <LinearProgress
                    variant="determinate"
                    value={capacityPct(agent)}
                    sx={{
                      height: 4, borderRadius: 2,
                      bgcolor: "rgba(255,255,255,0.08)",
                      "& .MuiLinearProgress-bar": {
                        background:
                          capacityPct(agent) >= 90 ? "#ef5350"
                          : capacityPct(agent) >= 60 ? "#ffa726"
                          : "#66bb6a",
                        borderRadius: 2,
                      },
                    }}
                  />
                </TableCell>

                <TableCell sx={{ fontSize: 12, color: "rgba(255,255,255,0.4)" }}>
                  {agent.last_heartbeat
                    ? new Date(agent.last_heartbeat).toLocaleString()
                    : "Never"}
                </TableCell>

                <TableCell align="right">
                  <Tooltip title="Remove agent (soft)">
                    <IconButton
                      id={`delete-agent-${agent.id}`}
                      size="small"
                      onClick={() => deleteMutation.mutate(agent.id)}
                      sx={{ color: "#ef5350" }}
                    >
                      <Delete fontSize="small" />
                    </IconButton>
                  </Tooltip>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
    </Box>
  );
}
