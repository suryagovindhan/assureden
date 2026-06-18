import { useState } from "react";
import { Outlet, useNavigate, useLocation } from "react-router-dom";
import { Link } from "react-router-dom";
import {
  Box, Drawer, AppBar, Toolbar, Typography,
  List, ListItemButton, ListItemIcon, ListItemText,
  Avatar, Menu, MenuItem, Divider, Chip, Tooltip,
  IconButton,
} from "@mui/material";
import {
  Dashboard as DashboardIcon,
  People as PeopleIcon,
  Computer as AgentIcon,
  Business as OrgIcon,
  Shield as ShieldIcon,
  Logout,
  ChevronRight,
  TouchApp as ObjectIcon,
  Search as SearchIcon,
  FolderOpen as RepoIcon,
  Assignment as CaseIcon,
  PlaylistAddCheck as AllCasesIcon,
  AccountTree as SuiteIcon,
} from "@mui/icons-material";
import { useAuth } from "../contexts/AuthContext";

const DRAWER_WIDTH = 240;

const NAV_GROUPS = [
  {
    label: null,
    items: [
      { label: "Dashboard", path: "/dashboard", icon: <DashboardIcon />, minRole: 0 },
    ],
  },
  {
    label: "Object Repository",
    items: [
      { label: "Explorer",       path: "/objects",        icon: <ObjectIcon />, minRole: 0 },
      { label: "Keyword Search", path: "/objects/search", icon: <SearchIcon />, minRole: 0 },
    ],
  },
  {
    label: "Test Cases",
    items: [
      { label: "Suites",     path: "/test-cases",     icon: <SuiteIcon />,    minRole: 0 },
      { label: "All Cases",  path: "/test-cases/all", icon: <AllCasesIcon />, minRole: 0 },
      { label: "My Cases",   path: "/test-cases/all?owner=me", icon: <CaseIcon />, minRole: 0 },
    ],
  },
  {
    label: "Admin",
    items: [
      { label: "Organizations", path: "/admin/organizations", icon: <OrgIcon />,    minRole: 3 },
      { label: "Users",         path: "/admin/users",         icon: <PeopleIcon />, minRole: 3 },
      { label: "Agents",        path: "/admin/agents",        icon: <AgentIcon />,  minRole: 3 },
    ],
  },
];

const ROLE_ORDER: Record<string, number> = { VIEWER: 0, TESTER: 1, LEAD: 2, ADMIN: 3 };

export default function DashboardShell() {
  const { user, logout } = useAuth();
  const location  = useLocation();
  const [anchorEl, setAnchorEl] = useState<null | HTMLElement>(null);

  const userRoleLevel = ROLE_ORDER[user?.role ?? "VIEWER"] ?? 0;
  const visibleGroups = NAV_GROUPS.map((g) => ({
    ...g,
    items: g.items.filter((item) => userRoleLevel >= item.minRole),
  })).filter((g) => g.items.length > 0);

  return (
    <Box sx={{ display: "flex", minHeight: "100vh", bgcolor: "#0d0d1a" }}>
      {/* ── Sidebar ─────────────────────────────────────────────── */}
      <Drawer
        variant="permanent"
        sx={{
          width: DRAWER_WIDTH,
          flexShrink: 0,
          "& .MuiDrawer-paper": {
            width: DRAWER_WIDTH,
            boxSizing: "border-box",
            background: "linear-gradient(180deg, #13132a 0%, #0d0d1a 100%)",
            borderRight: "1px solid rgba(255,255,255,0.06)",
          },
        }}
      >
        {/* Brand */}
        <Box sx={{ p: 2.5, display: "flex", alignItems: "center", gap: 1.5 }}>
          <Box
            sx={{
              width: 36, height: 36, borderRadius: 1.5,
              background: "linear-gradient(135deg, #667eea, #764ba2)",
              display: "flex", alignItems: "center", justifyContent: "center",
            }}
          >
            <ShieldIcon sx={{ color: "#fff", fontSize: 20 }} />
          </Box>
          <Typography sx={{ fontWeight: 700, color: "#fff", fontSize: 16 }}>
            AssureDen
          </Typography>
        </Box>

        <Divider sx={{ borderColor: "rgba(255,255,255,0.06)" }} />

        <List sx={{ px: 1, mt: 1 }}>
          {visibleGroups.map((group, gi) => (
            <Box key={gi}>
              {group.label && (
                <Typography sx={{
                  fontSize: 9.5, fontWeight: 700, color: "rgba(255,255,255,0.25)",
                  textTransform: "uppercase", letterSpacing: 1.2,
                  px: 1.5, pt: gi > 0 ? 2 : 0.5, pb: 0.75,
                }}>
                  {group.label}
                </Typography>
              )}
              {group.items.map((item) => {
                const active = location.pathname.startsWith(item.path);
                return (
                  <ListItemButton
                    key={item.path}
                    component={Link}
                    to={item.path}
                    sx={{
                      borderRadius: 2, mb: 0.5,
                      color: active ? "#fff" : "rgba(255,255,255,0.5)",
                      background: active ? "rgba(102,126,234,0.15)" : "transparent",
                      "&:hover": { background: "rgba(255,255,255,0.05)", color: "#fff" },
                      transition: "all 0.15s",
                    }}
                  >
                    <ListItemIcon sx={{ color: "inherit", minWidth: 36 }}>
                      {item.icon}
                    </ListItemIcon>
                    <ListItemText
                      primary={item.label}
                      slotProps={{ primary: { style: { fontSize: 14, fontWeight: active ? 600 : 400 } } }}
                    />
                    {active && <ChevronRight sx={{ fontSize: 16, opacity: 0.6 }} />}
                  </ListItemButton>
                );
              })}
            </Box>
          ))}
        </List>
      </Drawer>

      {/* ── Main area ────────────────────────────────────────────── */}
      <Box sx={{ flexGrow: 1, display: "flex", flexDirection: "column" }}>
        <AppBar
          position="static"
          elevation={0}
          sx={{
            background: "rgba(13,13,26,0.8)",
            backdropFilter: "blur(10px)",
            borderBottom: "1px solid rgba(255,255,255,0.06)",
          }}
        >
          <Toolbar sx={{ justifyContent: "flex-end" }}>
            <Chip
              label={user?.role}
              size="small"
              sx={{
                mr: 1.5,
                background: "rgba(102,126,234,0.2)",
                color: "#667eea",
                fontWeight: 600,
                border: "1px solid rgba(102,126,234,0.3)",
              }}
            />
            <Tooltip title="Account">
              <IconButton
                id="user-menu-button"
                onClick={(e) => setAnchorEl(e.currentTarget)}
                sx={{ p: 0.5 }}
              >
                <Avatar sx={{ width: 34, height: 34, bgcolor: "#667eea", fontSize: 14 }}>
                  {user?.username?.[0]?.toUpperCase()}
                </Avatar>
              </IconButton>
            </Tooltip>
          </Toolbar>
        </AppBar>

        {/* User menu */}
        <Menu
          anchorEl={anchorEl}
          open={Boolean(anchorEl)}
          onClose={() => setAnchorEl(null)}
          slotProps={{
            paper: {
              sx: {
                background: "#1a1a2e",
                border: "1px solid rgba(255,255,255,0.1)",
                borderRadius: 2,
                mt: 1,
              },
            },
          }}
        >
          <MenuItem disabled sx={{ color: "rgba(255,255,255,0.5)", fontSize: 13 }}>
            {user?.email}
          </MenuItem>
          <Divider sx={{ borderColor: "rgba(255,255,255,0.08)" }} />
          <MenuItem
            id="logout-button"
            onClick={() => { setAnchorEl(null); logout(); }}
            sx={{ color: "#ef5350", gap: 1 }}
          >
            <Logout fontSize="small" /> Sign out
          </MenuItem>
        </Menu>

        {/* Page content */}
        <Box sx={{ flexGrow: 1, p: 3, overflowY: "auto" }}>
          <Outlet />
        </Box>
      </Box>
    </Box>
  );
}
