/**
 * PageObjectPicker.tsx — Reusable PageObject search popover
 *
 * Shows full breadcrumb: App > Module > Page > Object
 */

import { useState, useCallback } from "react";
import {
  Box, TextField, Popover, List, ListItemButton, Typography,
  CircularProgress, Chip, InputAdornment,
} from "@mui/material";
import {
  Search as SearchIcon, TouchApp as PoIcon,
} from "@mui/icons-material";
import { useQuery } from "@tanstack/react-query";
import { pageObjectsApi, type PageObjectSearchResult } from "../../lib/api/objectRepository";

export interface PickedPageObject {
  id: string;
  name: string;
  object_type: string;
  application_name: string;
  module_name: string;
  page_name: string;
  updated_at: string;
}

interface Props {
  value: PickedPageObject | null;
  onChange: (po: PickedPageObject | null) => void;
  label?: string;
  placeholder?: string;
  disabled?: boolean;
}

export default function PageObjectPicker({
  value, onChange, label = "PageObject", placeholder = "Search objects…", disabled,
}: Props) {
  const [anchor, setAnchor] = useState<HTMLElement | null>(null);
  const [q, setQ] = useState("");

  const open = Boolean(anchor) && q.length >= 2;

  const { data, isFetching } = useQuery({
    queryKey: ["po-search", q],
    queryFn: () => pageObjectsApi.search(q),
    enabled: q.length >= 2,
    staleTime: 10_000,
  });

  const items: PageObjectSearchResult[] = data?.items ?? [];

  const handleSelect = useCallback(
    (po: PageObjectSearchResult) => {
      onChange(po as unknown as PickedPageObject);
      setAnchor(null);
      setQ("");
    },
    [onChange],
  );

  return (
    <Box>
      {value ? (
        /* Selected state */
        <Box
          sx={{
            p: 1.5, borderRadius: 1, border: "1px solid rgba(255,255,255,0.12)",
            bgcolor: "rgba(99,102,241,0.08)", cursor: disabled ? "default" : "pointer",
            display: "flex", alignItems: "center", gap: 1,
          }}
          onClick={disabled ? undefined : () => onChange(null)}
        >
          <PoIcon sx={{ color: "#818cf8", fontSize: 16 }} />
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Typography variant="body2" sx={{ color: "#e2e8f0", fontWeight: 600 }} noWrap>
              {value.name}
            </Typography>
            <Typography variant="caption" sx={{ color: "#94a3b8" }} noWrap>
              {value.application_name} › {value.module_name} › {value.page_name}
            </Typography>
          </Box>
          <Chip label={value.object_type} size="small" sx={{ bgcolor: "rgba(99,102,241,0.2)", color: "#a5b4fc", fontSize: 10 }} />
          {!disabled && (
            <Typography variant="caption" sx={{ color: "#64748b" }}>✕</Typography>
          )}
        </Box>
      ) : (
        /* Search input */
        <>
          <TextField
            size="small"
            fullWidth
            label={label}
            placeholder={placeholder}
            value={q}
            disabled={disabled}
            onChange={(e) => {
              setQ(e.target.value);
              setAnchor(e.currentTarget as HTMLElement);
            }}
            onFocus={(e) => setAnchor(e.currentTarget as HTMLElement)}
            slotProps={{
              input: {
                startAdornment: (
                  <InputAdornment position="start">
                    <SearchIcon sx={{ color: "#64748b", fontSize: 18 }} />
                  </InputAdornment>
                ),
                endAdornment: isFetching ? (
                  <InputAdornment position="end">
                    <CircularProgress size={14} sx={{ color: "#818cf8" }} />
                  </InputAdornment>
                ) : undefined,
              },
            }}
            sx={{
              "& .MuiOutlinedInput-root": {
                background: "rgba(255,255,255,0.04)",
                "& fieldset": { borderColor: "rgba(255,255,255,0.12)" },
                "&:hover fieldset": { borderColor: "#818cf8" },
                "&.Mui-focused fieldset": { borderColor: "#818cf8" },
              },
              "& .MuiInputLabel-root": { color: "#64748b" },
              input: { color: "#e2e8f0" },
            }}
          />

          <Popover
            open={open}
            anchorEl={anchor}
            onClose={() => setAnchor(null)}
            anchorOrigin={{ vertical: "bottom", horizontal: "left" }}
            slotProps={{
              paper: {
                sx: {
                  bgcolor: "#1e1e3a", border: "1px solid rgba(255,255,255,0.1)",
                  borderRadius: 2, mt: 0.5, minWidth: 420, maxHeight: 360, overflowY: "auto",
                },
              },
            }}
          >
            {items.length === 0 && !isFetching && (
              <Box sx={{ p: 2, textAlign: "center" }}>
                <Typography variant="body2" sx={{ color: "#64748b" }}>
                  {q.length < 2 ? "Type at least 2 characters…" : "No results found"}
                </Typography>
              </Box>
            )}
            <List dense disablePadding>
              {items.map((po) => (
                <ListItemButton
                  key={po.id}
                  onClick={() => handleSelect(po)}
                  sx={{
                    py: 1, px: 2, borderBottom: "1px solid rgba(255,255,255,0.04)",
                    "&:hover": { bgcolor: "rgba(99,102,241,0.12)" },
                  }}
                >
                  <Box sx={{ flex: 1, minWidth: 0 }}>
                    {/* Breadcrumb */}
                    <Typography variant="caption" sx={{ color: "#64748b" }} noWrap>
                      {po.application_name} › {po.module_name} › {po.page_name}
                    </Typography>
                    {/* Object name */}
                    <Typography variant="body2" sx={{ color: "#e2e8f0", fontWeight: 600 }} noWrap>
                      {po.name}
                    </Typography>
                  </Box>
                  <Chip
                    label={po.object_type}
                    size="small"
                    sx={{ ml: 1, bgcolor: "rgba(99,102,241,0.2)", color: "#a5b4fc", fontSize: 10 }}
                  />
                </ListItemButton>
              ))}
            </List>
          </Popover>
        </>
      )}
    </Box>
  );
}
