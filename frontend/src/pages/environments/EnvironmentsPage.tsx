import { useState, useEffect, useCallback } from "react";
import {
  Box, Typography, Button, Chip, IconButton, Tooltip,
  Dialog, DialogTitle, DialogContent, DialogActions,
  TextField, Stack, Alert, CircularProgress,
  Table, TableBody, TableCell, TableHead, TableRow,
  TableContainer, Paper, Switch, FormControlLabel, Select,
  MenuItem, FormControl, InputLabel,
} from "@mui/material";
import { Add, Delete, ExpandMore, ExpandLess, Lock, LockOpen } from "@mui/icons-material";
import {
  listEnvironments, getEnvironment, createEnvironment, updateEnvironment,
  deleteEnvironment, listVariables, createVariable, deleteVariable,
  type Environment, type EnvironmentVariable,
} from "../../lib/api/environments";

const TF_SX = {
  "& .MuiOutlinedInput-root": {
    bgcolor: "rgba(255,255,255,0.04)",
    "& fieldset": { borderColor: "rgba(255,255,255,0.12)" },
    color: "#e0e0ff",
  },
  "& .MuiInputLabel-root": { color: "#aaa" },
};

// ── Add Variable Dialog ───────────────────────────────────────────────────────
function AddVarDialog({ envId, open, onClose, onCreated }: {
  envId: string; open: boolean; onClose: () => void; onCreated: () => void;
}) {
  const [key, setKey] = useState("");
  const [value, setValue] = useState("");
  const [type, setType] = useState("STRING");
  const [isSecret, setIsSecret] = useState(false);
  const [desc, setDesc] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const reset = () => { setKey(""); setValue(""); setType("STRING"); setIsSecret(false); setDesc(""); setError(""); };

  const handleSubmit = async () => {
    if (!key.trim() || !value.trim()) { setError("Key and value are required"); return; }
    setLoading(true);
    try {
      await createVariable(envId, { key: key.trim(), value, type, is_secret: isSecret, description: desc || undefined });
      reset(); onCreated(); onClose();
    } catch (e: any) {
      setError(e?.message ?? "Failed to create variable");
    } finally { setLoading(false); }
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth
      slotProps={{ paper: { sx: { bgcolor: "#13132a", color: "#fff" } } }}>
      <DialogTitle>Add Variable</DialogTitle>
      <DialogContent>
        <Box sx={{ display: "flex", flexDirection: "column", gap: 2, mt: 1 }}>
          {error && <Alert severity="error">{error}</Alert>}
          <TextField label="Key" value={key} onChange={(e) => setKey(e.target.value)} fullWidth size="small" sx={TF_SX} />
          <TextField label={isSecret ? "Value (will be encrypted)" : "Value"} value={value}
            onChange={(e) => setValue(e.target.value)} fullWidth size="small"
            type={isSecret ? "password" : "text"} sx={TF_SX} />
          <FormControl size="small" fullWidth>
            <InputLabel sx={{ color: "#aaa" }}>Type</InputLabel>
            <Select value={type} onChange={(e) => setType(e.target.value)} label="Type"
              sx={{ color: "#e0e0ff", bgcolor: "rgba(255,255,255,0.04)" }}>
              {["STRING", "NUMBER", "BOOLEAN", "JSON"].map((t) => <MenuItem key={t} value={t}>{t}</MenuItem>)}
            </Select>
          </FormControl>
          <FormControlLabel
            control={<Switch checked={isSecret} onChange={(e) => setIsSecret(e.target.checked)} />}
            label="Secret (encrypted at rest)" />
          <TextField label="Description (optional)" value={desc} onChange={(e) => setDesc(e.target.value)} fullWidth size="small" sx={TF_SX} />
        </Box>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} sx={{ color: "#aaa" }}>Cancel</Button>
        <Button onClick={handleSubmit} disabled={loading} variant="contained"
          sx={{ background: "linear-gradient(135deg,#6c63ff,#48cae4)" }}>
          {loading ? <CircularProgress size={18} /> : "Add"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

// ── Create Environment Dialog ─────────────────────────────────────────────────
function CreateEnvDialog({ open, onClose, onCreated }: { open: boolean; onClose: () => void; onCreated: () => void }) {
  const [name, setName] = useState("");
  const [desc, setDesc] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [tags, setTags] = useState("");
  const [isDefault, setIsDefault] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async () => {
    if (!name.trim()) { setError("Name is required"); return; }
    setLoading(true);
    try {
      await createEnvironment({
        name: name.trim(),
        description: desc || undefined,
        base_url: baseUrl || undefined,
        tags: tags ? tags.split(",").map((t) => t.trim()).filter(Boolean) : undefined,
        is_default: isDefault,
      });
      setName(""); setDesc(""); setBaseUrl(""); setTags(""); setIsDefault(false); setError("");
      onCreated(); onClose();
    } catch (e: any) {
      setError(e?.message ?? "Failed to create environment");
    } finally { setLoading(false); }
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth
      slotProps={{ paper: { sx: { bgcolor: "#13132a", color: "#fff" } } }}>
      <DialogTitle>New Environment</DialogTitle>
      <DialogContent>
        <Box sx={{ display: "flex", flexDirection: "column", gap: 2, mt: 1 }}>
          {error && <Alert severity="error">{error}</Alert>}
          <TextField label="Name" value={name} onChange={(e) => setName(e.target.value)} fullWidth size="small" sx={TF_SX} />
          <TextField label="Description" value={desc} onChange={(e) => setDesc(e.target.value)} fullWidth size="small" sx={TF_SX} />
          <TextField label="Base URL" value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} fullWidth size="small" sx={TF_SX} />
          <TextField label="Tags (comma-separated)" value={tags} onChange={(e) => setTags(e.target.value)} fullWidth size="small" sx={TF_SX} />
          <FormControlLabel
            control={<Switch checked={isDefault} onChange={(e) => setIsDefault(e.target.checked)} />}
            label="Set as default environment" />
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

// ── Variables Panel ───────────────────────────────────────────────────────────
function EnvVariablesPanel({ env }: { env: Environment }) {
  const [vars, setVars] = useState<EnvironmentVariable[]>([]);
  const [loading, setLoading] = useState(true);
  const [addOpen, setAddOpen] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try { setVars(await listVariables(env.id)); }
    finally { setLoading(false); }
  }, [env.id]);

  useEffect(() => { load(); }, [load]);

  return (
    <Box sx={{ px: 3, py: 2, bgcolor: "#0a0a1e" }}>
      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 1 }}>
        <Typography variant="caption" sx={{ color: "#8b8bff", textTransform: "uppercase", letterSpacing: 1 }}>
          Variables ({vars.length})
        </Typography>
        <Button size="small" startIcon={<Add />} onClick={() => setAddOpen(true)}
          sx={{ background: "linear-gradient(135deg,#6c63ff,#48cae4)", color: "#fff", borderRadius: 2 }}>
          Add Variable
        </Button>
      </Box>
      {loading ? <CircularProgress size={20} /> : (
        <Table size="small">
          <TableHead>
            <TableRow>
              {["Key", "Type", "Secret", ""].map((h) => (
                <TableCell key={h} sx={{ color: "#666", borderBottom: "1px solid #1e1e3a" }}>{h}</TableCell>
              ))}
            </TableRow>
          </TableHead>
          <TableBody>
            {vars.length === 0 ? (
              <TableRow><TableCell colSpan={4} sx={{ color: "#666", textAlign: "center" }}>No variables yet</TableCell></TableRow>
            ) : vars.map((v) => (
              <TableRow key={v.id}>
                <TableCell sx={{ color: "#e0e0ff", fontFamily: "monospace" }}>{v.key}</TableCell>
                <TableCell>
                  <Chip label={v.type} size="small" variant="outlined" sx={{ borderColor: "#6c63ff", color: "#8b8bff" }} />
                </TableCell>
                <TableCell>
                  {v.is_secret
                    ? <Lock fontSize="small" sx={{ color: "#ff6b6b" }} />
                    : <LockOpen fontSize="small" sx={{ color: "#4ecdc4" }} />}
                </TableCell>
                <TableCell>
                  <Tooltip title="Delete variable">
                    <IconButton size="small" onClick={() => deleteVariable(env.id, v.id).then(load)} sx={{ color: "#ff6b6b" }}>
                      <Delete fontSize="small" />
                    </IconButton>
                  </Tooltip>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
      <AddVarDialog envId={env.id} open={addOpen} onClose={() => setAddOpen(false)} onCreated={load} />
    </Box>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────
export default function EnvironmentsPage() {
  const [envs, setEnvs] = useState<Environment[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [createOpen, setCreateOpen] = useState(false);
  const [expanded, setExpanded] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const data = await listEnvironments();
      setEnvs(data.items); setTotal(data.total);
    } catch (e: any) {
      setError(e?.message ?? "Failed to load environments");
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  return (
    <Box sx={{ p: 3, color: "#e0e0ff", minHeight: "100vh" }}>
      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 3 }}>
        <Box>
          <Typography variant="h5" sx={{ fontWeight: 700, color: "#fff" }}>Environments</Typography>
          <Typography variant="body2" sx={{ color: "#666" }}>
            {total} environment{total !== 1 ? "s" : ""} · Click a row to expand variables
          </Typography>
        </Box>
        <Button variant="contained" startIcon={<Add />} onClick={() => setCreateOpen(true)}
          sx={{ background: "linear-gradient(135deg,#6c63ff,#48cae4)", borderRadius: 2, fontWeight: 600 }}>
          New Environment
        </Button>
      </Box>

      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

      {loading ? (
        <Box sx={{ display: "flex", justifyContent: "center", mt: 6 }}><CircularProgress /></Box>
      ) : (
        <TableContainer component={Paper}
          sx={{ bgcolor: "#13132a", borderRadius: 3, boxShadow: "0 4px 32px rgba(108,99,255,.15)" }}>
          <Table>
            <TableHead>
              <TableRow>
                {["", "Name", "Base URL", "Tags", "Version", "Default", "Actions"].map((h) => (
                  <TableCell key={h} sx={{ color: "#8b8bff", borderBottom: "1px solid #1e1e3a", fontWeight: 600 }}>{h}</TableCell>
                ))}
              </TableRow>
            </TableHead>
            <TableBody>
              {envs.length === 0 && (
                <TableRow>
                  <TableCell colSpan={7} sx={{ textAlign: "center", color: "#666", py: 6 }}>
                    No environments yet. Create one to get started.
                  </TableCell>
                </TableRow>
              )}
              {envs.map((env) => (
                <>
                  <TableRow key={env.id} hover
                    sx={{ cursor: "pointer", "&:hover": { bgcolor: "#1e1e3a" } }}
                    onClick={() => setExpanded(expanded === env.id ? null : env.id)}>
                    <TableCell sx={{ color: "#666", border: "none" }}>
                      {expanded === env.id ? <ExpandLess /> : <ExpandMore />}
                    </TableCell>
                    <TableCell sx={{ color: "#e0e0ff", fontWeight: 600, borderBottom: "1px solid #1e1e3a" }}>
                      {env.name}
                      {env.description && (
                        <Typography variant="caption" sx={{ display: "block", color: "#666" }}>{env.description}</Typography>
                      )}
                    </TableCell>
                    <TableCell sx={{ color: "#8b8bff", fontFamily: "monospace", fontSize: 12, borderBottom: "1px solid #1e1e3a" }}>
                      {env.base_url ?? "—"}
                    </TableCell>
                    <TableCell sx={{ borderBottom: "1px solid #1e1e3a" }}>
                      <Box sx={{ display: "flex", gap: 0.5, flexWrap: "wrap" }}>
                        {env.tags.map((t) => <Chip key={t} label={t} size="small" sx={{ bgcolor: "#1e1e3a", color: "#8b8bff" }} />)}
                      </Box>
                    </TableCell>
                    <TableCell sx={{ borderBottom: "1px solid #1e1e3a" }}>
                      <Chip label={`v${env.version}`} size="small"
                        sx={{ fontFamily: "monospace", bgcolor: "#1e1e3a", color: "#8b8bff" }} />
                    </TableCell>
                    <TableCell sx={{ borderBottom: "1px solid #1e1e3a" }}>
                      {env.is_default && <Chip label="DEFAULT" size="small" color="primary" />}
                    </TableCell>
                    <TableCell sx={{ borderBottom: "1px solid #1e1e3a" }} onClick={(e) => e.stopPropagation()}>
                      <Tooltip title="Delete">
                        <IconButton size="small"
                          onClick={() => { if (confirm("Delete this environment?")) deleteEnvironment(env.id).then(load); }}
                          sx={{ color: "#ff6b6b" }}>
                          <Delete fontSize="small" />
                        </IconButton>
                      </Tooltip>
                    </TableCell>
                  </TableRow>
                  {expanded === env.id && (
                    <TableRow key={`${env.id}-vars`}>
                      <TableCell colSpan={7} sx={{ p: 0, borderBottom: "2px solid #6c63ff" }}>
                        <EnvVariablesPanel env={env} />
                      </TableCell>
                    </TableRow>
                  )}
                </>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      )}

      <CreateEnvDialog open={createOpen} onClose={() => setCreateOpen(false)} onCreated={load} />
    </Box>
  );
}
