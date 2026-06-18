/**
 * KeywordSearch.tsx — Org-wide PageObject keyword search
 *
 * Debounced input → GET /api/object-repository/objects/search?q=...
 * Results grid: Application/Module/Page breadcrumb + type/status/criticality chips
 * Click row → navigate to ObjectExplorer (future: deep-link to object)
 */

import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  Box, Typography, TextField, InputAdornment, Chip,
  Table, TableHead, TableRow, TableCell, TableBody,
  Skeleton, alpha, IconButton, Tooltip,
} from "@mui/material";
import {
  Search as SearchIcon,
  Clear as ClearIcon,
  ChevronRight as BreadcrumbIcon,
  OpenInNew as OpenIcon,
} from "@mui/icons-material";
import { pageObjectsApi, PageObjectSearchResult } from "../../lib/api/objectRepository";
import { useDebounce } from "../../lib/useDebounce";

const CRITICALITY_COLOR: Record<string, string> = {
  HIGH: "#ef4444", MEDIUM: "#f59e0b", LOW: "#22c55e",
};
const STATUS_COLOR: Record<string, string> = {
  DRAFT: "#6b7280", ACTIVE: "#22c55e", DEPRECATED: "#f59e0b", ARCHIVED: "#6b7280",
};
const TYPE_COLOR = "#818cf8";

function ResultRow({ result }: { result: PageObjectSearchResult }) {
  const navigate = useNavigate();

  return (
    <TableRow
      hover
      sx={{
        cursor: "pointer",
        "&:hover": { bgcolor: "rgba(255,255,255,0.03)" },
        "& td": { borderColor: "rgba(255,255,255,0.04)", py: 1.25 },
      }}
      onClick={() => navigate("/objects")}
    >
      {/* Breadcrumb path */}
      <TableCell>
        <Box sx={{ display: "flex", alignItems: "center", gap: 0.5, mb: 0.5, flexWrap: "wrap" }}>
          <Typography sx={{ fontSize: 10.5, color: "rgba(255,255,255,0.35)" }}>{result.application_name}</Typography>
          <BreadcrumbIcon sx={{ fontSize: 10, color: "rgba(255,255,255,0.2)" }} />
          <Typography sx={{ fontSize: 10.5, color: "rgba(255,255,255,0.35)" }}>{result.module_name}</Typography>
          <BreadcrumbIcon sx={{ fontSize: 10, color: "rgba(255,255,255,0.2)" }} />
          <Typography sx={{ fontSize: 10.5, color: "rgba(255,255,255,0.35)" }}>{result.page_name}</Typography>
        </Box>
        <Typography sx={{ fontSize: 13, fontWeight: 600, color: "#e2e8f0" }}>{result.name}</Typography>
      </TableCell>

      {/* Type */}
      <TableCell>
        <Chip
          label={result.object_type.replace("_", " ")}
          size="small"
          sx={{ fontSize: 10, bgcolor: alpha(TYPE_COLOR, 0.12), color: TYPE_COLOR, border: "none" }}
        />
      </TableCell>

      {/* Criticality */}
      <TableCell>
        <Chip
          label={result.criticality}
          size="small"
          sx={{ fontSize: 10,
                bgcolor: alpha(CRITICALITY_COLOR[result.criticality] || "#818cf8", 0.12),
                color: CRITICALITY_COLOR[result.criticality] || "#818cf8", border: "none" }}
        />
      </TableCell>

      {/* Status */}
      <TableCell>
        <Chip
          label={result.status}
          size="small"
          sx={{ fontSize: 10,
                bgcolor: alpha(STATUS_COLOR[result.status] || "#6b7280", 0.12),
                color: STATUS_COLOR[result.status] || "#6b7280", border: "none" }}
        />
      </TableCell>

      {/* Open */}
      <TableCell align="right">
        <Tooltip title="Open in Explorer">
          <IconButton size="small" sx={{ color: "rgba(255,255,255,0.2)", "&:hover": { color: "#818cf8" } }}>
            <OpenIcon sx={{ fontSize: 14 }} />
          </IconButton>
        </Tooltip>
      </TableCell>
    </TableRow>
  );
}

export default function KeywordSearch() {
  const [query, setQuery] = useState("");
  const debouncedQ = useDebounce(query, 350);

  const { data, isLoading, isFetching } = useQuery({
    queryKey: ["objectSearch", debouncedQ],
    queryFn: () => pageObjectsApi.search(debouncedQ, { limit: 50 }),
    enabled: debouncedQ.trim().length >= 1,
  });

  const loading = isLoading || isFetching;

  return (
    <Box sx={{ maxWidth: 1000, mx: "auto" }}>
      {/* Page header */}
      <Box sx={{ mb: 3 }}>
        <Typography sx={{ fontSize: 22, fontWeight: 700, color: "#e2e8f0", mb: 0.5 }}>
          Object Search
        </Typography>
        <Typography sx={{ fontSize: 13, color: "rgba(255,255,255,0.4)" }}>
          Search PageObjects by name or keyword across the entire repository.
        </Typography>
      </Box>

      {/* Search input */}
      <TextField
        fullWidth
        size="medium"
        autoFocus
        placeholder="Search by name or keyword…  e.g. Login, Username Field, Submit"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        slotProps={{
          input: {
            startAdornment: (
              <InputAdornment position="start">
                <SearchIcon sx={{ color: "rgba(255,255,255,0.3)", fontSize: 20 }} />
              </InputAdornment>
            ),
            endAdornment: query && (
              <InputAdornment position="end">
                <IconButton size="small" onClick={() => setQuery("")}
                  sx={{ color: "rgba(255,255,255,0.3)", "&:hover": { color: "#e2e8f0" } }}>
                  <ClearIcon fontSize="small" />
                </IconButton>
              </InputAdornment>
            ),
          },
        }}
        sx={{
          mb: 3,
          "& .MuiOutlinedInput-root": {
            fontSize: 14,
            background: "rgba(255,255,255,0.03)",
            borderRadius: 2,
            "& fieldset": { borderColor: "rgba(255,255,255,0.1)" },
            "&:hover fieldset": { borderColor: "rgba(255,255,255,0.2)" },
            "&.Mui-focused fieldset": { borderColor: "#667eea" },
          },
        }}
      />

      {/* Results */}
      {debouncedQ.trim().length < 1 ? (
        <Box sx={{ textAlign: "center", py: 6 }}>
          <SearchIcon sx={{ fontSize: 56, color: "rgba(255,255,255,0.06)", mb: 1.5 }} />
          <Typography sx={{ fontSize: 14, color: "rgba(255,255,255,0.25)" }}>
            Type at least 1 character to search
          </Typography>
        </Box>
      ) : loading ? (
        <Box>
          {[1, 2, 3, 4].map((i) => (
            <Skeleton key={i} height={56} sx={{ borderRadius: 1.5, mb: 0.75 }} />
          ))}
        </Box>
      ) : !data?.items.length ? (
        <Box sx={{ textAlign: "center", py: 6 }}>
          <Typography sx={{ fontSize: 14, color: "rgba(255,255,255,0.3)" }}>
            No objects found for <strong style={{ color: "#e2e8f0" }}>"{debouncedQ}"</strong>
          </Typography>
          <Typography sx={{ fontSize: 12, color: "rgba(255,255,255,0.2)", mt: 0.5 }}>
            Try a different keyword or check spelling
          </Typography>
        </Box>
      ) : (
        <>
          <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", mb: 1.5 }}>
            <Typography sx={{ fontSize: 12, color: "rgba(255,255,255,0.4)" }}>
              {data.total} result{data.total !== 1 ? "s" : ""} for{" "}
              <strong style={{ color: "#818cf8" }}>"{debouncedQ}"</strong>
            </Typography>
          </Box>

          <Box sx={{ border: "1px solid rgba(255,255,255,0.06)", borderRadius: 2, overflow: "hidden" }}>
            <Table size="small">
              <TableHead>
                <TableRow sx={{ "& th": { borderColor: "rgba(255,255,255,0.06)",
                                          bgcolor: "rgba(255,255,255,0.02)",
                                          fontSize: 10, fontWeight: 600,
                                          color: "rgba(255,255,255,0.35)",
                                          textTransform: "uppercase", letterSpacing: 0.8, py: 1 } }}>
                  <TableCell>Object / Path</TableCell>
                  <TableCell>Type</TableCell>
                  <TableCell>Criticality</TableCell>
                  <TableCell>Status</TableCell>
                  <TableCell />
                </TableRow>
              </TableHead>
              <TableBody>
                {data.items.map((r) => <ResultRow key={r.id} result={r} />)}
              </TableBody>
            </Table>
          </Box>
        </>
      )}
    </Box>
  );
}
