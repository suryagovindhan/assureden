import { useState } from "react";
import {
  Box, Typography, Button, Table, TableBody, TableCell,
  TableContainer, TableHead, TableRow, Paper, Chip,
  IconButton, Dialog, DialogTitle, DialogContent,
  DialogActions, TextField, MenuItem, Alert, CircularProgress,
  Tooltip, Avatar,
} from "@mui/material";
import { Add, Delete, Refresh } from "@mui/icons-material";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import api from "../../lib/api";

interface User {
  id: string;
  org_id: string;
  username: string;
  email: string;
  role: string;
  is_active: boolean;
}

const ROLES = ["ADMIN", "LEAD", "TESTER", "VIEWER"];

type ChipColor = "error" | "warning" | "info" | "default";
const ROLE_COLORS: Record<string, ChipColor> = {
  ADMIN: "error", LEAD: "warning", TESTER: "info", VIEWER: "default",
};

export default function UsersPage() {
  const qc = useQueryClient();
  const [createOpen, setCreateOpen] = useState(false);
  const [form, setForm] = useState({ username: "", email: "", password: "", role: "TESTER" });
  const [formError, setFormError] = useState("");

  const { data: users = [], isLoading } = useQuery<User[]>({
    queryKey: ["users"],
    queryFn: () => api.get("/users/").then((r) => r.data),
  });

  const createMutation = useMutation({
    mutationFn: (body: typeof form) => api.post("/users/", body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["users"] });
      setCreateOpen(false);
      setForm({ username: "", email: "", password: "", role: "TESTER" });
      setFormError("");
    },
    onError: (e: unknown) => {
      const err = e as { response?: { data?: { detail?: string } } };
      setFormError(err.response?.data?.detail ?? "Failed to create user");
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.delete(`/users/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["users"] }),
  });

  return (
    <Box>
      <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", mb: 3 }}>
        <Box>
          <Typography variant="h5" sx={{ fontWeight: 700, color: "#fff" }}>Users</Typography>
          <Typography variant="body2" sx={{ color: "rgba(255,255,255,0.4)" }}>
            Manage org members and their roles
          </Typography>
        </Box>
        <Box sx={{ display: "flex", gap: 1 }}>
          <Tooltip title="Refresh">
            <IconButton
              onClick={() => qc.invalidateQueries({ queryKey: ["users"] })}
              sx={{ color: "rgba(255,255,255,0.5)" }}
            >
              <Refresh />
            </IconButton>
          </Tooltip>
          <Button
            id="create-user-button"
            variant="contained"
            startIcon={<Add />}
            onClick={() => setCreateOpen(true)}
            sx={{
              background: "linear-gradient(135deg, #667eea, #764ba2)",
              textTransform: "none", fontWeight: 600, borderRadius: 2,
            }}
          >
            Add User
          </Button>
        </Box>
      </Box>

      <TableContainer
        component={Paper}
        sx={{
          background: "rgba(255,255,255,0.03)",
          border: "1px solid rgba(255,255,255,0.07)",
          borderRadius: 3,
        }}
      >
        <Table>
          <TableHead>
            <TableRow
              sx={{
                "& th": {
                  color: "rgba(255,255,255,0.4)", fontSize: 12, fontWeight: 600,
                  borderBottom: "1px solid rgba(255,255,255,0.07)",
                  letterSpacing: "0.05em", textTransform: "uppercase",
                },
              }}
            >
              <TableCell>User</TableCell>
              <TableCell>Email</TableCell>
              <TableCell>Role</TableCell>
              <TableCell>Status</TableCell>
              <TableCell align="right">Actions</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {isLoading ? (
              <TableRow>
                <TableCell colSpan={5} align="center" sx={{ py: 4 }}>
                  <CircularProgress size={28} sx={{ color: "#667eea" }} />
                </TableCell>
              </TableRow>
            ) : users.map((user) => (
              <TableRow
                key={user.id}
                sx={{
                  "& td": {
                    color: "rgba(255,255,255,0.8)",
                    borderBottom: "1px solid rgba(255,255,255,0.05)",
                  },
                  "&:hover": { background: "rgba(255,255,255,0.02)" },
                }}
              >
                <TableCell>
                  <Box sx={{ display: "flex", alignItems: "center", gap: 1.5 }}>
                    <Avatar sx={{ width: 32, height: 32, bgcolor: "#667eea", fontSize: 13 }}>
                      {user.username[0].toUpperCase()}
                    </Avatar>
                    <Typography sx={{ fontWeight: 500, fontSize: 14 }}>{user.username}</Typography>
                  </Box>
                </TableCell>
                <TableCell sx={{ fontSize: 13 }}>{user.email}</TableCell>
                <TableCell>
                  <Chip
                    label={user.role}
                    size="small"
                    color={ROLE_COLORS[user.role] ?? "default"}
                    variant="outlined"
                    sx={{ fontWeight: 600, fontSize: 11 }}
                  />
                </TableCell>
                <TableCell>
                  <Chip
                    label={user.is_active ? "Active" : "Inactive"}
                    size="small"
                    color={user.is_active ? "success" : "default"}
                    sx={{ fontWeight: 500, fontSize: 11 }}
                  />
                </TableCell>
                <TableCell align="right">
                  <Tooltip title="Remove (soft delete)">
                    <IconButton
                      id={`delete-user-${user.id}`}
                      size="small"
                      onClick={() => deleteMutation.mutate(user.id)}
                      sx={{ color: "#ef5350" }}
                    >
                      <Delete fontSize="small" />
                    </IconButton>
                  </Tooltip>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>

      {/* Create User Dialog */}
      <Dialog
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        slotProps={{ paper: { sx: { background: "#1a1a2e", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 3, minWidth: 400 } } }}
      >
        <DialogTitle sx={{ fontWeight: 700, color: "#fff" }}>Add User</DialogTitle>
        <DialogContent
          sx={{ display: "flex", flexDirection: "column", gap: 2, pt: "16px !important" }}
        >
          {formError && (
            <Alert severity="error" sx={{ borderRadius: 2 }}>{formError}</Alert>
          )}
          <TextField
            id="new-user-username" label="Username" value={form.username}
            onChange={(e) => setForm({ ...form, username: e.target.value })}
            required fullWidth sx={dialogInputSx}
          />
          <TextField
            id="new-user-email" label="Email" type="email" value={form.email}
            onChange={(e) => setForm({ ...form, email: e.target.value })}
            required fullWidth sx={dialogInputSx}
          />
          <TextField
            id="new-user-password" label="Password" type="password" value={form.password}
            onChange={(e) => setForm({ ...form, password: e.target.value })}
            required fullWidth sx={dialogInputSx}
          />
          <TextField
            id="new-user-role" label="Role" select value={form.role}
            onChange={(e) => setForm({ ...form, role: e.target.value })}
            fullWidth sx={dialogInputSx}
          >
            {ROLES.map((r) => <MenuItem key={r} value={r}>{r}</MenuItem>)}
          </TextField>
        </DialogContent>
        <DialogActions sx={{ p: 2.5 }}>
          <Button
            onClick={() => setCreateOpen(false)}
            sx={{ color: "rgba(255,255,255,0.5)", textTransform: "none" }}
          >
            Cancel
          </Button>
          <Button
            id="confirm-create-user"
            variant="contained"
            onClick={() => createMutation.mutate(form)}
            disabled={createMutation.isPending}
            sx={{
              background: "linear-gradient(135deg, #667eea, #764ba2)",
              textTransform: "none", borderRadius: 2,
            }}
          >
            {createMutation.isPending
              ? <CircularProgress size={18} sx={{ color: "#fff" }} />
              : "Create"
            }
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}

const dialogInputSx = {
  "& .MuiOutlinedInput-root": {
    color: "#fff",
    "& fieldset": { borderColor: "rgba(255,255,255,0.2)" },
    "&:hover fieldset": { borderColor: "rgba(255,255,255,0.3)" },
    "&.Mui-focused fieldset": { borderColor: "#667eea" },
  },
  "& .MuiInputLabel-root": { color: "rgba(255,255,255,0.5)" },
  "& .MuiInputLabel-root.Mui-focused": { color: "#667eea" },
  "& .MuiSelect-icon": { color: "rgba(255,255,255,0.5)" },
};
