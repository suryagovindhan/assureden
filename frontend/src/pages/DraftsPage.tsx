import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { Alert, Box, Button, MenuItem, Paper, Stack, TextField, Typography } from "@mui/material";
import api from "../lib/api";
import BrowserRecorder from "../components/BrowserRecorder";

type Locator = { type: string; value: string; priority: number; is_primary: boolean; is_active: boolean; added_by: string };
type Step = { action: string; input_value: string; is_secret: boolean; locators: Locator[] };
type Recording = { schema_version: number; name: string; steps: Step[]; warnings?: string[] };
type Draft = { id: string; name: string; version: number; status: string; recording: Recording; promoted_case_id: string | null; promoted_flow_id: string | null };
type Choice = { id: string; name: string };

export default function DraftsPage() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [draft, setDraft] = useState<Draft | null>(null);
  const [appId, setAppId] = useState("");
  const [moduleId, setModuleId] = useState("");
  const [pageId, setPageId] = useState("");
  const [target, setTarget] = useState("TEST_CASE");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const { data: drafts = [] } = useQuery({ queryKey: ["drafts"], queryFn: async () => (await api.get<Draft[]>("/drafts")).data });
  const { data: apps = [], isError: appsError } = useQuery({ queryKey: ["draft-apps"], queryFn: async () => (await api.get<{ items: Choice[] }>("/object-repository/applications?limit=200")).data.items });
  const { data: modules = [] } = useQuery({ queryKey: ["draft-modules", appId], enabled: !!appId,
    queryFn: async () => (await api.get<{ items: Choice[] }>(`/object-repository/applications/${appId}/modules?limit=200`)).data.items });
  const { data: pages = [] } = useQuery({ queryKey: ["draft-pages", moduleId], enabled: !!moduleId,
    queryFn: async () => (await api.get<{ items: Choice[] }>(`/object-repository/modules/${moduleId}/pages?limit=200`)).data.items });
  const perform = async (task: () => Promise<void>) => {
    setBusy(true); setError("");
    try { await task(); await qc.invalidateQueries({ queryKey: ["drafts"] }); }
    catch { setError("Could not save this recording. Check its fields, permissions and version; reload the draft if another user changed it."); }
    finally { setBusy(false); }
  };
  const changeStep = (index: number, patch: Partial<Step>) => {
    if (draft) setDraft({ ...draft, recording: { ...draft.recording, steps: draft.recording.steps.map((s, i) => i === index ? { ...s, ...patch } : s) } });
  };
  const save = async () => {
    if (!draft) throw new Error("Choose a draft");
    const saved = (await api.put<Draft>(`/drafts/${draft.id}`, { ...draft.recording, expected_version: draft.version })).data;
    setDraft(saved); return saved;
  };
  const locked = !draft || draft.status !== "DRAFT" || busy;
  return <Stack spacing={2}>
    <Typography variant="h5">Record a test</Typography>
    <Typography color="text.secondary">Connect your agent → record actions → review the draft → add assertions and run.</Typography>
    <BrowserRecorder onReview={id => void perform(async () => {
      const response = await api.get<Draft[]>('/drafts');
      setDraft(response.data.find(d => d.id === id) ?? null);
    })} />
    <Typography>Review a browser recording below, or import an existing file. Add assertions in the test editor before running it.</Typography>
    {error && <Alert severity="error">{error}</Alert>}
    {appsError && <Alert severity="error">Could not load destination applications. Check your connection.</Alert>}
    <Button component="label" disabled={busy} variant="outlined">Import recording
      <input hidden type="file" accept=".json" onChange={event => {
        const file = event.target.files?.[0]; event.target.value = "";
        if (file) void perform(async () => {
          if (file.size > 2_000_000) throw new Error("Too large");
          setDraft((await api.post<Draft>("/drafts", JSON.parse(await file.text()))).data);
        });
      }} />
    </Button>
    <TextField select label="Choose a draft" value={draft?.id ?? ""} disabled={busy} onChange={e => setDraft(structuredClone(drafts.find(d => d.id === e.target.value) ?? null))}>
      {drafts.map(d => <MenuItem key={d.id} value={d.id}>{d.name} — {d.status}</MenuItem>)}
    </TextField>
    {draft && <>
      {draft.recording.warnings?.map((warning, i) => <Alert key={i} severity="warning">{warning}</Alert>)}
      <TextField label="Test case name" value={draft.recording.name} disabled={locked}
        onChange={e => setDraft({ ...draft, recording: { ...draft.recording, name: e.target.value } })} />
      {draft.recording.steps.map((step, index) => <Paper key={index} sx={{ p: 2 }}>
        <Stack spacing={1}>
          <Typography>Step {index + 1}: {step.action}</Typography>
          <TextField label={step.is_secret ? "Secret variable placeholder" : "Value or URL"} value={step.input_value}
            disabled={locked} onChange={e => changeStep(index, { input_value: e.target.value })} />
          {step.locators.map((locator, locatorIndex) => <TextField key={locatorIndex}
            label={`${locator.type}${locator.is_primary ? " (primary)" : " (fallback)"}`}
            value={locator.value} disabled={locked} onChange={e => changeStep(index, {
              locators: step.locators.map((l, i) => i === locatorIndex ? { ...l, value: e.target.value } : l),
            })} />)}
          <Button disabled={locked || draft.recording.steps.length < 2} onClick={() => setDraft({ ...draft,
            recording: { ...draft.recording, steps: draft.recording.steps.filter((_, i) => i !== index) } })}>Remove step</Button>
        </Stack>
      </Paper>)}
      {draft.status === "DRAFT" ? <>
        <Button disabled={busy} onClick={() => void perform(async () => { await save(); })}>Save review</Button>
        <Typography>Store recorded objects under an existing repository page:</Typography>
        <Box sx={{ display: "flex", gap: 2 }}>
          <TextField select fullWidth label="Application" value={appId} onChange={e => { setAppId(e.target.value); setModuleId(""); setPageId(""); }}>
            {apps.map(a => <MenuItem key={a.id} value={a.id}>{a.name}</MenuItem>)}
          </TextField>
          <TextField select fullWidth label="Module" value={moduleId} onChange={e => { setModuleId(e.target.value); setPageId(""); }}>
            {modules.map(m => <MenuItem key={m.id} value={m.id}>{m.name}</MenuItem>)}
          </TextField>
          <TextField select fullWidth label="Page" value={pageId} onChange={e => setPageId(e.target.value)}>
            {pages.map(p => <MenuItem key={p.id} value={p.id}>{p.name}</MenuItem>)}
          </TextField>
        </Box>
        <TextField select label="Create as" value={target} onChange={e => setTarget(e.target.value)} disabled={busy}>
          <MenuItem value="TEST_CASE">Test case</MenuItem><MenuItem value="FLOW">Reusable flow</MenuItem><MenuItem value="BUSINESS_ACTION">Business action</MenuItem>
        </TextField>
        <Button variant="contained" disabled={busy || !pageId} onClick={() => void perform(async () => {
          const saved = await save();
          const result = (await api.post<{ test_case_id?: string; flow_id?: string }>(`/drafts/${saved.id}/promote`, { expected_version: saved.version, page_id: pageId, target })).data;
          navigate(result.flow_id ? `/flows?flow=${result.flow_id}` : `/test-cases/${result.test_case_id}`);
        })}>Create {target === "BUSINESS_ACTION" ? "business action" : target === "FLOW" ? "flow" : "test case"} from reviewed draft</Button>
      </> : <Button onClick={() => navigate(draft.promoted_flow_id ? `/flows?flow=${draft.promoted_flow_id}` : `/test-cases/${draft.promoted_case_id}`)}>Open promoted {draft.promoted_flow_id ? "flow" : "test case"}</Button>}
    </>}
  </Stack>;
}
