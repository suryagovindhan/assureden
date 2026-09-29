/**
 * AllCasesPage.tsx — /test-cases/all
 *
 * Filterable, sortable table of all test cases across all suites.
 * Filters: status, priority, suite, tag, owner=me
 */

import { useState } from "react";
import { useAuth } from "../../contexts/AuthContext";
import { useNavigate, useSearchParams } from "react-router-dom";
import {
  Box, Typography, Chip, Button, TextField, Select,
  MenuItem, FormControl, InputLabel, InputAdornment, CircularProgress,
  Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Paper,
  Tooltip, IconButton,
} from "@mui/material";
import {
  Search as SearchIcon, Add as AddIcon, OpenInNew as OpenIcon,
  Refresh as RefreshIcon,
} from "@mui/icons-material";
import { useQuery } from "@tanstack/react-query";
import { casesApi, suitesApi, type TestCaseSummary } from "../../lib/api/testCases";

const STATUS_COLORS: Record<string, string> = {
  DRAFT: "#64748b", READY: "#22c55e", BLOCKED: "#ef4444", DEPRECATED: "#94a3b8",
};
const PRIORITY_COLORS: Record<string, string> = {
  CRITICAL: "#ef4444", HIGH: "#f97316", MEDIUM: "#f59e0b", LOW: "#22c55e",
};

export default function AllCasesPage() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [searchParams] = useSearchParams();
  const ownerMe = searchParams.get("owner") === "me";

  const [search, setSearch] = useState("");
  const [filterStatus, setFilterStatus] = useState("");
  const [filterPriority, setFilterPriority] = useState("");
  const [filterSuite, setFilterSuite] = useState("");

  const { data: suites = [] } = useQuery({
    queryKey: ["suites"],
    queryFn: () => suitesApi.list().then((r) => r.data),
  });

  const { data: cases = [], isLoading, refetch } = useQuery({
    queryKey: ["all-cases", filterStatus, filterPriority, filterSuite],
    queryFn: () =>
      casesApi.list({
        status: filterStatus || undefined,
        priority: filterPriority || undefined,
        suite_id: filterSuite || undefined,
        limit: 500,
      }).then((r) => r.data),
  });

  const { data: searchResults = [], isFetching: searching } = useQuery({
    queryKey: ["cases-search", search],
    queryFn: () => casesApi.search(search, { limit: 100 }).then((r) => r.data),
    enabled: search.length >= 2,
  });

  const displayCases: TestCaseSummary[] = search.length >= 2 ? searchResults : cases;

  const filtered = displayCases.filter((c) => {
    if (filterStatus && c.status !== filterStatus) return false;
    if (filterPriority && c.priority !== filterPriority) return false;
    if (filterSuite && c.suite_id !== filterSuite) return false;
    return true;
  });

  const selectSx = {
    color: "#e2e8f0",
    "& .MuiOutlinedInput-notchedOutline": { borderColor: "rgba(255,255,255,0.12)" },
    "&:hover .MuiOutlinedInput-notchedOutline": { borderColor: "#818cf8" },
    bgcolor: "rgba(255,255,255,0.04)",
  };

  return (
    <Box sx={{ p: 3, bgcolor: "#0d0d1a", minHeight: "100vh" }}>
      {/* Header */}
      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", mb: 3 }}>
        <Box>
          <Typography variant="h5" sx={{ color: "#e2e8f0", fontWeight: 800, background: "linear-gradient(135deg,#e2e8f0,#a5b4fc)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}>
            All Test Cases
          </Typography>
          <Typography variant="body2" sx={{ color: "#475569", mt: 0.3 }}>
            {filtered.length} case{filtered.length !== 1 ? "s" : ""}
            {ownerMe ? " assigned to me" : ""}
          </Typography>
        </Box>
        <Box sx={{ display: "flex", gap: 1 }}>
          {user && user.role !== "VIEWER" && <Button variant="outlined" onClick={() => navigate("/drafts")}>Record a test</Button>}
          <Tooltip title="Refresh">
            <IconButton onClick={() => refetch()} sx={{ color: "#64748b" }}>
              <RefreshIcon />
            </IconButton>
          </Tooltip>
          <Button
            variant="contained" startIcon={<AddIcon />}
            onClick={() => navigate("/test-cases")}
            sx={{ background: "linear-gradient(135deg,#6366f1,#8b5cf6)", "&:hover": { background: "linear-gradient(135deg,#818cf8,#a78bfa)" } }}
          >
            New Test Case
          </Button>
        </Box>
      </Box>

      {/* Filters */}
      <Box sx={{ display: "flex", gap: 1.5, mb: 2.5, flexWrap: "wrap", alignItems: "center" }}>
        <TextField
          size="small" placeholder="Search cases…" value={search}
          onChange={(e) => setSearch(e.target.value)}
          sx={{ width: 250, "& .MuiOutlinedInput-root": { bgcolor: "rgba(255,255,255,0.04)", "& fieldset": { borderColor: "rgba(255,255,255,0.12)" } }, input: { color: "#e2e8f0" } }}
          slotProps={{
            input: {
              startAdornment: (
                <InputAdornment position="start">
                  {searching
                    ? <CircularProgress size={14} sx={{ color: "#818cf8" }} />
                    : <SearchIcon sx={{ fontSize: 18, color: "#64748b" }} />}
                </InputAdornment>
              ),
            },
          }}
        />
        <FormControl size="small" sx={{ minWidth: 130 }}>
          <InputLabel sx={{ color: "#64748b" }}>Status</InputLabel>
          <Select value={filterStatus} onChange={(e) => setFilterStatus(e.target.value)} label="Status" sx={selectSx}>
            <MenuItem value="" sx={{ color: "#e2e8f0" }}>All</MenuItem>
            {["DRAFT", "READY", "BLOCKED", "DEPRECATED"].map((s) => (
              <MenuItem key={s} value={s} sx={{ color: STATUS_COLORS[s] }}>{s}</MenuItem>
            ))}
          </Select>
        </FormControl>
        <FormControl size="small" sx={{ minWidth: 130 }}>
          <InputLabel sx={{ color: "#64748b" }}>Priority</InputLabel>
          <Select value={filterPriority} onChange={(e) => setFilterPriority(e.target.value)} label="Priority" sx={selectSx}>
            <MenuItem value="" sx={{ color: "#e2e8f0" }}>All</MenuItem>
            {["CRITICAL", "HIGH", "MEDIUM", "LOW"].map((p) => (
              <MenuItem key={p} value={p} sx={{ color: PRIORITY_COLORS[p] }}>{p}</MenuItem>
            ))}
          </Select>
        </FormControl>
        <FormControl size="small" sx={{ minWidth: 160 }}>
          <InputLabel sx={{ color: "#64748b" }}>Suite</InputLabel>
          <Select value={filterSuite} onChange={(e) => setFilterSuite(e.target.value)} label="Suite" sx={selectSx}>
            <MenuItem value="" sx={{ color: "#e2e8f0" }}>All suites</MenuItem>
            {suites.map((s) => (
              <MenuItem key={s.id} value={s.id} sx={{ color: "#e2e8f0" }}>{s.name}</MenuItem>
            ))}
          </Select>
        </FormControl>
        {(filterStatus || filterPriority || filterSuite || search) && (
          <Button size="small" onClick={() => { setFilterStatus(""); setFilterPriority(""); setFilterSuite(""); setSearch(""); }} sx={{ color: "#64748b" }}>
            Clear
          </Button>
        )}
      </Box>

      {/* Table */}
      <TableContainer component={Paper} sx={{ bgcolor: "rgba(255,255,255,0.02)", border: "1px solid rgba(255,255,255,0.06)", borderRadius: 2 }}>
        <Table size="small">
          <TableHead>
            <TableRow sx={{ "& th": { color: "#64748b", fontSize: 11, textTransform: "uppercase", letterSpacing: 0.8, borderBottom: "1px solid rgba(255,255,255,0.06)", py: 1.5, bgcolor: "rgba(255,255,255,0.02)" } }}>
              <TableCell>Name</TableCell>
              <TableCell>Suite</TableCell>
              <TableCell>Status</TableCell>
              <TableCell>Priority</TableCell>
              <TableCell>Version</TableCell>
              <TableCell>Tags</TableCell>
              <TableCell>Updated</TableCell>
              <TableCell align="right">Open</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {isLoading ? (
              <TableRow>
                <TableCell colSpan={8} align="center" sx={{ py: 4 }}>
                  <CircularProgress size={24} sx={{ color: "#818cf8" }} />
                </TableCell>
              </TableRow>
            ) : filtered.length === 0 ? (
              <TableRow>
                <TableCell colSpan={8} align="center" sx={{ py: 4, color: "#475569" }}>
                  No test cases match the current filters.
                </TableCell>
              </TableRow>
            ) : (
              filtered.map((tc) => (
                <TableRow
                  key={tc.id}
                  hover
                  onClick={() => navigate(`/test-cases/${tc.id}`)}
                  sx={{
                    cursor: "pointer",
                    "& td": { borderBottom: "1px solid rgba(255,255,255,0.04)", color: "#e2e8f0", py: 1 },
                    "&:hover": { bgcolor: "rgba(99,102,241,0.06)" },
                  }}
                >
                  <TableCell>
                    <Typography variant="body2" sx={{ fontWeight: 600 }}>{tc.name}</Typography>
                  </TableCell>
                  <TableCell>
                    <Typography variant="caption" sx={{ color: "#64748b" }}>
                      {suites.find((s) => s.id === tc.suite_id)?.name ?? "—"}
                    </Typography>
                  </TableCell>
                  <TableCell>
                    <Chip label={tc.status} size="small"
                      sx={{ bgcolor: `${STATUS_COLORS[tc.status]}22`, color: STATUS_COLORS[tc.status], fontSize: 10, height: 18 }} />
                  </TableCell>
                  <TableCell>
                    <Chip label={tc.priority} size="small"
                      sx={{ bgcolor: `${PRIORITY_COLORS[tc.priority]}22`, color: PRIORITY_COLORS[tc.priority], fontSize: 10, height: 18 }} />
                  </TableCell>
                  <TableCell>
                    <Typography variant="caption" sx={{ color: "#64748b" }}>v{tc.version}</Typography>
                  </TableCell>
                  <TableCell>
                    <Box sx={{ display: "flex", gap: 0.5, flexWrap: "wrap" }}>
                      {(tc.tags ?? []).slice(0, 3).map((t) => (
                        <Chip key={t} label={t} size="small"
                          sx={{ bgcolor: "rgba(99,102,241,0.1)", color: "#a5b4fc", fontSize: 10, height: 16 }} />
                      ))}
                      {(tc.tags ?? []).length > 3 && (
                        <Chip label={`+${tc.tags!.length - 3}`} size="small" sx={{ bgcolor: "rgba(255,255,255,0.06)", color: "#64748b", fontSize: 10, height: 16 }} />
                      )}
                    </Box>
                  </TableCell>
                  <TableCell>
                    <Typography variant="caption" sx={{ color: "#475569" }}>
                      {new Date(tc.updated_at).toLocaleDateString()}
                    </Typography>
                  </TableCell>
                  <TableCell align="right" onClick={(e) => e.stopPropagation()}>
                    <IconButton size="small" onClick={() => navigate(`/test-cases/${tc.id}`)} sx={{ color: "#64748b", "&:hover": { color: "#818cf8" } }}>
                      <OpenIcon sx={{ fontSize: 15 }} />
                    </IconButton>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </TableContainer>
    </Box>
  );
}
