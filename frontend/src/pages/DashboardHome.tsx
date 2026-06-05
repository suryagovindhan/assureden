import { Box, Typography, Grid, Card, CardContent } from "@mui/material";
import {
  Shield as ShieldIcon,
  Computer as AgentIcon,
  People as PeopleIcon,
  CheckCircleOutlined,
} from "@mui/icons-material";
import { useQuery } from "@tanstack/react-query";
import api from "../lib/api";
import { useAuth } from "../contexts/AuthContext";

interface AgentRow { id: string; status: string }

export default function DashboardHome() {
  const { user } = useAuth();

  const { data: agents = [] } = useQuery<AgentRow[]>({
    queryKey: ["agents"],
    queryFn: () => api.get("/agents/").then((r) => r.data),
  });

  const { data: users = [] } = useQuery<unknown[]>({
    queryKey: ["users"],
    queryFn: () => api.get("/users/").then((r) => r.data),
  });

  const onlineAgents = agents.filter((a) => a.status !== "OFFLINE").length;

  const stats = [
    { label: "Total Agents",   value: agents.length, sub: `${onlineAgents} online`, icon: <AgentIcon />,            color: "#667eea" },
    { label: "Team Members",   value: users.length,  sub: "in your org",            icon: <PeopleIcon />,           color: "#764ba2" },
    { label: "Phase",          value: "0",           sub: "Foundation Sprint",       icon: <ShieldIcon />,           color: "#42a5f5" },
    { label: "Status",         value: "Ready",       sub: "All systems operational", icon: <CheckCircleOutlined />,  color: "#66bb6a" },
  ];

  return (
    <Box>
      <Box sx={{ mb: 4 }}>
        <Typography variant="h4" sx={{ color: "#fff", fontWeight: 700 }}>
          Welcome back, {user?.username} 👋
        </Typography>
        <Typography sx={{ color: "rgba(255,255,255,0.4)", mt: 0.5 }}>
          AssureDen · Phase 0 Foundation ·{" "}
          {new Date().toLocaleDateString("en-GB", { dateStyle: "long" })}
        </Typography>
      </Box>

      <Grid container spacing={3}>
        {stats.map((stat) => (
          <Grid key={stat.label} size={{ xs: 12, sm: 6, md: 3 }}>
            <Card
              sx={{
                background: "rgba(255,255,255,0.03)",
                border: "1px solid rgba(255,255,255,0.07)",
                borderRadius: 3,
                transition: "transform 0.15s",
                "&:hover": {
                  transform: "translateY(-2px)",
                  border: `1px solid ${stat.color}40`,
                },
              }}
            >
              <CardContent sx={{ p: 2.5 }}>
                <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                  <Box>
                    <Typography
                      sx={{
                        fontSize: 12, color: "rgba(255,255,255,0.4)", fontWeight: 500,
                        textTransform: "uppercase", letterSpacing: 1,
                      }}
                    >
                      {stat.label}
                    </Typography>
                    <Typography variant="h4" sx={{ fontWeight: 700, color: "#fff", mt: 0.5 }}>
                      {stat.value}
                    </Typography>
                    <Typography sx={{ fontSize: 12, color: "rgba(255,255,255,0.4)", mt: 0.5 }}>
                      {stat.sub}
                    </Typography>
                  </Box>
                  <Box
                    sx={{
                      width: 44, height: 44, borderRadius: 2,
                      background: `${stat.color}20`,
                      border: `1px solid ${stat.color}30`,
                      display: "flex", alignItems: "center", justifyContent: "center",
                      color: stat.color,
                    }}
                  >
                    {stat.icon}
                  </Box>
                </Box>
              </CardContent>
            </Card>
          </Grid>
        ))}
      </Grid>

      <Box
        sx={{
          mt: 4, p: 3,
          background: "rgba(102,126,234,0.06)",
          border: "1px solid rgba(102,126,234,0.15)",
          borderRadius: 3,
        }}
      >
        <Typography sx={{ fontWeight: 600, color: "#fff", mb: 1 }}>
          🏗️  Phase 0 — Foundation Sprint
        </Typography>
        <Typography sx={{ fontSize: 13, color: "rgba(255,255,255,0.5)" }}>
          OrgScopedRepository enforced · JWT access + refresh tokens active ·
          Agent heartbeat + capacity tracking live · Soft-delete on all entities ·
          AuditEvent on every mutation · Redis + Celery configured ·
          Reserved schemas: Notification, Webhook, RBAC
        </Typography>
      </Box>
    </Box>
  );
}
