/**
 * CreateDialog.tsx — Generic create dialog for all hierarchy levels
 *
 * Supports: application | module | page | page_object
 * Each type shows the relevant fields for that entity.
 */

import { useState } from "react";
import {
  Dialog, DialogTitle, DialogContent, DialogActions,
  TextField, Button, Box, CircularProgress,
  Select, MenuItem, FormControl, InputLabel, Chip,
} from "@mui/material";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  appsApi, modulesApi, pagesApi, pageObjectsApi,
  ObjectType, PageArea, Criticality,
} from "../../lib/api/objectRepository";

type CreateType = "application" | "module" | "page" | "page_object";

interface Props {
  type: CreateType;
  parentId?: string;           // app_id for module, module_id for page, page_id for po
  parentName?: string;         // shown in dialog subtitle
  onClose: () => void;
  onCreated?: (entity: any) => void;  // receives the newly created entity for auto-expand/select
}

const OBJECT_TYPES: ObjectType[] = [
  "INPUT", "BUTTON", "LINK", "DROPDOWN", "CHECKBOX", "RADIO",
  "TABLE", "CONTAINER", "TEXT", "IFRAME", "DATE_PICKER", "FILE_UPLOAD",
];
const PAGE_AREAS: PageArea[] = ["HEADER", "BODY", "FOOTER", "MODAL", "SIDEBAR", "NAVIGATION"];
const CRITICALITIES: Criticality[] = ["HIGH", "MEDIUM", "LOW"];

const TITLE: Record<CreateType, string> = {
  application: "New Application",
  module: "New Module",
  page: "New Page",
  page_object: "New Page Object",
};

export default function CreateDialog({ type, parentId, parentName, onClose, onCreated }: Props) {
  const qc = useQueryClient();

  // Common fields
  const [name, setName] = useState("");
  const [desc, setDesc] = useState("");
  // Page-specific
  const [urlPattern, setUrlPattern] = useState("");
  // PageObject-specific
  const [objectType, setObjectType] = useState<ObjectType>("BUTTON");
  const [pageArea, setPageArea] = useState<PageArea>("BODY");
  const [criticality, setCriticality] = useState<Criticality>("MEDIUM");

  const mutation = useMutation<any, Error, void>({
    mutationFn: () => {
      const trimmedName = name.trim();
      if (type === "application") {
        return appsApi.create({ name: trimmedName, description: desc.trim() || undefined });
      }
      if (type === "module" && parentId) {
        return modulesApi.create(parentId, { name: trimmedName, description: desc.trim() || undefined });
      }
      if (type === "page" && parentId) {
        return pagesApi.create(parentId, {
          name: trimmedName,
          description: desc.trim() || undefined,
          url_pattern: urlPattern.trim() || undefined,
        });
      }
      if (type === "page_object" && parentId) {
        return pageObjectsApi.create(parentId, {
          name: trimmedName,
          description: desc.trim() || undefined,
          object_type: objectType,
          page_area: pageArea,
          criticality,
          status: "DRAFT",
        });
      }
      return Promise.reject("Unknown type or missing parentId");
    },
    onSuccess: (created) => {
      // Invalidate the relevant query so the tree refreshes
      if (type === "application") qc.invalidateQueries({ queryKey: ["applications"] });
      if (type === "module" && parentId) qc.invalidateQueries({ queryKey: ["modules", parentId] });
      if (type === "page" && parentId) qc.invalidateQueries({ queryKey: ["pages", parentId] });
      if (type === "page_object" && parentId) qc.invalidateQueries({ queryKey: ["pageObjects", parentId] });
      onCreated?.(created);
      onClose();
    },
  });

  const canSubmit = name.trim().length > 0 && !mutation.isPending;

  return (
    <Dialog
      open
      onClose={onClose}
      maxWidth="xs"
      fullWidth
      slotProps={{
        paper: {
          sx: {
            background: "#13132a",
            border: "1px solid rgba(255,255,255,0.1)",
            borderRadius: 2,
          },
        },
      }}
    >
      <DialogTitle sx={{ fontSize: 15, fontWeight: 600, color: "#e2e8f0", pb: 0.5 }}>
        {TITLE[type]}
        {parentName && (
          <Box component="span" sx={{ fontSize: 11, color: "rgba(255,255,255,0.35)", ml: 1 }}>
            under {parentName}
          </Box>
        )}
      </DialogTitle>

      <DialogContent sx={{ pt: "12px !important" }}>
        <Box sx={{ display: "flex", flexDirection: "column", gap: 1.5 }}>

          {/* Name — always shown */}
          <TextField
            label="Name *"
            fullWidth
            size="small"
            autoFocus
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && canSubmit && mutation.mutate()}
            slotProps={{ htmlInput: { maxLength: 200 } }}
            sx={fieldSx}
          />

          {/* Description — always shown */}
          <TextField
            label="Description"
            fullWidth
            size="small"
            multiline
            rows={2}
            value={desc}
            onChange={(e) => setDesc(e.target.value)}
            sx={fieldSx}
          />

          {/* Page-specific: URL pattern */}
          {type === "page" && (
            <TextField
              label="URL Pattern"
              fullWidth
              size="small"
              placeholder="/login, /dashboard/:id"
              value={urlPattern}
              onChange={(e) => setUrlPattern(e.target.value)}
              sx={fieldSx}
            />
          )}

          {/* PageObject-specific */}
          {type === "page_object" && (
            <>
              <FormControl size="small" fullWidth sx={fieldSx}>
                <InputLabel>Object Type *</InputLabel>
                <Select
                  value={objectType}
                  label="Object Type *"
                  onChange={(e) => setObjectType(e.target.value as ObjectType)}
                >
                  {OBJECT_TYPES.map((t) => (
                    <MenuItem key={t} value={t} sx={{ fontSize: 12 }}>
                      {t.replace("_", " ")}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>

              <Box sx={{ display: "flex", gap: 1 }}>
                <FormControl size="small" fullWidth sx={fieldSx}>
                  <InputLabel>Page Area</InputLabel>
                  <Select
                    value={pageArea}
                    label="Page Area"
                    onChange={(e) => setPageArea(e.target.value as PageArea)}
                  >
                    {PAGE_AREAS.map((a) => (
                      <MenuItem key={a} value={a} sx={{ fontSize: 12 }}>{a}</MenuItem>
                    ))}
                  </Select>
                </FormControl>

                <FormControl size="small" fullWidth sx={fieldSx}>
                  <InputLabel>Criticality</InputLabel>
                  <Select
                    value={criticality}
                    label="Criticality"
                    onChange={(e) => setCriticality(e.target.value as Criticality)}
                  >
                    {CRITICALITIES.map((c) => (
                      <MenuItem key={c} value={c} sx={{ fontSize: 12 }}>{c}</MenuItem>
                    ))}
                  </Select>
                </FormControl>
              </Box>
            </>
          )}

          {/* Error */}
          {mutation.isError && (
            <Box sx={{ fontSize: 12, color: "#ef4444", mt: 0.5 }}>
              {(() => {
                const detail = (mutation.error as any)?.response?.data?.detail;
                if (Array.isArray(detail)) return detail.map((d: any) => d.msg || JSON.stringify(d)).join(", ");
                return detail || "Failed to create. Check if the name already exists.";
              })()}
            </Box>
          )}
        </Box>
      </DialogContent>

      <DialogActions sx={{ px: 2.5, pb: 2, pt: 0.5, gap: 1 }}>
        <Button
          size="small"
          onClick={onClose}
          sx={{ color: "rgba(255,255,255,0.4)", fontSize: 12 }}
        >
          Cancel
        </Button>
        <Button
          size="small"
          variant="contained"
          disabled={!canSubmit}
          onClick={() => mutation.mutate()}
          sx={{
            fontSize: 12,
            px: 2,
            background: "linear-gradient(135deg, #667eea, #764ba2)",
            "&:hover": { background: "linear-gradient(135deg, #5a71e4, #6a4298)" },
            "&.Mui-disabled": { opacity: 0.5 },
          }}
        >
          {mutation.isPending ? <CircularProgress size={14} sx={{ color: "#fff" }} /> : "Create"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

const fieldSx = {
  "& .MuiOutlinedInput-notchedOutline": { borderColor: "rgba(255,255,255,0.15)" },
  "& .MuiInputLabel-root": { color: "rgba(255,255,255,0.4)" },
  "& .MuiInputBase-input": { color: "#e2e8f0" },
  "& .MuiSelect-icon": { color: "rgba(255,255,255,0.4)" },
};
