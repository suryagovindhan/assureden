/**
 * ObjectExplorer.tsx — Phase 1 Object Repository two-panel explorer
 *
 * Tree: Application → Module → Page → PageObject  (lazy-loaded, collapse/expand)
 * Each node has an inline "+" button to create its child entity.
 * Right panel: PageObject detail + inline LocatorEditor.
 *
 * UX pattern:
 *   Application row  →  hover shows [+ Module]  [delete]
 *   Module row       →  hover shows [+ Page]    [delete]
 *   Page row         →  hover shows [+ Object]  [delete]
 *   PageObject row   →  click to open detail panel
 */

import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Box, Typography, IconButton, Chip, Tooltip, Skeleton,
  Collapse, List, ListItemButton, ListItemText, ListItemIcon,
  Button, alpha,
} from "@mui/material";
import {
  Apps as AppsIcon,
  ViewModule as ModuleIcon,
  WebAsset as PageIcon,
  TouchApp as ObjectIcon,
  ExpandMore, ChevronRight,
  Add as AddIcon,
  Delete as DeleteIcon,
  Search as SearchIcon,
  Circle as DotIcon,
} from "@mui/icons-material";
import { useAuth } from "../../contexts/AuthContext";
import {
  appsApi, modulesApi, pagesApi, pageObjectsApi,
  Application, Module, Page, PageObject,
} from "../../lib/api/objectRepository";
import LocatorEditor from "./LocatorEditor";
import CreateDialog from "./CreateDialog";

// ── colour helpers ─────────────────────────────────────────────────────────

const CRITICALITY_COLOR: Record<string, string> = {
  HIGH: "#ef4444", MEDIUM: "#f59e0b", LOW: "#22c55e",
};
const STATUS_COLOR: Record<string, string> = {
  DRAFT: "#6b7280", ACTIVE: "#22c55e", DEPRECATED: "#f59e0b", ARCHIVED: "#6b7280",
};
const TYPE_COLOR = "#818cf8";

// ── shared "hover action row" wrapper ────────────────────────────────────────

function HoverRow({
  children,
  actions,
}: {
  children: React.ReactNode;
  actions: React.ReactNode;
}) {
  const [hovered, setHovered] = useState(false);
  return (
    <Box
      sx={{ position: "relative" }}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      {children}
      {hovered && (
        <Box
          sx={{
            position: "absolute",
            right: 6,
            top: "50%",
            transform: "translateY(-50%)",
            display: "flex",
            gap: 0.25,
            zIndex: 1,
            bgcolor: "rgba(13,13,26,0.9)",
            borderRadius: 1,
            px: 0.25,
          }}
        >
          {actions}
        </Box>
      )}
    </Box>
  );
}

// ── Application tree item ─────────────────────────────────────────────────

function AppTreeItem({
  app,
  selectedPoId,
  onSelectPo,
  isLead,
}: {
  app: Application;
  selectedPoId: string | null;
  onSelectPo: (po: PageObject) => void;
  isLead: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const qc = useQueryClient();

  const { data: modulesData } = useQuery({
    queryKey: ["modules", app.id],
    queryFn: () => modulesApi.listByApp(app.id),
    enabled: open,
  });

  const deleteMut = useMutation({
    mutationFn: () => appsApi.delete(app.id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["applications"] }),
  });

  return (
    <>
      <HoverRow
        actions={
          <>
            <Tooltip title="Add Module">
              <IconButton
                size="small"
                onClick={(e) => { e.stopPropagation(); setCreating(true); setOpen(true); }}
                sx={{ color: "#22c55e", p: 0.3, "&:hover": { bgcolor: "rgba(34,197,94,0.1)" } }}
              >
                <AddIcon sx={{ fontSize: 13 }} />
              </IconButton>
            </Tooltip>
            {isLead && (
              <Tooltip title="Delete Application">
                <IconButton
                  size="small"
                  onClick={(e) => { e.stopPropagation(); deleteMut.mutate(); }}
                  sx={{ color: "rgba(255,255,255,0.25)", p: 0.3, "&:hover": { color: "#ef4444", bgcolor: "rgba(239,68,68,0.1)" } }}
                >
                  <DeleteIcon sx={{ fontSize: 13 }} />
                </IconButton>
              </Tooltip>
            )}
          </>
        }
      >
        <ListItemButton
          onClick={() => setOpen((o) => !o)}
          sx={{ borderRadius: 1.5, mb: 0.25, pl: 1, pr: 9 }}
        >
          <ListItemIcon sx={{ minWidth: 32, color: "#818cf8" }}>
            <AppsIcon fontSize="small" />
          </ListItemIcon>
          <ListItemText
            primary={app.name}
            slotProps={{ primary: { style: { fontSize: 13, fontWeight: 600, color: "#e2e8f0" } } }}
          />
          <Chip
            label={app.status}
            size="small"
            sx={{
              fontSize: 9, height: 16, mr: 1,
              bgcolor: alpha(STATUS_COLOR[app.status] || "#6b7280", 0.15),
              color: STATUS_COLOR[app.status] || "#6b7280", border: "none",
            }}
          />
          {open
            ? <ExpandMore sx={{ fontSize: 15, color: "rgba(255,255,255,0.35)", flexShrink: 0 }} />
            : <ChevronRight sx={{ fontSize: 15, color: "rgba(255,255,255,0.35)", flexShrink: 0 }} />}
        </ListItemButton>
      </HoverRow>

      <Collapse in={open} unmountOnExit>
        <List disablePadding sx={{ pl: 2 }}>
          {!modulesData ? (
            [1, 2].map((i) => <Skeleton key={i} height={32} sx={{ my: 0.25, borderRadius: 1 }} />)
          ) : modulesData.items.length === 0 ? (
            <Box sx={{ px: 1.5, py: 1, display: "flex", alignItems: "center", gap: 1 }}>
              <Typography sx={{ fontSize: 11, color: "rgba(255,255,255,0.25)", flexGrow: 1 }}>
                No modules yet
              </Typography>
              <Button
                size="small"
                startIcon={<AddIcon sx={{ fontSize: 12 }} />}
                onClick={() => setCreating(true)}
                sx={{
                  fontSize: 10.5, py: 0.3, px: 1,
                  color: "#22c55e",
                  border: "1px solid rgba(34,197,94,0.25)",
                  borderRadius: 1,
                  "&:hover": { bgcolor: "rgba(34,197,94,0.06)", borderColor: "#22c55e" },
                }}
              >
                Add Module
              </Button>
            </Box>
          ) : (
            modulesData.items.map((mod) => (
              <ModuleTreeItem
                key={mod.id}
                mod={mod}
                selectedPoId={selectedPoId}
                onSelectPo={onSelectPo}
                isLead={isLead}
              />
            ))
          )}
        </List>
      </Collapse>

      {creating && (
        <CreateDialog
          type="module"
          parentId={app.id}
          parentName={app.name}
          onClose={() => setCreating(false)}
          onCreated={() => {
            // Module created → keep app expanded (already open), tree will re-fetch
            setOpen(true);
          }}
        />
      )}
    </>
  );
}

// ── Module tree item ──────────────────────────────────────────────────────

function ModuleTreeItem({
  mod,
  selectedPoId,
  onSelectPo,
  isLead,
}: {
  mod: Module;
  selectedPoId: string | null;
  onSelectPo: (po: PageObject) => void;
  isLead: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const qc = useQueryClient();

  const { data: pagesData } = useQuery({
    queryKey: ["pages", mod.id],
    queryFn: () => pagesApi.listByModule(mod.id),
    enabled: open,
  });

  const deleteMut = useMutation({
    mutationFn: () => modulesApi.delete(mod.id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["modules", mod.application_id] }),
  });

  return (
    <>
      <HoverRow
        actions={
          <>
            <Tooltip title="Add Page">
              <IconButton
                size="small"
                onClick={(e) => { e.stopPropagation(); setCreating(true); setOpen(true); }}
                sx={{ color: "#22c55e", p: 0.3, "&:hover": { bgcolor: "rgba(34,197,94,0.1)" } }}
              >
                <AddIcon sx={{ fontSize: 12 }} />
              </IconButton>
            </Tooltip>
            {isLead && (
              <Tooltip title="Delete Module">
                <IconButton
                  size="small"
                  onClick={(e) => { e.stopPropagation(); deleteMut.mutate(); }}
                  sx={{ color: "rgba(255,255,255,0.2)", p: 0.3, "&:hover": { color: "#ef4444" } }}
                >
                  <DeleteIcon sx={{ fontSize: 12 }} />
                </IconButton>
              </Tooltip>
            )}
          </>
        }
      >
        <ListItemButton
          onClick={() => setOpen((o) => !o)}
          sx={{ borderRadius: 1.5, mb: 0.25, pl: 1, pr: 9 }}
        >
          <ListItemIcon sx={{ minWidth: 28, color: "#a78bfa" }}>
            <ModuleIcon fontSize="small" />
          </ListItemIcon>
          <ListItemText
            primary={mod.name}
            slotProps={{ primary: { style: { fontSize: 12.5, color: "#cbd5e1" } } }}
          />
          {open
            ? <ExpandMore sx={{ fontSize: 13, color: "rgba(255,255,255,0.3)" }} />
            : <ChevronRight sx={{ fontSize: 13, color: "rgba(255,255,255,0.3)" }} />}
        </ListItemButton>
      </HoverRow>

      <Collapse in={open} unmountOnExit>
        <List disablePadding sx={{ pl: 2 }}>
          {!pagesData ? (
            <Skeleton height={28} sx={{ my: 0.25, borderRadius: 1 }} />
          ) : pagesData.items.length === 0 ? (
            <Box sx={{ px: 1.5, py: 1, display: "flex", alignItems: "center", gap: 1 }}>
              <Typography sx={{ fontSize: 11, color: "rgba(255,255,255,0.25)", flexGrow: 1 }}>
                No pages yet
              </Typography>
              <Button
                size="small"
                startIcon={<AddIcon sx={{ fontSize: 12 }} />}
                onClick={() => setCreating(true)}
                sx={{
                  fontSize: 10.5, py: 0.3, px: 1,
                  color: "#60a5fa",
                  border: "1px solid rgba(96,165,250,0.25)",
                  borderRadius: 1,
                  "&:hover": { bgcolor: "rgba(96,165,250,0.06)", borderColor: "#60a5fa" },
                }}
              >
                Add Page
              </Button>
            </Box>
          ) : (
            pagesData.items.map((page) => (
              <PageTreeItem
                key={page.id}
                page={page}
                moduleId={mod.id}
                selectedPoId={selectedPoId}
                onSelectPo={onSelectPo}
                isLead={isLead}
              />
            ))
          )}
        </List>
      </Collapse>

      {creating && (
        <CreateDialog
          type="page"
          parentId={mod.id}
          parentName={mod.name}
          onClose={() => setCreating(false)}
          onCreated={() => {
            // Page created → auto-expand module so user sees it immediately
            setOpen(true);
          }}
        />
      )}
    </>
  );
}

// ── Page tree item ────────────────────────────────────────────────────────

function PageTreeItem({
  page,
  moduleId,
  selectedPoId,
  onSelectPo,
  isLead,
}: {
  page: Page;
  moduleId: string;
  selectedPoId: string | null;
  onSelectPo: (po: PageObject) => void;
  isLead: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const qc = useQueryClient();

  const { data: objectsData } = useQuery({
    queryKey: ["pageObjects", page.id],
    queryFn: () => pageObjectsApi.listByPage(page.id),
    enabled: open,
  });

  const deleteMut = useMutation({
    mutationFn: () => pagesApi.delete(page.id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["pages", moduleId] }),
  });

  return (
    <>
      <HoverRow
        actions={
          <>
            <Tooltip title="Add Object">
              <IconButton
                size="small"
                onClick={(e) => { e.stopPropagation(); setCreating(true); setOpen(true); }}
                sx={{ color: "#22c55e", p: 0.3, "&:hover": { bgcolor: "rgba(34,197,94,0.1)" } }}
              >
                <AddIcon sx={{ fontSize: 12 }} />
              </IconButton>
            </Tooltip>
            {isLead && (
              <Tooltip title="Delete Page">
                <IconButton
                  size="small"
                  onClick={(e) => { e.stopPropagation(); deleteMut.mutate(); }}
                  sx={{ color: "rgba(255,255,255,0.2)", p: 0.3, "&:hover": { color: "#ef4444" } }}
                >
                  <DeleteIcon sx={{ fontSize: 12 }} />
                </IconButton>
              </Tooltip>
            )}
          </>
        }
      >
        <ListItemButton
          onClick={() => setOpen((o) => !o)}
          sx={{ borderRadius: 1.5, mb: 0.25, pl: 1, pr: 9 }}
        >
          <ListItemIcon sx={{ minWidth: 26, color: "#60a5fa" }}>
            <PageIcon sx={{ fontSize: 15 }} />
          </ListItemIcon>
          <ListItemText
            primary={page.name}
            slotProps={{ primary: { style: { fontSize: 12, color: "#94a3b8" } } }}
          />
          {open
            ? <ExpandMore sx={{ fontSize: 13, color: "rgba(255,255,255,0.25)" }} />
            : <ChevronRight sx={{ fontSize: 13, color: "rgba(255,255,255,0.25)" }} />}
        </ListItemButton>
      </HoverRow>

      <Collapse in={open} unmountOnExit>
        <List disablePadding sx={{ pl: 2 }}>
          {!objectsData ? (
            <Skeleton height={26} sx={{ my: 0.25, borderRadius: 1 }} />
          ) : objectsData.items.length === 0 ? (
            <Box sx={{ px: 1.5, py: 1, display: "flex", alignItems: "center", gap: 1 }}>
              <Typography sx={{ fontSize: 10.5, color: "rgba(255,255,255,0.2)", flexGrow: 1 }}>
                No objects yet
              </Typography>
              <Button
                size="small"
                startIcon={<AddIcon sx={{ fontSize: 11 }} />}
                onClick={() => setCreating(true)}
                sx={{
                  fontSize: 10, py: 0.25, px: 0.75,
                  color: "#818cf8",
                  border: "1px solid rgba(129,140,248,0.25)",
                  borderRadius: 1,
                  "&:hover": { bgcolor: "rgba(129,140,248,0.06)", borderColor: "#818cf8" },
                }}
              >
                Add Object
              </Button>
            </Box>
          ) : (
            objectsData.items.map((po) => (
              <PageObjectRow
                key={po.id}
                po={po}
                pageId={page.id}
                selectedPoId={selectedPoId}
                onSelectPo={onSelectPo}
                isLead={isLead}
              />
            ))
          )}
        </List>
      </Collapse>

      {creating && (
        <CreateDialog
          type="page_object"
          parentId={page.id}
          parentName={page.name}
          onClose={() => setCreating(false)}
          onCreated={(newPo) => {
            // PageObject created → auto-expand page and auto-select the new object
            setOpen(true);
            onSelectPo(newPo);
          }}
        />
      )}
    </>
  );
}

// ── PageObject leaf ───────────────────────────────────────────────────────

function PageObjectRow({
  po,
  pageId,
  selectedPoId,
  onSelectPo,
  isLead,
}: {
  po: PageObject;
  pageId: string;
  selectedPoId: string | null;
  onSelectPo: (po: PageObject) => void;
  isLead: boolean;
}) {
  const qc = useQueryClient();

  const deleteMut = useMutation({
    mutationFn: () => pageObjectsApi.delete(po.id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["pageObjects", pageId] }),
  });

  return (
    <HoverRow
      actions={
        isLead ? (
          <Tooltip title="Delete Object">
            <IconButton
              size="small"
              onClick={(e) => { e.stopPropagation(); deleteMut.mutate(); }}
              sx={{ color: "rgba(255,255,255,0.2)", p: 0.3, "&:hover": { color: "#ef4444" } }}
            >
              <DeleteIcon sx={{ fontSize: 12 }} />
            </IconButton>
          </Tooltip>
        ) : null
      }
    >
      <ListItemButton
        selected={selectedPoId === po.id}
        onClick={() => onSelectPo(po)}
        sx={{
          borderRadius: 1.5, mb: 0.25, pl: 1, pr: 7,
          "&.Mui-selected": {
            bgcolor: "rgba(102,126,234,0.18)",
            "&:hover": { bgcolor: "rgba(102,126,234,0.23)" },
          },
        }}
      >
        <ListItemIcon sx={{ minWidth: 20 }}>
          <DotIcon sx={{ fontSize: 8, color: CRITICALITY_COLOR[po.criticality] || "#818cf8" }} />
        </ListItemIcon>
        <ListItemText
          primary={po.name}
          slotProps={{ primary: { style: { fontSize: 11.5, color: "#94a3b8" } } }}
        />
        <Chip
          label={po.object_type.replace("_", " ")}
          size="small"
          sx={{
            fontSize: 9, height: 15, mr: 0.5,
            bgcolor: alpha(TYPE_COLOR, 0.12), color: TYPE_COLOR, border: "none",
          }}
        />
      </ListItemButton>
    </HoverRow>
  );
}

// ── Detail Panel ─────────────────────────────────────────────────────────

function PageObjectDetail({ po }: { po: PageObject }) {
  const qc = useQueryClient();
  const { user } = useAuth();
  const isLead = ["LEAD", "ADMIN"].includes(user?.role ?? "");

  const updateMutation = useMutation({
    mutationFn: (body: Partial<PageObject>) => pageObjectsApi.update(po.id, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["pageObjects", po.page_id] }),
  });

  return (
    <Box sx={{ height: "100%", overflowY: "auto", p: 3, display: "flex", flexDirection: "column", gap: 2.5 }}>
      {/* Header */}
      <Box>
        <Typography sx={{ fontSize: 18, fontWeight: 700, color: "#e2e8f0", mb: 0.75 }}>
          {po.name}
        </Typography>
        <Box sx={{ display: "flex", gap: 0.75, flexWrap: "wrap" }}>
          <Chip label={po.object_type.replace("_", " ")} size="small"
            sx={{ fontSize: 10, bgcolor: alpha(TYPE_COLOR, 0.15), color: TYPE_COLOR }} />
          <Chip label={po.status} size="small"
            sx={{ fontSize: 10, bgcolor: alpha(STATUS_COLOR[po.status] || "#6b7280", 0.15),
                  color: STATUS_COLOR[po.status] || "#6b7280" }} />
          <Chip label={po.criticality} size="small"
            sx={{ fontSize: 10, bgcolor: alpha(CRITICALITY_COLOR[po.criticality] || "#818cf8", 0.15),
                  color: CRITICALITY_COLOR[po.criticality] || "#818cf8" }} />
          {po.page_area && (
            <Chip label={po.page_area} size="small"
              sx={{ fontSize: 10, bgcolor: "rgba(255,255,255,0.06)", color: "rgba(255,255,255,0.45)" }} />
          )}
        </Box>
      </Box>

      {po.description && (
        <Typography sx={{ fontSize: 12.5, color: "rgba(255,255,255,0.5)", lineHeight: 1.6 }}>
          {po.description}
        </Typography>
      )}

      {/* Meta */}
      <Box sx={{ bgcolor: "rgba(255,255,255,0.03)", borderRadius: 2, p: 2,
                  border: "1px solid rgba(255,255,255,0.06)" }}>
        <Typography sx={{ fontSize: 10.5, fontWeight: 600, color: "rgba(255,255,255,0.35)",
                          textTransform: "uppercase", letterSpacing: 1, mb: 1.5 }}>
          Governance
        </Typography>
        <Box sx={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 1.5 }}>
          {[
            ["Owner team", po.owner_team || "—"],
            ["Last validated", po.last_validated_at
              ? new Date(po.last_validated_at).toLocaleDateString()
              : <Box component="span" sx={{ color: "#f59e0b" }}>Not validated</Box>],
          ].map(([label, value]) => (
            <Box key={String(label)}>
              <Typography sx={{ fontSize: 10, color: "rgba(255,255,255,0.3)", mb: 0.25 }}>{label}</Typography>
              <Typography sx={{ fontSize: 12.5, color: "#e2e8f0" }}>{value}</Typography>
            </Box>
          ))}
        </Box>
      </Box>

      {/* Keywords */}
      {po.search_keywords && po.search_keywords.length > 0 && (
        <Box>
          <Typography sx={{ fontSize: 10.5, fontWeight: 600, color: "rgba(255,255,255,0.35)",
                            textTransform: "uppercase", letterSpacing: 1, mb: 1 }}>
            Keywords
          </Typography>
          <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.5 }}>
            {po.search_keywords.map((kw) => (
              <Chip key={kw} label={kw} size="small"
                sx={{ fontSize: 10, bgcolor: "rgba(255,255,255,0.05)", color: "rgba(255,255,255,0.55)" }} />
            ))}
          </Box>
        </Box>
      )}

      {/* Locator Editor */}
      <LocatorEditor
        pageObject={po}
        readOnly={!isLead}
        onSave={(locators) => updateMutation.mutate({ locators } as any)}
        saving={updateMutation.isPending}
      />
    </Box>
  );
}

// ── Main Component ────────────────────────────────────────────────────────

export default function ObjectExplorer() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const isLead = ["LEAD", "ADMIN"].includes(user?.role ?? "");

  const [selectedPo, setSelectedPo] = useState<PageObject | null>(null);
  const [creatingApp, setCreatingApp] = useState(false);

  const { data: appsData, isLoading } = useQuery({
    queryKey: ["applications"],
    queryFn: () => appsApi.list(),
  });

  return (
    <Box sx={{ display: "flex", height: "calc(100vh - 112px)", gap: 2 }}>

      {/* ── LEFT: Tree panel ───────────────────────────────────────────── */}
      <Box
        sx={{
          width: 320, flexShrink: 0,
          background: "rgba(255,255,255,0.02)",
          border: "1px solid rgba(255,255,255,0.06)",
          borderRadius: 2,
          display: "flex", flexDirection: "column",
          overflow: "hidden",
        }}
      >
        {/* Tree header */}
        <Box sx={{
          px: 2, py: 1.5,
          display: "flex", alignItems: "center", justifyContent: "space-between",
          borderBottom: "1px solid rgba(255,255,255,0.06)",
        }}>
          <Typography sx={{ fontSize: 13, fontWeight: 600, color: "#e2e8f0" }}>
            Object Repository
          </Typography>
          <Box sx={{ display: "flex", gap: 0.5 }}>
            <Tooltip title="Keyword Search">
              <IconButton
                size="small"
                onClick={() => navigate("/objects/search")}
                sx={{ color: "rgba(255,255,255,0.35)", "&:hover": { color: "#818cf8" } }}
              >
                <SearchIcon fontSize="small" />
              </IconButton>
            </Tooltip>
            <Tooltip title="Add Application">
              <IconButton
                size="small"
                onClick={() => setCreatingApp(true)}
                sx={{ color: "rgba(255,255,255,0.35)", "&:hover": { color: "#22c55e" } }}
              >
                <AddIcon fontSize="small" />
              </IconButton>
            </Tooltip>
          </Box>
        </Box>

        {/* Tree body */}
        <Box sx={{ flexGrow: 1, overflowY: "auto", p: 1 }}>
          {isLoading ? (
            [1, 2, 3].map((i) => <Skeleton key={i} height={36} sx={{ borderRadius: 1.5, mb: 0.5 }} />)
          ) : !appsData?.items.length ? (
            <Box sx={{ p: 3, textAlign: "center" }}>
              <AppsIcon sx={{ fontSize: 40, color: "rgba(255,255,255,0.08)", mb: 1 }} />
              <Typography sx={{ fontSize: 12, color: "rgba(255,255,255,0.3)", mb: 1.5 }}>
                No applications yet.
              </Typography>
              <Button
                size="small"
                variant="outlined"
                startIcon={<AddIcon />}
                onClick={() => setCreatingApp(true)}
                sx={{
                  fontSize: 11,
                  borderColor: "rgba(255,255,255,0.12)",
                  color: "rgba(255,255,255,0.5)",
                  "&:hover": { borderColor: "#22c55e", color: "#22c55e" },
                }}
              >
                Add Application
              </Button>
            </Box>
          ) : (
            <List disablePadding>
              {appsData.items.map((app) => (
                <AppTreeItem
                  key={app.id}
                  app={app}
                  selectedPoId={selectedPo?.id ?? null}
                  onSelectPo={setSelectedPo}
                  isLead={isLead}
                />
              ))}
            </List>
          )}
        </Box>

        {/* Bottom: "Add Application" shortcut if apps exist */}
        {appsData && appsData.items.length > 0 && (
          <Box sx={{ borderTop: "1px solid rgba(255,255,255,0.05)", p: 1 }}>
            <Button
              fullWidth
              size="small"
              startIcon={<AddIcon sx={{ fontSize: 13 }} />}
              onClick={() => setCreatingApp(true)}
              sx={{
                fontSize: 11, py: 0.5,
                color: "rgba(255,255,255,0.3)",
                "&:hover": { color: "#22c55e", bgcolor: "rgba(34,197,94,0.05)" },
              }}
            >
              Add Application
            </Button>
          </Box>
        )}
      </Box>

      {/* ── RIGHT: Detail panel ───────────────────────────────────────── */}
      <Box
        sx={{
          flexGrow: 1,
          background: "rgba(255,255,255,0.02)",
          border: "1px solid rgba(255,255,255,0.06)",
          borderRadius: 2,
          overflow: "hidden",
        }}
      >
        {selectedPo ? (
          <PageObjectDetail po={selectedPo} />
        ) : (
          <Box sx={{
            height: "100%",
            display: "flex", flexDirection: "column",
            alignItems: "center", justifyContent: "center", gap: 2,
          }}>
            <ObjectIcon sx={{ fontSize: 64, color: "rgba(255,255,255,0.06)" }} />
            <Typography sx={{ fontSize: 14, color: "rgba(255,255,255,0.28)", textAlign: "center" }}>
              Expand the tree → click a PageObject<br />to view its details and locators
            </Typography>
            <Button
              variant="outlined"
              startIcon={<SearchIcon />}
              onClick={() => navigate("/objects/search")}
              sx={{
                fontSize: 12,
                borderColor: "rgba(255,255,255,0.1)",
                color: "rgba(255,255,255,0.4)",
                "&:hover": { borderColor: "#818cf8", color: "#818cf8" },
              }}
            >
              Search objects by keyword
            </Button>
          </Box>
        )}
      </Box>

      {/* Create Application Dialog */}
      {creatingApp && (
        <CreateDialog
          type="application"
          onClose={() => setCreatingApp(false)}
        />
      )}
    </Box>
  );
}
