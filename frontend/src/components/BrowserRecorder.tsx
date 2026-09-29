import { useState } from "react";
import { useAuth } from "../contexts/AuthContext";
import AgentSetup from "./AgentSetup";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Stack, TextField, MenuItem, Paper, Typography } from "@mui/material";
import api from "../lib/api";
import { requestError } from "./RunTestButton";

type Recording = { id: string; name: string; status: string; draft_id: string | null; error: string | null };
export default function BrowserRecorder({ onReview }: { onReview: (id: string) => void }) {
  const { user } = useAuth();
  const [name, setName] = useState('New recorded test');
  const [url, setUrl] = useState('');
  const [agentId, setAgentId] = useState('');
  const qc = useQueryClient();
  const agents = useQuery({ queryKey: ['recording-agents'], refetchInterval: 5000,
    queryFn: async () => (await api.get<{ id: string; name: string; status: string; last_heartbeat: string | null; capabilities: { recording?: boolean } | null }[]>('/agents/')).data });
  const recordings = useQuery({ queryKey: ['recordings'], refetchInterval: 2000,
    queryFn: async () => (await api.get<Recording[]>('/agent-control/recordings')).data });
  const start = useMutation({ mutationFn: () => api.post('/agent-control/recordings', { name, url, agent_id: agentId }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['recordings'] }) });
  const stop = useMutation({ mutationFn: (id: string) => api.post(`/agent-control/recordings/${id}/stop`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['recordings'] }) });
  const cancel = useMutation({ mutationFn: (id: string) => api.post(`/agent-control/recordings/${id}/cancel`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['recordings'] }) });
  const recordingAgents = (agents.data ?? []).filter(a => a.capabilities?.recording);
  const isConnected = (agent: typeof recordingAgents[number]) => {
    const time = agent.last_heartbeat;
    if (!time || agent.status === 'OFFLINE') return false;
    const heartbeat = new Date(/[Zz]|[+-]\d\d:\d\d$/.test(time) ? time : `${time}Z`).getTime();
    return Number.isFinite(heartbeat) && Date.now() - heartbeat <= 30000;
  };
  const selectedAgent = recordingAgents.find(a => a.id === agentId);
  const ready = selectedAgent && isConnected(selectedAgent);
  const canRecord = !!user && user.role !== 'VIEWER';
  return <Paper sx={{ p: 2 }}><Stack spacing={2}>
    <Typography variant="h6">Record a test</Typography>
    <TextField label="Recording name" value={name} onChange={e => setName(e.target.value)} />
    <TextField label="Application URL" placeholder="https://your-test-application" value={url} onChange={e => setUrl(e.target.value)} />
    <TextField select label="Agent computer" value={agentId} onChange={e => setAgentId(e.target.value)}>
      {recordingAgents.map(a => <MenuItem key={a.id} value={a.id} disabled={!isConnected(a)}>{a.name} — {isConnected(a) ? 'Connected' : 'Offline'}</MenuItem>)}
    </TextField>
    {agents.isPending && <Typography>Checking agent connections…</Typography>}
    {!agents.isPending && !agents.isError && !recordingAgents.some(isConnected) && <Alert severity="info">
      Open the AssureDen Agent companion on your computer and keep it open while recording.
      {user?.role === 'ADMIN' ? ' For a new computer, use Set up agent below.' : ' Ask your administrator to pair the computer if it has not been set up yet.'}
    </Alert>}
    {user?.role === 'ADMIN' && <AgentSetup />}
    {selectedAgent && !ready && <Alert severity="warning">The selected agent is offline. Reconnect the companion or choose another connected computer.</Alert>}
    {!canRecord && <Alert severity="info">Recording requires the Tester role or higher.</Alert>}
    <Button variant="contained" disabled={!canRecord || !ready || agents.isError || !name.trim() || !url.trim() || start.isPending} onClick={() => start.mutate()}>Start recording</Button>
    <Typography variant="body2">Interact in the Edge window on the selected computer, then click Stop and review here. Main tab only; recordings capture actions. Add assertions after creating the test case.</Typography>
    {(start.isError || stop.isError || cancel.isError) && <Alert severity="error">{requestError(start.error || stop.error || cancel.error)}</Alert>}
    {(agents.isError || recordings.isError) && <Alert severity="error">Could not load agents or recordings.</Alert>}
    {(recordings.data ?? []).map(r => <Stack key={r.id} direction="row" spacing={2} sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
      <Typography>{r.name} — {r.status}</Typography>
      {['REQUESTED', 'RECORDING'].includes(r.status) && <Button disabled={stop.isPending} onClick={() => stop.mutate(r.id)}>{r.status === 'REQUESTED' ? 'Cancel' : 'Stop and review'}</Button>}
      {['RECORDING', 'STOP_REQUESTED'].includes(r.status) && <Button color="warning" disabled={cancel.isPending} onClick={() => cancel.mutate(r.id)}>Discard recording</Button>}
      {r.draft_id && <Button onClick={() => onReview(r.draft_id!)}>Review draft</Button>}
      {r.error && <Alert severity="error">{r.error}</Alert>}
    </Stack>)}
  </Stack></Paper>;
}
