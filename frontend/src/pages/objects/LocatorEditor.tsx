/**
 * LocatorEditor.tsx — Inline locator CRUD for a PageObject
 *
 * Renders the locators JSON array with:
 *  - Type badge (CSS_SELECTOR, XPATH, ID, ARIA_LABEL, TEST_ID, TEXT)
 *  - Value display/edit
 *  - Priority number
 *  - is_primary toggle
 *  - is_active toggle (disable without deleting history)
 *  - notes field
 *  - Add / Remove controls
 *  - Save to PUT /api/object-repository/objects/{id}
 */

import { useState } from "react";
import {
  Box, Typography, IconButton, Chip, Button, TextField,
  Select, MenuItem, Switch, Tooltip, Collapse, Divider,
  alpha, FormControlLabel,
} from "@mui/material";
import {
  Add as AddIcon,
  Delete as DeleteIcon,
  Save as SaveIcon,
  ExpandMore, ChevronRight,
  Star as PrimaryIcon,
} from "@mui/icons-material";
import { PageObject, Locator, LocatorType } from "../../lib/api/objectRepository";

const LOCATOR_TYPES: LocatorType[] = [
  "CSS_SELECTOR", "XPATH", "ID", "ARIA_LABEL", "TEST_ID", "TEXT",
];

const TYPE_BADGE: Record<LocatorType, { label: string; color: string }> = {
  CSS_SELECTOR: { label: "CSS",   color: "#38bdf8" },
  XPATH:        { label: "XPath", color: "#fb923c" },
  ID:           { label: "ID",    color: "#a78bfa" },
  ARIA_LABEL:   { label: "Aria",  color: "#34d399" },
  TEST_ID:      { label: "Test",  color: "#f472b6" },
  TEXT:         { label: "Text",  color: "#facc15" },
};

const defaultLocator = (): Omit<Locator, "added_at"> => ({
  type: "CSS_SELECTOR",
  value: "",
  priority: 1,
  is_primary: false,
  is_active: true,
  added_by: "MANUAL",
  notes: null,
});

interface Props {
  pageObject: PageObject;
  readOnly?: boolean;
  onSave: (locators: Locator[]) => void;
  saving?: boolean;
}

export default function LocatorEditor({ pageObject, readOnly = false, onSave, saving = false }: Props) {
  const [locators, setLocators] = useState<Locator[]>(pageObject.locators ?? []);
  const [expandedIdx, setExpandedIdx] = useState<number | null>(null);
  const [dirty, setDirty] = useState(false);

  function update(idx: number, patch: Partial<Locator>) {
    setLocators((prev) => {
      const next = [...prev];
      next[idx] = { ...next[idx], ...patch };
      return next;
    });
    setDirty(true);
  }

  function addLocator() {
    const next = [...locators, { ...defaultLocator(), added_at: new Date().toISOString() }];
    setLocators(next);
    setExpandedIdx(next.length - 1);
    setDirty(true);
  }

  function removeLocator(idx: number) {
    setLocators((prev) => prev.filter((_, i) => i !== idx));
    setExpandedIdx(null);
    setDirty(true);
  }

  function handleSave() {
    onSave(locators);
    setDirty(false);
  }

  return (
    <Box>
      {/* Section header */}
      <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", mb: 1.5 }}>
        <Typography sx={{ fontSize: 11, fontWeight: 600, color: "rgba(255,255,255,0.4)",
                          textTransform: "uppercase", letterSpacing: 1 }}>
          Locators ({locators.filter((l) => l.is_active).length} active / {locators.length} total)
        </Typography>
        {!readOnly && (
          <Box sx={{ display: "flex", gap: 0.75 }}>
            {dirty && (
              <Button
                size="small"
                variant="contained"
                startIcon={saving ? null : <SaveIcon />}
                onClick={handleSave}
                disabled={saving}
                sx={{ fontSize: 11, py: 0.4, px: 1.25,
                      background: "linear-gradient(135deg, #667eea, #764ba2)",
                      "&:hover": { background: "linear-gradient(135deg, #5a71e4, #6a4298)" } }}
              >
                {saving ? "Saving…" : "Save"}
              </Button>
            )}
            <Button
              size="small"
              startIcon={<AddIcon />}
              onClick={addLocator}
              sx={{ fontSize: 11, py: 0.4, px: 1.25,
                    color: "#22c55e", borderColor: "rgba(34,197,94,0.3)", border: "1px solid",
                    "&:hover": { borderColor: "#22c55e", bgcolor: "rgba(34,197,94,0.06)" } }}
            >
              Add
            </Button>
          </Box>
        )}
      </Box>

      {/* Empty state */}
      {locators.length === 0 && (
        <Box sx={{ textAlign: "center", py: 3, border: "1px dashed rgba(255,255,255,0.08)", borderRadius: 2 }}>
          <Typography sx={{ fontSize: 12, color: "rgba(255,255,255,0.25)" }}>
            No locators defined yet.
          </Typography>
          {!readOnly && (
            <Button size="small" startIcon={<AddIcon />} onClick={addLocator} sx={{ mt: 1, fontSize: 11 }}>
              Add first locator
            </Button>
          )}
        </Box>
      )}

      {/* Locator list */}
      <Box sx={{ display: "flex", flexDirection: "column", gap: 0.75 }}>
        {locators.map((loc, idx) => {
          const badge = TYPE_BADGE[loc.type] || { label: loc.type, color: "#818cf8" };
          const isExpanded = expandedIdx === idx;

          return (
            <Box
              key={idx}
              sx={{
                border: "1px solid",
                borderColor: isExpanded ? "rgba(102,126,234,0.3)" : "rgba(255,255,255,0.06)",
                borderRadius: 1.5,
                bgcolor: isExpanded ? "rgba(102,126,234,0.05)" : "rgba(255,255,255,0.02)",
                opacity: loc.is_active ? 1 : 0.45,
                transition: "all 0.15s",
              }}
            >
              {/* Row summary */}
              <Box
                sx={{ display: "flex", alignItems: "center", gap: 1, px: 1.5, py: 1,
                      cursor: "pointer" }}
                onClick={() => setExpandedIdx(isExpanded ? null : idx)}
              >
                <Chip
                  label={badge.label}
                  size="small"
                  sx={{ fontSize: 10, height: 18, bgcolor: alpha(badge.color, 0.15),
                        color: badge.color, border: "none", minWidth: 40, flexShrink: 0 }}
                />

                {loc.is_primary && (
                  <Tooltip title="Primary locator">
                    <PrimaryIcon sx={{ fontSize: 13, color: "#f59e0b", flexShrink: 0 }} />
                  </Tooltip>
                )}

                <Typography
                  sx={{ fontSize: 11.5, color: "#94a3b8", flexGrow: 1,
                        overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
                >
                  {loc.value || <em style={{ color: "rgba(255,255,255,0.2)" }}>empty</em>}
                </Typography>

                <Chip
                  label={`P${loc.priority}`}
                  size="small"
                  sx={{ fontSize: 9, height: 16, bgcolor: "rgba(255,255,255,0.05)",
                        color: "rgba(255,255,255,0.4)", border: "none", flexShrink: 0 }}
                />

                {!readOnly && (
                  <IconButton
                    size="small"
                    onClick={(e) => { e.stopPropagation(); removeLocator(idx); }}
                    sx={{ color: "rgba(255,255,255,0.2)", p: 0.25,
                          "&:hover": { color: "#ef4444" } }}
                  >
                    <DeleteIcon sx={{ fontSize: 14 }} />
                  </IconButton>
                )}

                {isExpanded
                  ? <ExpandMore sx={{ fontSize: 14, color: "rgba(255,255,255,0.3)", flexShrink: 0 }} />
                  : <ChevronRight sx={{ fontSize: 14, color: "rgba(255,255,255,0.3)", flexShrink: 0 }} />}
              </Box>

              {/* Expanded editor */}
              <Collapse in={isExpanded} unmountOnExit>
                <Divider sx={{ borderColor: "rgba(255,255,255,0.06)" }} />
                <Box sx={{ p: 1.5, display: "flex", flexDirection: "column", gap: 1.5 }}>
                  {/* Type */}
                  <Box sx={{ display: "flex", gap: 1.5, alignItems: "flex-start", flexWrap: "wrap" }}>
                    <Box sx={{ minWidth: 140 }}>
                      <Typography sx={{ fontSize: 10, color: "rgba(255,255,255,0.35)", mb: 0.5 }}>Type</Typography>
                      <Select
                        size="small"
                        value={loc.type}
                        disabled={readOnly}
                        onChange={(e) => update(idx, { type: e.target.value as LocatorType })}
                        sx={{ fontSize: 11.5, height: 30,
                              "& .MuiOutlinedInput-notchedOutline": { borderColor: "rgba(255,255,255,0.12)" } }}
                      >
                        {LOCATOR_TYPES.map((t) => (
                          <MenuItem key={t} value={t} sx={{ fontSize: 12 }}>{t}</MenuItem>
                        ))}
                      </Select>
                    </Box>

                    {/* Priority */}
                    <Box sx={{ width: 72 }}>
                      <Typography sx={{ fontSize: 10, color: "rgba(255,255,255,0.35)", mb: 0.5 }}>Priority</Typography>
                      <TextField
                        size="small"
                        type="number"
                        disabled={readOnly}
                        value={loc.priority}
                        onChange={(e) => update(idx, { priority: Math.max(1, parseInt(e.target.value) || 1) })}
                        slotProps={{ htmlInput: { min: 1, max: 99, style: { fontSize: 12, textAlign: "center" } } }}
                        sx={{ "& .MuiOutlinedInput-notchedOutline": { borderColor: "rgba(255,255,255,0.12)" },
                              "& input": { py: 0.5, px: 0.75 } }}
                      />
                    </Box>

                    {/* Toggles */}
                    <Box sx={{ display: "flex", gap: 1.5, alignItems: "center", pt: 2.5 }}>
                      <FormControlLabel
                        control={
                          <Switch
                            size="small"
                            checked={loc.is_primary}
                            disabled={readOnly}
                            onChange={(e) => update(idx, { is_primary: e.target.checked })}
                          />
                        }
                        label={<Typography sx={{ fontSize: 10.5, color: "rgba(255,255,255,0.4)" }}>Primary</Typography>}
                      />
                      <FormControlLabel
                        control={
                          <Switch
                            size="small"
                            checked={loc.is_active}
                            disabled={readOnly}
                            onChange={(e) => update(idx, { is_active: e.target.checked })}
                          />
                        }
                        label={<Typography sx={{ fontSize: 10.5, color: "rgba(255,255,255,0.4)" }}>Active</Typography>}
                      />
                    </Box>
                  </Box>

                  {/* Value */}
                  <Box>
                    <Typography sx={{ fontSize: 10, color: "rgba(255,255,255,0.35)", mb: 0.5 }}>Value</Typography>
                    <TextField
                      fullWidth
                      size="small"
                      disabled={readOnly}
                      value={loc.value}
                      onChange={(e) => update(idx, { value: e.target.value })}
                      placeholder={loc.type === "CSS_SELECTOR" ? "#username" : loc.type === "XPATH" ? "//input[@id='user']" : ""}
                      sx={{ "& .MuiOutlinedInput-notchedOutline": { borderColor: "rgba(255,255,255,0.12)" },
                            "& input": { fontSize: 12, fontFamily: "monospace" } }}
                    />
                  </Box>

                  {/* Notes */}
                  <Box>
                    <Typography sx={{ fontSize: 10, color: "rgba(255,255,255,0.35)", mb: 0.5 }}>Notes (optional)</Typography>
                    <TextField
                      fullWidth
                      size="small"
                      disabled={readOnly}
                      multiline
                      maxRows={2}
                      value={loc.notes ?? ""}
                      onChange={(e) => update(idx, { notes: e.target.value || null })}
                      placeholder="e.g. Fallback after page redesign, Temporary for build 14.2"
                      sx={{ "& .MuiOutlinedInput-notchedOutline": { borderColor: "rgba(255,255,255,0.12)" },
                            "& textarea": { fontSize: 11.5 } }}
                    />
                  </Box>

                  {/* Meta: added_by + added_at */}
                  {loc.added_at && (
                    <Typography sx={{ fontSize: 10, color: "rgba(255,255,255,0.2)" }}>
                      Added {loc.added_by === "RECORDER" ? "by recorder" : "manually"} ·{" "}
                      {new Date(loc.added_at).toLocaleDateString()}
                    </Typography>
                  )}
                </Box>
              </Collapse>
            </Box>
          );
        })}
      </Box>
    </Box>
  );
}
