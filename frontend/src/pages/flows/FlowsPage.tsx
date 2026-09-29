import { useSearchParams } from "react-router-dom";
import { useState, useEffect, useCallback } from "react";
import {
  Box, Typography, Button, Chip, IconButton, Tooltip,
  Dialog, DialogTitle, DialogContent, DialogActions,
  TextField, Alert, CircularProgress,
  Table, TableBody, TableCell, TableHead, TableRow,
  TableContainer, Paper, Tabs, Tab,
  InputAdornment, MenuItem,
} from "@mui/material";
import { Add, Delete, ContentCopy, Search, DragIndicator } from "@mui/icons-material";
import {
  listFlows, getFlow, createFlow, deleteFlow, duplicateFlow,
  createFlowStep, deleteFlowStep,
  type Flow, type FlowStep,
} from "../../lib/api/flows";

const TF_SX = {
  "& .MuiOutlinedInput-root": {
    bgcolor: "rgba(255,255,255,0.04)",
    "& fieldset": { borderColor: "rgba(255,255,255,0.12)" },
    color: "#e0e0ff",
  },
  "& .MuiInputLabel-root": { color: "#aaa" },
};

// ── Checksum badge ─────────────────────────────────────────────────────────────
const ChecksumBadge = ({ checksum }: { checksum: string }) =>
  checksum ? (
    <Tooltip title={`SHA-256: ${checksum}`}>
      <Chip label={`#${checksum.slice(0, 8)}`} size="small"
        sx={{ fontFamily: "monospace", bgcolor: "#1e1e3a", color: "#4ecdc4", fontSize: 11 }} />
    </Tooltip>
  ) : (
    <Chip label="empty" size="small" sx={{ bgcolor: "#1e1e3a", color: "#666" }} />
  );

// ── Action colors ──────────────────────────────────────────────────────────────
const ACTION_COLORS: Record<string, string> = {
  NAVIGATE: "#6c63ff", CLICK: "#4ecdc4", TYPE: "#ffbe76",
  WAIT_FOR: "#a29bfe", SCREENSHOT: "#fd79a8", EXECUTE_SCRIPT: "#fdcb6e",
};

// ── Step Row ───────────────────────────────────────────────────────────────────
function StepRow({ step, onDelete }: { step: FlowStep; onDelete: () => void }) {
  const color = ACTION_COLORS[step.action] ?? "#8b8bff";
  return (
    <TableRow sx={{ "&:hover": { bgcolor: "#1a1a30" } }}>
      <TableCell sx={{ color: "#555", width: 40, borderBottom: "1px solid #1e1e3a" }}>
        <DragIndicator fontSize="small" />
      </TableCell>
      <TableCell sx={{ color: "#666", width: 40, borderBottom: "1px solid #1e1e3a" }}>{step.position}</TableCell>
      <TableCell sx={{ borderBottom: "1px solid #1e1e3a" }}>
        <Chip label={step.action} size="small"
          sx={{ bgcolor: `${color}22`, color, border: `1px solid ${color}` }} />
      </TableCell>
      <TableCell sx={{ color: "#8b8bff", fontFamily: "monospace", fontSize: 12, borderBottom: "1px solid #1e1e3a" }}>
        {step.target_url ?? step.input_value ?? "—"}
      </TableCell>
      <TableCell sx={{ color: "#555", fontSize: 11, borderBottom: "1px solid #1e1e3a" }}>
        {step.timeout_ms}ms
      </TableCell>
      <TableCell sx={{ borderBottom: "1px solid #1e1e3a" }}>
        <Tooltip title="Delete step">
          <IconButton size="small" onClick={onDelete} sx={{ color: "#ff6b6b" }}>
            <Delete fontSize="small" />
          </IconButton>
        </Tooltip>
      </TableCell>
    </TableRow>
  );
}

// ── Flow Detail Dialog ─────────────────────────────────────────────────────────
const ACTIONS = [
  "CLICK", "DOUBLE_CLICK", "RIGHT_CLICK", "TYPE", "NAVIGATE",
  "WAIT_FOR", "SCREENSHOT", "EXECUTE_SCRIPT", "SELECT", "HOVER",
  "SCROLL_TO", "PRESS_KEY",
];

function FlowDetailDialog({ flow, open, onClose, onUpdated }: {
  flow: Flow; open: boolean; onClose: () => void; onUpdated: () => void;
}) {
  const [steps, setSteps] = useState<FlowStep[]>([]);
  const [loading, setLoading] = useState(true);
  const [action, setAction] = useState("CLICK");
  const [targetUrl, setTargetUrl] = useState("");
  const [inputValue, setInputValue] = useState("");
  const [addError, setAddError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const detail = await getFlow(flow.id);
      setSteps(detail.steps ?? []);
    } finally { setLoading(false); }
  }, [flow.id]);

  useEffect(() => { if (open) load(); }, [open, load]);

  const handleAddStep = async () => {
    if (!action) return;
    setAddError("");
    try {
      await createFlowStep(flow.id, {
        action,
        target_url: targetUrl || undefined,
        input_value: inputValue || undefined,
      });
      setTargetUrl(""); setInputValue("");
      await load(); onUpdated();
    } catch (e: any) { setAddError(e?.message ?? "Failed to add step"); }
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth
      slotProps={{ paper: { sx: { bgcolor: "#13132a", color: "#fff", minHeight: 500 } } }}>
      <DialogTitle sx={{ borderBottom: "1px solid #1e1e3a", pb: 2 }}>
        <Box sx={{ display: "flex", alignItems: "center", gap: 2 }}>
          <Typography sx={{ fontWeight: 700, fontSize: 18 }}>{flow.name}</Typography>
          <Chip label={`v${flow.version}`} size="small" sx={{ bgcolor: "#1e1e3a", color: "#8b8bff" }} />
          <ChecksumBadge checksum={flow.checksum} />
        </Box>
        {flow.description && <Typography variant="body2" sx={{ color: "#666", mt: 0.5 }}>{flow.description}</Typography>}
      </DialogTitle>
      <DialogContent sx={{ pt: 2 }}>
        {/* Add step */}
        <Box sx={{ display: "flex", gap: 1, mb: 2, flexWrap: "wrap" }}>
          <TextField
            select size="small" label="Action" value={action}
            onChange={(e) => setAction(e.target.value)}
            sx={{ minWidth: 160, ...TF_SX }}
            slotProps={{ select: { native: true } }}>
            {ACTIONS.map((a) => <option key={a} value={a}>{a}</option>)}
          </TextField>
          <TextField label="Target URL" value={targetUrl} onChange={(e) => setTargetUrl(e.target.value)}
            size="small" sx={{ flex: 1, ...TF_SX }} />
          <TextField label="Input Value" value={inputValue} onChange={(e) => setInputValue(e.target.value)}
            size="small" sx={{ flex: 1, ...TF_SX }} />
          <Button onClick={handleAddStep} variant="contained" size="small"
            sx={{ background: "linear-gradient(135deg,#6c63ff,#48cae4)", alignSelf: "stretch" }}>
            <Add />
          </Button>
        </Box>
        {addError && <Alert severity="error" sx={{ mb: 1 }}>{addError}</Alert>}

        {loading ? <CircularProgress size={24} /> : (
          <TableContainer>
            <Table size="small">
              <TableHead>
                <TableRow>
                  {["", "#", "Action", "Value / URL", "Config", ""].map((h) => (
                    <TableCell key={h} sx={{ color: "#666", borderBottom: "1px solid #1e1e3a", fontSize: 11 }}>{h}</TableCell>
                  ))}
                </TableRow>
              </TableHead>
              <TableBody>
                {steps.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={6} sx={{ textAlign: "center", color: "#555", py: 4 }}>
                      No steps yet. Add the first step above.
                    </TableCell>
                  </TableRow>
                ) : steps.map((s) => (
                  <StepRow key={s.id} step={s}
                    onDelete={() => deleteFlowStep(s.id).then(load).then(onUpdated)} />
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        )}
      </DialogContent>
      <DialogActions sx={{ borderTop: "1px solid #1e1e3a" }}>
        <Button onClick={onClose} sx={{ color: "#aaa" }}>Close</Button>
      </DialogActions>
    </Dialog>
  );
}

// ── Create Flow Dialog ─────────────────────────────────────────────────────────
function CreateFlowDialog({ open, onClose, onCreated }: { open: boolean; onClose: () => void; onCreated: () => void }) {
  const [name, setName] = useState("");
  const [kind, setKind] = useState<"FLOW" | "BUSINESS_ACTION">("FLOW");
  const [desc, setDesc] = useState("");
  const [tags, setTags] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async () => {
    if (!name.trim()) { setError("Name is required"); return; }
    setLoading(true);
    try {
      await createFlow({
        name: name.trim(), kind,
        description: desc || undefined,
        tags: tags ? tags.split(",").map((t) => t.trim()).filter(Boolean) : undefined,
      });
      setName(""); setDesc(""); setTags(""); setError("");
      onCreated(); onClose();
    } catch (e: any) {
      setError(e?.message ?? "Failed to create flow");
    } finally { setLoading(false); }
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth
      slotProps={{ paper: { sx: { bgcolor: "#13132a", color: "#fff" } } }}>
      <DialogTitle>New reusable asset</DialogTitle>
      <DialogContent>
        <Box sx={{ display: "flex", flexDirection: "column", gap: 2, mt: 1 }}>
          {error && <Alert severity="error">{error}</Alert>}
          <TextField select label="Asset type" value={kind} onChange={e => setKind(e.target.value as typeof kind)} sx={TF_SX}>
            <MenuItem value="FLOW">Flow</MenuItem><MenuItem value="BUSINESS_ACTION">Business action</MenuItem>
          </TextField>
          <TextField label="Name" value={name} onChange={(e) => setName(e.target.value)} fullWidth size="small" sx={TF_SX} />
          <TextField label="Description" value={desc} onChange={(e) => setDesc(e.target.value)} fullWidth size="small" sx={TF_SX} />
          <TextField label="Tags (comma-separated)" value={tags} onChange={(e) => setTags(e.target.value)} fullWidth size="small" sx={TF_SX} />
        </Box>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} sx={{ color: "#aaa" }}>Cancel</Button>
        <Button onClick={handleSubmit} disabled={loading} variant="contained"
          sx={{ background: "linear-gradient(135deg,#6c63ff,#48cae4)" }}>
          {loading ? <CircularProgress size={18} /> : "Create"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────
export default function FlowsPage() {
  const [params] = useSearchParams();
  const requestedFlow = params.get('flow');
  const [flows, setFlows] = useState<Flow[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [error, setError] = useState("");
  const [createOpen, setCreateOpen] = useState(false);
  const [selected, setSelected] = useState<Flow | null>(null);

  const load = useCallback(async (q?: string) => {
    setLoading(true); setError("");
    try {
      const data = await listFlows({ search: q });
      setFlows(data.items); setTotal(data.total);
    } catch (e: any) {
      setError(e?.message ?? "Failed to load flows");
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    if (!requestedFlow) return;
    let active = true;
    getFlow(requestedFlow).then(flow => { if (active) setSelected(flow); })
      .catch(() => { if (active) setError('Could not open the promoted flow.'); });
    return () => { active = false; };
  }, [requestedFlow]);

  const handleSearch = (v: string) => { setSearch(v); load(v); };

  return (
    <Box sx={{ p: 3, color: "#e0e0ff", minHeight: "100vh" }}>
      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 3 }}>
        <Box>
          <Typography variant="h5" sx={{ fontWeight: 700, color: "#fff" }}>Business Actions & Flows</Typography>
          <Typography variant="body2" sx={{ color: "#666" }}>
            {total} flow{total !== 1 ? "s" : ""} · Version-pinned & checksum-verified
          </Typography>
        </Box>
        <Button variant="contained" startIcon={<Add />} onClick={() => setCreateOpen(true)}
          sx={{ background: "linear-gradient(135deg,#6c63ff,#48cae4)", borderRadius: 2, fontWeight: 600 }}>
          New Flow
        </Button>
      </Box>

      <TextField
        size="small" placeholder="Search flows…" value={search}
        onChange={(e) => handleSearch(e.target.value)}
        sx={{ mb: 2, width: 320, ...TF_SX }}
        slotProps={{
          input: {
            startAdornment: (
              <InputAdornment position="start"><Search sx={{ color: "#666" }} /></InputAdornment>
            ),
          },
        }}
      />

      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

      {loading ? (
        <Box sx={{ display: "flex", justifyContent: "center", mt: 6 }}><CircularProgress /></Box>
      ) : (
        <TableContainer component={Paper}
          sx={{ bgcolor: "#13132a", borderRadius: 3, boxShadow: "0 4px 32px rgba(108,99,255,.15)" }}>
          <Table>
            <TableHead>
              <TableRow>
                {["Name", "Tags", "Version", "Checksum", ""].map((h) => (
                  <TableCell key={h} sx={{ color: "#8b8bff", borderBottom: "1px solid #1e1e3a", fontWeight: 600 }}>{h}</TableCell>
                ))}
              </TableRow>
            </TableHead>
            <TableBody>
              {flows.length === 0 && (
                <TableRow>
                  <TableCell colSpan={5} sx={{ textAlign: "center", color: "#666", py: 6 }}>
                    No flows yet. Create one to get started.
                  </TableCell>
                </TableRow>
              )}
              {flows.map((f) => (
                <TableRow key={f.id} hover
                  sx={{ cursor: "pointer", "&:hover": { bgcolor: "#1e1e3a" } }}
                  onClick={() => setSelected(f)}>
                  <TableCell sx={{ color: "#e0e0ff", fontWeight: 600, borderBottom: "1px solid #1e1e3a" }}>
                    {f.name} <Chip size="small" label={f.kind === "BUSINESS_ACTION" ? "Business action" : "Flow"} />
                    {f.description && (
                      <Typography variant="caption" sx={{ display: "block", color: "#666" }}>{f.description}</Typography>
                    )}
                    {f.created_from_flow_id && (
                      <Chip label="clone" size="small" sx={{ bgcolor: "#1e1e3a", color: "#48cae4", ml: 1 }} />
                    )}
                  </TableCell>
                  <TableCell sx={{ borderBottom: "1px solid #1e1e3a" }}>
                    <Box sx={{ display: "flex", gap: 0.5, flexWrap: "wrap" }}>
                      {f.tags.map((t) => <Chip key={t} label={t} size="small" sx={{ bgcolor: "#1e1e3a", color: "#8b8bff" }} />)}
                    </Box>
                  </TableCell>
                  <TableCell sx={{ borderBottom: "1px solid #1e1e3a" }}>
                    <Chip label={`v${f.version}`} size="small"
                      sx={{ fontFamily: "monospace", bgcolor: "#1e1e3a", color: "#8b8bff" }} />
                  </TableCell>
                  <TableCell sx={{ borderBottom: "1px solid #1e1e3a" }}>
                    <ChecksumBadge checksum={f.checksum} />
                  </TableCell>
                  <TableCell sx={{ borderBottom: "1px solid #1e1e3a" }} onClick={(e) => e.stopPropagation()}>
                    <Box sx={{ display: "flex" }}>
                      <Tooltip title="Duplicate">
                        <IconButton size="small" sx={{ color: "#48cae4" }}
                          onClick={() => duplicateFlow(f.id, `${f.name} (copy)`).then(() => load(search))}>
                          <ContentCopy fontSize="small" />
                        </IconButton>
                      </Tooltip>
                      <Tooltip title="Delete">
                        <IconButton size="small" sx={{ color: "#ff6b6b" }}
                          onClick={() => { if (confirm("Delete flow?")) deleteFlow(f.id).then(() => load(search)); }}>
                          <Delete fontSize="small" />
                        </IconButton>
                      </Tooltip>
                    </Box>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      )}

      <CreateFlowDialog open={createOpen} onClose={() => setCreateOpen(false)} onCreated={() => load(search)} />
      {selected && (
        <FlowDetailDialog flow={selected} open={!!selected}
          onClose={() => setSelected(null)}
          onUpdated={() => load(search)} />
      )}
    </Box>
  );
}
