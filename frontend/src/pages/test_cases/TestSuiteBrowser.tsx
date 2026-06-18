/**
 * TestSuiteBrowser.tsx — /test-cases
 *
 * Two-panel layout:
 *   Left:  Suite list with case count badges, search, + Create Suite
 *   Right: Cases in selected suite (or empty state)
 */

import { useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Box, Typography, List, ListItemButton, Chip, Button,
  TextField, InputAdornment, Skeleton, IconButton, Tooltip,
  Dialog, DialogTitle, DialogContent, DialogActions,
} from "@mui/material";
import {
  Add as AddIcon, Search as SearchIcon,
  FolderSpecial as SuiteIcon, PlaylistAdd as CaseIcon,
  Archive as ArchiveIcon,
} from "@mui/icons-material";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { suitesApi, casesApi, type TestSuiteRead, type TestCaseSummary } from "../../lib/api/testCases";

const PRIORITY_COLORS: Record<string, string> = {
  CRITICAL: "#ef4444", HIGH: "#f97316", MEDIUM: "#f59e0b", LOW: "#22c55e",
};
const STATUS_COLORS: Record<string, string> = {
  DRAFT: "#64748b", READY: "#22c55e", BLOCKED: "#ef4444", DEPRECATED: "#94a3b8",
};

const dialogPaper = {
  bgcolor: "#1e1e3a",
  border: "1px solid rgba(255,255,255,0.1)",
  borderRadius: 3,
  minWidth: 420,
};

const textFieldSx = {
  "& .MuiOutlinedInput-root": {
    background: "rgba(255,255,255,0.04)",
    "& fieldset": { borderColor: "rgba(255,255,255,0.12)" },
  },
  input: { color: "#e2e8f0" },
  textarea: { color: "#e2e8f0" },
  "& .MuiInputLabel-root": { color: "#64748b" },
};

function CreateSuiteDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [desc, setDesc] = useState("");

  const { mutate, isPending } = useMutation({
    mutationFn: () => suitesApi.create({ name, description: desc || undefined }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["suites"] });
      onClose();
      setName("");
      setDesc("");
    },
  });

  return (
    <Dialog open={open} onClose={onClose} slotProps={{ paper: { sx: dialogPaper } }}>
      <DialogTitle sx={{ color: "#e2e8f0" }}>Create Test Suite</DialogTitle>
      <DialogContent sx={{ display: "flex", flexDirection: "column", gap: 2, pt: "12px !important" }}>
        <TextField label="Suite name" value={name} onChange={(e) => setName(e.target.value)} autoFocus fullWidth sx={textFieldSx} />
        <TextField label="Description (optional)" value={desc} onChange={(e) => setDesc(e.target.value)} multiline rows={3} fullWidth sx={textFieldSx} />
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button onClick={onClose} sx={{ color: "#64748b" }}>Cancel</Button>
        <Button variant="contained" disabled={!name.trim() || isPending} onClick={() => mutate()}
          sx={{ background: "linear-gradient(135deg,#6366f1,#8b5cf6)", "&:hover": { background: "linear-gradient(135deg,#818cf8,#a78bfa)" } }}>
          {isPending ? "Creating…" : "Create Suite"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

function CreateCaseDialog({ suiteId, open, onClose }: { suiteId: string; open: boolean; onClose: () => void }) {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [priority, setPriority] = useState<"LOW" | "MEDIUM" | "HIGH" | "CRITICAL">("MEDIUM");

  const { mutate, isPending } = useMutation({
    mutationFn: () => casesApi.create({ name, suite_id: suiteId, priority }),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ["suite-cases", suiteId] });
      navigate(`/test-cases/${res.data.id}`);
      onClose();
    },
  });

  return (
    <Dialog open={open} onClose={onClose} slotProps={{ paper: { sx: dialogPaper } }}>
      <DialogTitle sx={{ color: "#e2e8f0" }}>Create Test Case</DialogTitle>
      <DialogContent sx={{ display: "flex", flexDirection: "column", gap: 2, pt: "12px !important" }}>
        <TextField label="Test case name" value={name} onChange={(e) => setName(e.target.value)} autoFocus fullWidth sx={textFieldSx} />
        <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap" }}>
          {(["LOW", "MEDIUM", "HIGH", "CRITICAL"] as const).map((p) => (
            <Chip key={p} label={p} onClick={() => setPriority(p)}
              sx={{
                cursor: "pointer",
                bgcolor: priority === p ? `${PRIORITY_COLORS[p]}33` : "rgba(255,255,255,0.05)",
                color: priority === p ? PRIORITY_COLORS[p] : "#94a3b8",
                border: priority === p ? `1px solid ${PRIORITY_COLORS[p]}` : "1px solid transparent",
              }} />
          ))}
        </Box>
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button onClick={onClose} sx={{ color: "#64748b" }}>Cancel</Button>
        <Button variant="contained" disabled={!name.trim() || isPending} onClick={() => mutate()}
          sx={{ background: "linear-gradient(135deg,#6366f1,#8b5cf6)", "&:hover": { background: "linear-gradient(135deg,#818cf8,#a78bfa)" } }}>
          {isPending ? "Creating…" : "Create & Open"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

export default function TestSuiteBrowser() {
  const navigate = useNavigate();
  const [selectedSuite, setSelectedSuite] = useState<TestSuiteRead | null>(null);
  const [suiteSearch, setSuiteSearch] = useState("");
  const [showCreateSuite, setShowCreateSuite] = useState(false);
  const [showCreateCase, setShowCreateCase] = useState(false);

  const { data: suites = [], isLoading: suitesLoading } = useQuery({
    queryKey: ["suites"],
    queryFn: () => suitesApi.list().then((r) => r.data),
  });

  const { data: cases = [], isLoading: casesLoading } = useQuery({
    queryKey: ["suite-cases", selectedSuite?.id],
    queryFn: () => suitesApi.cases(selectedSuite!.id).then((r) => r.data),
    enabled: !!selectedSuite,
  });

  const filteredSuites = suites.filter((s) =>
    s.name.toLowerCase().includes(suiteSearch.toLowerCase()),
  );

  return (
    <Box sx={{ display: "flex", height: "calc(100vh - 64px)", bgcolor: "#0d0d1a" }}>
      {/* Left — suite list */}
      <Box sx={{ width: 300, borderRight: "1px solid rgba(255,255,255,0.06)", display: "flex", flexDirection: "column" }}>
        {/* Header */}
        <Box sx={{ p: 2, borderBottom: "1px solid rgba(255,255,255,0.06)" }}>
          <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 1.5 }}>
            <Typography variant="subtitle2" sx={{ color: "#94a3b8", textTransform: "uppercase", letterSpacing: 1, fontSize: 11 }}>
              Test Suites
            </Typography>
            <Tooltip title="Create Suite">
              <IconButton size="small" onClick={() => setShowCreateSuite(true)} sx={{ color: "#818cf8", "&:hover": { bgcolor: "rgba(99,102,241,0.12)" } }}>
                <AddIcon fontSize="small" />
              </IconButton>
            </Tooltip>
          </Box>
          <TextField
            size="small" fullWidth placeholder="Search suites…" value={suiteSearch}
            onChange={(e) => setSuiteSearch(e.target.value)}
            slotProps={{
              input: {
                startAdornment: (
                  <InputAdornment position="start">
                    <SearchIcon sx={{ fontSize: 16, color: "#64748b" }} />
                  </InputAdornment>
                ),
              },
            }}
            sx={{ "& .MuiOutlinedInput-root": { background: "rgba(255,255,255,0.04)", "& fieldset": { borderColor: "rgba(255,255,255,0.08)" } }, input: { color: "#e2e8f0", fontSize: 13 } }}
          />
        </Box>

        {/* Suite list */}
        <Box sx={{ flex: 1, overflowY: "auto" }}>
          {suitesLoading ? (
            [...Array(4)].map((_, i) => (
              <Skeleton key={i} variant="rounded" height={52} sx={{ mx: 1.5, my: 0.5, bgcolor: "rgba(255,255,255,0.05)" }} />
            ))
          ) : filteredSuites.length === 0 ? (
            <Box sx={{ p: 3, textAlign: "center" }}>
              <SuiteIcon sx={{ color: "#334155", fontSize: 32, mb: 1 }} />
              <Typography variant="body2" sx={{ color: "#475569" }}>No suites yet</Typography>
              <Button size="small" onClick={() => setShowCreateSuite(true)} sx={{ mt: 1, color: "#818cf8" }}>
                + Create Suite
              </Button>
            </Box>
          ) : (
            <List dense disablePadding sx={{ pt: 0.5 }}>
              {filteredSuites.map((suite) => (
                <ListItemButton
                  key={suite.id}
                  selected={selectedSuite?.id === suite.id}
                  onClick={() => setSelectedSuite(suite)}
                  sx={{
                    mx: 1, my: 0.25, borderRadius: 1.5, px: 1.5,
                    "&.Mui-selected": { bgcolor: "rgba(99,102,241,0.15)", "&:hover": { bgcolor: "rgba(99,102,241,0.2)" } },
                    "&:hover": { bgcolor: "rgba(255,255,255,0.04)" },
                  }}
                >
                  <Box sx={{ display: "flex", alignItems: "center", gap: 1, flex: 1, minWidth: 0 }}>
                    <SuiteIcon sx={{ fontSize: 16, color: selectedSuite?.id === suite.id ? "#818cf8" : "#475569", flexShrink: 0 }} />
                    <Box sx={{ flex: 1, minWidth: 0 }}>
                      <Typography variant="body2" sx={{ color: "#e2e8f0", fontWeight: selectedSuite?.id === suite.id ? 600 : 400 }} noWrap>
                        {suite.name}
                      </Typography>
                      {suite.status === "ARCHIVED" && (
                        <Box sx={{ display: "flex", alignItems: "center", gap: 0.3 }}>
                          <ArchiveIcon sx={{ fontSize: 11, color: "#64748b" }} />
                          <Typography variant="caption" sx={{ color: "#64748b" }}>Archived</Typography>
                        </Box>
                      )}
                    </Box>
                    <Chip label={suite.case_count} size="small"
                      sx={{ bgcolor: "rgba(255,255,255,0.06)", color: "#94a3b8", fontSize: 10, height: 18, minWidth: 24 }} />
                  </Box>
                </ListItemButton>
              ))}
            </List>
          )}
        </Box>
      </Box>

      {/* Right — cases in suite */}
      <Box sx={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
        {!selectedSuite ? (
          <Box sx={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", flexDirection: "column", gap: 2 }}>
            <CaseIcon sx={{ fontSize: 56, color: "#1e293b" }} />
            <Typography variant="h6" sx={{ color: "#334155" }}>Select a suite to view its test cases</Typography>
          </Box>
        ) : (
          <>
            {/* Suite header */}
            <Box sx={{ p: 2.5, borderBottom: "1px solid rgba(255,255,255,0.06)", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <Box>
                <Typography variant="h6" sx={{ color: "#e2e8f0", fontWeight: 700 }}>{selectedSuite.name}</Typography>
                {selectedSuite.description && (
                  <Typography variant="body2" sx={{ color: "#64748b", mt: 0.3 }}>{selectedSuite.description}</Typography>
                )}
                <Box sx={{ display: "flex", gap: 0.75, mt: 0.5, flexWrap: "wrap" }}>
                  {(selectedSuite.tags ?? []).map((t) => (
                    <Chip key={t} label={t} size="small" sx={{ bgcolor: "rgba(99,102,241,0.1)", color: "#a5b4fc", fontSize: 10, height: 18 }} />
                  ))}
                </Box>
              </Box>
              <Button
                startIcon={<AddIcon />} variant="contained" size="small"
                onClick={() => setShowCreateCase(true)}
                sx={{ background: "linear-gradient(135deg,#6366f1,#8b5cf6)", "&:hover": { background: "linear-gradient(135deg,#818cf8,#a78bfa)" } }}
              >
                New Case
              </Button>
            </Box>

            {/* Case list */}
            <Box sx={{ flex: 1, overflowY: "auto", p: 2 }}>
              {casesLoading ? (
                [...Array(3)].map((_, i) => (
                  <Skeleton key={i} variant="rounded" height={68} sx={{ mb: 1, bgcolor: "rgba(255,255,255,0.05)" }} />
                ))
              ) : cases.length === 0 ? (
                <Box sx={{ textAlign: "center", pt: 6 }}>
                  <CaseIcon sx={{ fontSize: 40, color: "#1e293b", mb: 1 }} />
                  <Typography variant="body2" sx={{ color: "#475569" }}>No test cases in this suite</Typography>
                  <Button size="small" onClick={() => setShowCreateCase(true)} sx={{ mt: 1, color: "#818cf8" }}>
                    + Create Test Case
                  </Button>
                </Box>
              ) : (
                cases.map((tc: TestCaseSummary) => (
                  <Box
                    key={tc.id}
                    onClick={() => navigate(`/test-cases/${tc.id}`)}
                    sx={{
                      mb: 1, p: 2, borderRadius: 2, cursor: "pointer",
                      border: "1px solid rgba(255,255,255,0.06)",
                      bgcolor: "rgba(255,255,255,0.02)",
                      "&:hover": { bgcolor: "rgba(99,102,241,0.08)", borderColor: "rgba(99,102,241,0.3)" },
                      transition: "all 0.15s",
                    }}
                  >
                    <Box sx={{ display: "flex", alignItems: "flex-start", gap: 1.5 }}>
                      <Box sx={{ flex: 1 }}>
                        <Box sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap" }}>
                          <Typography variant="body2" sx={{ color: "#e2e8f0", fontWeight: 600 }}>
                            {tc.name}
                          </Typography>
                          <Chip label={`v${tc.version}`} size="small"
                            sx={{ bgcolor: "rgba(255,255,255,0.06)", color: "#64748b", fontSize: 10, height: 16 }} />
                        </Box>
                        <Box sx={{ display: "flex", gap: 0.75, mt: 0.5, flexWrap: "wrap" }}>
                          <Chip label={tc.status} size="small"
                            sx={{ bgcolor: `${STATUS_COLORS[tc.status]}22`, color: STATUS_COLORS[tc.status], fontSize: 10, height: 18 }} />
                          <Chip label={tc.priority} size="small"
                            sx={{ bgcolor: `${PRIORITY_COLORS[tc.priority]}22`, color: PRIORITY_COLORS[tc.priority], fontSize: 10, height: 18 }} />
                          {(tc.tags ?? []).map((tag) => (
                            <Chip key={tag} label={tag} size="small"
                              sx={{ bgcolor: "rgba(99,102,241,0.1)", color: "#a5b4fc", fontSize: 10, height: 18 }} />
                          ))}
                        </Box>
                      </Box>
                      {tc.estimated_duration_secs && (
                        <Typography variant="caption" sx={{ color: "#475569" }}>
                          ~{Math.ceil(tc.estimated_duration_secs / 60)}m
                        </Typography>
                      )}
                    </Box>
                  </Box>
                ))
              )}
            </Box>
          </>
        )}
      </Box>

      <CreateSuiteDialog open={showCreateSuite} onClose={() => setShowCreateSuite(false)} />
      {selectedSuite && (
        <CreateCaseDialog
          suiteId={selectedSuite.id}
          open={showCreateCase}
          onClose={() => setShowCreateCase(false)}
        />
      )}
    </Box>
  );
}
