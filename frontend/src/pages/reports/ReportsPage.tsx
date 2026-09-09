/**
 * pages/reports/ReportsPage.tsx — Phase 8: Standalone reports shell.
 *
 * ## Structure
 *
 *   ReportsPage
 *     ├── Header (title + subtitle)
 *     ├── TimeRangeSelector  ← lifted state, shared across ALL sub-views
 *     ├── Sub-nav tabs (Runs / Queue / Schedules / Agents / Flakiness / Pass Rate / Duration)
 *     └── <ActiveView params={sharedParams} />
 *
 * The time-range state lives here so switching tabs never resets the selector.
 * Each sub-view gets the resolved params as a prop and issues its own query.
 */

import { useState } from "react";
import {
  Box, Typography, Stack, Tabs, Tab, Paper,
  ToggleButton, ToggleButtonGroup, TextField,
  Divider, Chip,
} from "@mui/material";
import {
  BarChart as RunsIcon,
  Timeline as QueueIcon,
  Schedule as ScheduleIcon,
  SmartToy as AgentIcon,
  BugReport as FlakyIcon,
  CheckCircleOutlined as PassIcon,
  Timer as DurIcon,
} from "@mui/icons-material";
import type { Period, ReportParams } from "../../lib/api/reports";
import RunsReportView      from "./views/RunsReportView";
import QueueReportView     from "./views/QueueReportView";
import SchedulesReportView from "./views/SchedulesReportView";
import AgentsReportView    from "./views/AgentsReportView";
import FlakinessReportView from "./views/FlakinessReportView";
import PassRateReportView  from "./views/PassRateReportView";
import DurationReportView  from "./views/DurationReportView";

// ── Sub-navigation definition ─────────────────────────────────────────────────

const VIEWS = [
  { label: "Runs",      icon: <RunsIcon     sx={{ fontSize: 17 }} />, key: "runs"      },
  { label: "Queue",     icon: <QueueIcon    sx={{ fontSize: 17 }} />, key: "queue"     },
  { label: "Schedules", icon: <ScheduleIcon sx={{ fontSize: 17 }} />, key: "schedules" },
  { label: "Agents",    icon: <AgentIcon    sx={{ fontSize: 17 }} />, key: "agents"    },
  { label: "Flakiness", icon: <FlakyIcon    sx={{ fontSize: 17 }} />, key: "flakiness" },
  { label: "Pass Rate", icon: <PassIcon     sx={{ fontSize: 17 }} />, key: "pass-rate" },
  { label: "Duration",  icon: <DurIcon      sx={{ fontSize: 17 }} />, key: "duration"  },
] as const;

type ViewKey = typeof VIEWS[number]["key"];

// ── Time range selector ───────────────────────────────────────────────────────

interface TimeRangeState {
  mode:   "period" | "custom";
  period: Period;
  since:  string;
  until:  string;
}

function toApiParams(tr: TimeRangeState): ReportParams {
  if (tr.mode === "custom" && tr.since && tr.until) {
    return { since: tr.since, until: tr.until };
  }
  return { period: tr.period };
}

function TimeRangeSelector({
  value, onChange,
}: {
  value: TimeRangeState;
  onChange: (v: TimeRangeState) => void;
}) {
  return (
    <Paper sx={{
      bgcolor: "#0d0d1a", border: "1px solid rgba(255,255,255,0.08)",
      borderRadius: 2, p: 1.5, display: "flex", alignItems: "center", gap: 2, flexWrap: "wrap",
    }}>
      <Typography sx={{ fontSize: 12, color: "rgba(255,255,255,0.4)", whiteSpace: "nowrap" }}>
        Time range
      </Typography>

      {/* Mode toggle */}
      <ToggleButtonGroup
        exclusive
        value={value.mode}
        onChange={(_, v) => v && onChange({ ...value, mode: v })}
        size="small"
        sx={{ "& .MuiToggleButton-root": { color: "rgba(255,255,255,0.4)", borderColor: "rgba(255,255,255,0.1)", px: 1.5, py: 0.5, fontSize: 12, textTransform: "none" },
              "& .Mui-selected": { color: "#667eea !important", bgcolor: "rgba(102,126,234,0.12) !important" } }}
      >
        <ToggleButton value="period">Preset</ToggleButton>
        <ToggleButton value="custom">Custom</ToggleButton>
      </ToggleButtonGroup>

      {value.mode === "period" ? (
        <ToggleButtonGroup
          exclusive
          value={value.period}
          onChange={(_, v) => v && onChange({ ...value, period: v as Period })}
          size="small"
          sx={{ "& .MuiToggleButton-root": { color: "rgba(255,255,255,0.4)", borderColor: "rgba(255,255,255,0.1)", px: 1.5, py: 0.5, fontSize: 12, textTransform: "none" },
                "& .Mui-selected": { color: "#667eea !important", bgcolor: "rgba(102,126,234,0.12) !important" } }}
        >
          {(["1d", "7d", "30d", "90d"] as Period[]).map((p) => (
            <ToggleButton key={p} value={p}>{p}</ToggleButton>
          ))}
        </ToggleButtonGroup>
      ) : (
        <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
          <TextField
            size="small" type="datetime-local"
            value={value.since}
            onChange={(e) => onChange({ ...value, since: e.target.value })}
            label="From"
            slotProps={{ inputLabel: { shrink: true } }}
            sx={{ input: { color: "#fff", fontSize: 12 }, label: { color: "rgba(255,255,255,0.4)" },
                  "& .MuiOutlinedInput-root": { borderRadius: 1.5,
                    "& fieldset": { borderColor: "rgba(255,255,255,0.1)" },
                    "&:hover fieldset": { borderColor: "rgba(102,126,234,0.5)" },
                  } }}
          />
          <Typography sx={{ color: "rgba(255,255,255,0.3)", fontSize: 12 }}>→</Typography>
          <TextField
            size="small" type="datetime-local"
            value={value.until}
            onChange={(e) => onChange({ ...value, until: e.target.value })}
            label="To"
            slotProps={{ inputLabel: { shrink: true } }}
            sx={{ input: { color: "#fff", fontSize: 12 }, label: { color: "rgba(255,255,255,0.4)" },
                  "& .MuiOutlinedInput-root": { borderRadius: 1.5,
                    "& fieldset": { borderColor: "rgba(255,255,255,0.1)" },
                    "&:hover fieldset": { borderColor: "rgba(102,126,234,0.5)" },
                  } }}
          />
        </Stack>
      )}

      {/* Effective range label */}
      <Chip
        label={value.mode === "period" ? `Last ${value.period}` : "Custom range"}
        size="small"
        sx={{ ml: "auto", fontSize: 10, bgcolor: "rgba(102,126,234,0.1)", color: "#667eea" }}
      />
    </Paper>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function ReportsPage() {
  const [activeView, setActiveView] = useState<ViewKey>("runs");
  const [timeRange, setTimeRange] = useState<TimeRangeState>({
    mode: "period", period: "7d", since: "", until: "",
  });

  const params = toApiParams(timeRange);
  const activeIdx = VIEWS.findIndex((v) => v.key === activeView);

  return (
    <Box sx={{ p: { xs: 2, md: 3 }, maxWidth: 1200, mx: "auto" }}>
      {/* Header */}
      <Stack direction="row" sx={{ alignItems: "flex-start", justifyContent: "space-between", mb: 2.5 }}  >
        <Box>
          <Typography variant="h5" sx={{ fontWeight: 700, color: "#fff", mb: 0.5 }}>
            Reports
          </Typography>
          <Typography sx={{ fontSize: 13, color: "rgba(255,255,255,0.4)" }}>
            Historical analysis and quality trends. The Dashboard is your live operational view;
            this is where you investigate.
          </Typography>
        </Box>
      </Stack>

      {/* Shared time-range selector */}
      <TimeRangeSelector value={timeRange} onChange={setTimeRange} />

      {/* Sub-navigation */}
      <Box sx={{ borderBottom: "1px solid rgba(255,255,255,0.08)", mt: 2.5, mb: 3 }}>
        <Tabs
          value={activeIdx}
          onChange={(_, i) => setActiveView(VIEWS[i].key)}
          variant="scrollable"
          scrollButtons="auto"
          sx={{
            "& .MuiTab-root": {
              color: "rgba(255,255,255,0.45)",
              textTransform: "none",
              fontWeight: 500,
              fontSize: 13,
              minHeight: 44,
              px: 2,
              gap: 0.75,
            },
            "& .Mui-selected": { color: "#667eea !important" },
            "& .MuiTabs-indicator": { bgcolor: "#667eea" },
          }}
        >
          {VIEWS.map((v) => (
            <Tab
              key={v.key}
              icon={v.icon}
              iconPosition="start"
              label={v.label}
              disableRipple={false}
            />
          ))}
        </Tabs>
      </Box>

      {/* Active view */}
      {activeView === "runs"      && <RunsReportView      params={params} />}
      {activeView === "queue"     && <QueueReportView     params={params} />}
      {activeView === "schedules" && <SchedulesReportView params={params} />}
      {activeView === "agents"    && <AgentsReportView    params={params} />}
      {activeView === "flakiness" && <FlakinessReportView params={params} />}
      {activeView === "pass-rate" && <PassRateReportView  params={params} />}
      {activeView === "duration"  && <DurationReportView  params={params} />}
    </Box>
  );
}
