import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useMutation } from "@tanstack/react-query";
import { Button, Dialog, DialogTitle, DialogContent, DialogActions, TextField, MenuItem, Alert, Stack } from "@mui/material";
import { PlayArrow } from "@mui/icons-material";
import { listEnvironments } from "../lib/api/environments";
import { triggerRun } from "../lib/api/executions";
import { useAuth } from "../contexts/AuthContext";
import api from "../lib/api";

export function requestError(error: any): string {
  const detail = error?.response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (detail?.errors) return detail.errors.map((e: any) => `${e.step ? `Step ${e.step}: ` : ""}${e.message}`).join("; ");
  if (Array.isArray(detail)) return detail.map((e: any) => e.msg).join("; ");
  return "Request failed. Check your connection and try again.";
}

export default function RunTestButton({ caseId, environmentId, label = "Run test" }: {
  caseId: string; environmentId?: string | null; label?: string;
}) {
  const [open, setOpen] = useState(false);
  const [environment, setEnvironment] = useState(environmentId ?? "");
  const [agent, setAgent] = useState('');
  const navigate = useNavigate();
  const { user } = useAuth();
  const envs = useQuery({ queryKey: ["run-environments"], queryFn: () => listEnvironments({ limit: 200 }), enabled: open });
  const agents = useQuery({ queryKey: ['run-agents'], enabled: open, refetchInterval: 5000,
    queryFn: async () => (await api.get<{ id: string; name: string; last_heartbeat: string | null }[]>('/agents/')).data });
  const connected = (heartbeat: string | null) => heartbeat && Date.now() - new Date(heartbeat.endsWith('Z') ? heartbeat : heartbeat + 'Z').getTime() < 30000;
  const run = useMutation({
    mutationFn: () => triggerRun({ test_case_id: caseId, environment_id: environment || undefined, requested_agent_id: agent || undefined }),
    onSuccess: (result) => { setOpen(false); navigate(`/runs/${result.id}`); },
  });
  if (!user || user.role === "VIEWER") return null;
  return <>
    <Button variant="contained" startIcon={<PlayArrow />} onClick={() => { run.reset(); setOpen(true); }}>{label}</Button>
    <Dialog open={open} onClose={() => !run.isPending && setOpen(false)} fullWidth maxWidth="sm">
      <DialogTitle>{label}</DialogTitle>
      <DialogContent><Stack spacing={2} sx={{ pt: 1 }}>
        <Alert severity="info">Runs the saved test case. Save your step edits first. Choose a computer or let a compatible agent pick up the run.</Alert>
        <TextField select label="Environment" value={environment} onChange={(e) => setEnvironment(e.target.value)}>
          <MenuItem value="">No environment</MenuItem>
          {(envs.data?.items ?? []).map((e) => <MenuItem key={e.id} value={e.id}>{e.name}</MenuItem>)}
        </TextField>
        <TextField select label="Agent computer" value={agent} onChange={e => setAgent(e.target.value)}>
          <MenuItem value="">Any compatible agent</MenuItem>
          {(agents.data ?? []).map(a => <MenuItem key={a.id} value={a.id}>{a.name} — {connected(a.last_heartbeat) ? 'Connected' : 'Disconnected'}</MenuItem>)}
        </TextField>
        {!agents.data?.some(a => connected(a.last_heartbeat)) && <Alert severity="warning">No agent is connected. This run will wait in the queue until you open the paired desktop agent.</Alert>}
        <Alert severity="info">Configure variables, including passwords, in Environments before running.</Alert>
        {envs.isError && <Alert severity="error">Could not load environments.</Alert>}
        {agents.isError && <Alert severity="error">Could not load agent status. Check your connection.</Alert>}
        {run.isError && <Alert severity="error">{requestError(run.error)}</Alert>}
      </Stack></DialogContent>
      <DialogActions><Button disabled={run.isPending} onClick={() => setOpen(false)}>Cancel</Button>
        <Button variant="contained" disabled={run.isPending || envs.isLoading || envs.isError} onClick={() => run.mutate()}>
          {run.isPending ? "Queueing…" : "Start run"}
        </Button></DialogActions>
    </Dialog>
  </>;
}
