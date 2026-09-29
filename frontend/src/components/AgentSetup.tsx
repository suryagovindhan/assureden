import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Dialog, DialogTitle, DialogContent, DialogActions, Stack, TextField, Typography } from "@mui/material";
import { Link } from "react-router-dom";
import api from "../lib/api";
import { requestError } from "./RunTestButton";

export default function AgentSetup() {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("My computer");
  const [downloadError, setDownloadError] = useState("");
  const qc = useQueryClient();
  const [issuedAt, setIssuedAt] = useState(0);
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (!open) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [open]);
  const pair = useMutation({ mutationFn: async () => (await api.post<{ code: string; agent_id: string; expires_in_seconds: number }>("/agent-control/enroll", { name })).data,
    onSuccess: () => { setIssuedAt(Date.now()); setNow(Date.now()); void qc.invalidateQueries({ queryKey: ["agents"] }); } });
  const connection = useQuery({
    queryKey: ['agent-setup-connection', pair.data?.agent_id],
    enabled: open && !!pair.data,
    refetchInterval: 2000,
    queryFn: async () => (await api.get<{ id: string; status: string; last_heartbeat: string | null; capabilities: { recording?: boolean } | null }[]>('/agents/')).data,
  });
  const agent = connection.data?.find(a => a.id === pair.data?.agent_id);
  const heartbeat = agent?.last_heartbeat;
  const connectedAt = heartbeat ? new Date(/[Zz]|[+-]\d\d:\d\d$/.test(heartbeat) ? heartbeat : `${heartbeat}Z`).getTime() : 0;
  const connected = !!agent && agent.status !== 'OFFLINE' && connectedAt > 0 && now - connectedAt <= 30000;
  const ready = connected && agent?.capabilities?.recording;
  const secondsLeft = pair.data ? Math.max(0, Math.ceil((issuedAt + pair.data.expires_in_seconds * 1000 - now) / 1000)) : 0;
  const download = async () => {
    try {
      setDownloadError("");
      const response = await api.get('/agent-control/download', { responseType: 'blob' });
      const url = URL.createObjectURL(response.data); const link = document.createElement('a');
      link.href = url; link.download = 'AssureDen-Agent.zip'; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch { setDownloadError('Could not download the installer. Check the server connection.'); }
  };
  return <>
    <Button variant="contained" onClick={() => setOpen(true)}>Set up agent</Button>
    <Dialog open={open} onClose={() => setOpen(false)} fullWidth maxWidth="sm">
      <DialogTitle>Connect this computer</DialogTitle>
      <DialogContent><Stack spacing={2} sx={{ pt: 1 }}>
        <Typography>One-time Windows setup. Requires Microsoft Edge and Python 3.14 with Tcl/Tk and Python on PATH.</Typography>
        <Button variant="outlined" onClick={download}>Download Windows agent</Button>
        <Typography>Extract the ZIP, open Install.cmd, then follow the agent window. Installation creates a desktop shortcut and starts the agent when you sign in.</Typography>
        <TextField label="Computer name" value={name} onChange={e => setName(e.target.value)} />
        <Button disabled={pair.isPending || !name.trim() || !!ready} onClick={() => pair.mutate()}>Generate pairing code</Button>
        {pair.data && <>
          {!connected && <TextField label={secondsLeft ? `Pairing code - ${Math.floor(secondsLeft / 60)}m ${secondsLeft % 60}s remaining` : 'Pairing code expired'} value={pair.data.code} slotProps={{ input: { readOnly: true } }} />}
          {connection.isError ? <Alert severity="error">Cannot check the agent connection. Check your server connection.</Alert>
            : ready ? <Alert severity="success">Agent connected and ready to record. Keep the companion open.</Alert>
            : connected ? <Alert severity="warning">Agent connected but does not support recording. Install the desktop agent from this dialog.</Alert>
            : <Alert severity="info">{agent?.last_heartbeat ? 'Agent disconnected. Open the companion to reconnect.' : secondsLeft ? 'Waiting for you to paste the code into the desktop companion and click Pair and connect.' : 'This code has expired. Generate a new code if pairing was not completed.'}</Alert>}
          {ready && <Button component={Link} to="/drafts" variant="contained" onClick={() => setOpen(false)}>Continue to recording</Button>}
          <Typography>Paste this code and your AssureDen API server address into the desktop agent. For this local installation, use http://127.0.0.1:8000. Keep the agent open while testing.</Typography>
        </>}
        {pair.isError && <Alert severity="error">{requestError(pair.error)}</Alert>}
        {downloadError && <Alert severity="error">{downloadError}</Alert>}
      </Stack></DialogContent>
      <DialogActions><Button onClick={() => setOpen(false)}>Done</Button></DialogActions>
    </Dialog>
  </>;
}
