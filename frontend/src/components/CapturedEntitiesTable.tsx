"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import AppShell from "./AppShell";
import PageContainer from "./PageContainer";
import PageHeader from "./PageHeader";
import ContentCard from "./ContentCard";
import { apiGet } from "../lib/api";

type Workspace = "capture" | "discovery" | "summaries";

type CapturedEntitiesResponse = {
  headers: string[];
  rows: Record<string, string>[];
};

type ProtocolField = {
  section?: string;
  data_element?: string;
  label?: string;
  name?: string;
  format?: string;
  notes?: string;
};

type ProtocolColumn = {
  header: string;
  group: string;
};

type ProtocolResponse = {
  has_protocol?: boolean;
  fields?: ProtocolField[];
  protocol?: {
    fields?: ProtocolField[];
  };
};

type SortDirection = "asc" | "desc";

type SortState = {
  header: string;
  direction: SortDirection;
} | null;

type CapturedEntitiesTableProps = {
  workspace: Workspace;
  title?: string;
  subtitlePrefix?: string;
};

function normalizeHeader(value: string) {
  return value.trim();
}

function uniqueHeaders(headers: string[]) {
  const seen = new Set<string>();
  const output: string[] = [];

  headers.forEach((header) => {
    const clean = normalizeHeader(header);

    if (!clean || seen.has(clean)) {
      return;
    }

    seen.add(clean);
    output.push(clean);
  });

  return output;
}

function getProtocolFields(response: ProtocolResponse): ProtocolField[] {
  return response.fields || response.protocol?.fields || [];
}

function getProtocolColumns(response: ProtocolResponse): ProtocolColumn[] {
  const fields = getProtocolFields(response);

  return fields
    .map((field) => {
      const header =
        field.data_element ||
        field.label ||
        field.name ||
        "";

      return {
        header: normalizeHeader(header),
        group: normalizeHeader(field.section || "Protocol"),
      };
    })
    .filter((column) => column.header);
}

function splitFinalDocIds(value: any): string[] {
  if (Array.isArray(value)) {
    return value
      .map((item) => String(item || "").trim())
      .filter(Boolean);
  }

  return String(value || "")
    .split(";")
    .map((item) => item.trim())
    .filter(Boolean);
}

function getCellValue(row: Record<string, any>, header: string) {
  return String(row?.[header] ?? "");
}

function compareValues(a: string, b: string) {
  const cleanA = a.trim();
  const cleanB = b.trim();

  const numberA = Number(cleanA);
  const numberB = Number(cleanB);

  if (
    cleanA !== "" &&
    cleanB !== "" &&
    !Number.isNaN(numberA) &&
    !Number.isNaN(numberB)
  ) {
    return numberA - numberB;
  }

  return cleanA.localeCompare(cleanB, undefined, {
    numeric: true,
    sensitivity: "base",
  });
}

function buildReviewHref(
  workspace: Workspace,
  clientId: string,
  projectId: string,
  batchId: string,
  docId: string
) {
  const params = new URLSearchParams();

  if (clientId) params.set("client", clientId);
  if (projectId) params.set("project", projectId);
  if (batchId) params.set("batch", batchId);
  if (docId) params.set("doc", docId);

  return `/${workspace}/review/doc?${params.toString()}`;
}

function normalizeHeaderName(header: string) {
  return String(header || "")
    .trim()
    .toLowerCase()
    .replace(/[_\s-]+/g, " ");
}

function shouldShowColumnCheckboxFilter(header: string) {
  const clean = normalizeHeaderName(header);

  const alwaysAllow = [
    "state",
    "states",
    "minor",
    "minors",
    "data element",
    "element",
    "category",
    "type",
    "source",
    "coding",
    "review status",
    "capture status",
    "confidence",
    "confidence band",
    "country",
    "province",
    "pii type",
    "phi type",
    "hipaa",
    "gdpr",
    "ferpa",
    "partial ssn",
    "partial ssn?",
  ];

  if (alwaysAllow.includes(clean)) return true;

  const alwaysBlock = [
    "first",
    "first name",
    "middle",
    "middle name",
    "last",
    "last name",
    "full name",
    "name",
    "street",
    "street address",
    "address",
    "address 1",
    "address 2",
    "city",
    "zip",
    "zip code",
    "postal code",
    "email",
    "email address",
    "phone",
    "phone number",
    "ssn",
    "social security number",
    "dob",
    "date of birth",
    "uid",
    "uids",
    "ucid",
    "insyt uid",
    "entity uid",
    "final entity uid",
    "doc id",
    "doc_id",
    "document id",
    "file name",
    "filename",
    "path",
    "native path",
    "source path",
  ];

  if (alwaysBlock.includes(clean)) return false;

  return false;
}

function normalizeFilterValue(value: any) {
  const clean = String(value ?? "").trim();

  return clean || "(Blank)";
}

function getUniqueColumnValues(
  rows: Record<string, any>[],
  header: string
) {
  const values = rows.map((row) =>
    normalizeFilterValue(getCellValue(row, header))
  );

  return Array.from(new Set(values)).sort((a, b) =>
    a.localeCompare(b, undefined, {
      numeric: true,
      sensitivity: "base",
    })
  );
}

function shouldRenderColumnValueFilter(
  rows: Record<string, any>[],
  header: string
) {
  if (!shouldShowColumnCheckboxFilter(header)) return false;

  const uniqueValues = getUniqueColumnValues(rows, header);

  return uniqueValues.length > 0 && uniqueValues.length <= 150;
}

export default function CapturedEntitiesTable({
  workspace,
  title = "Captured Entities",
  subtitlePrefix = "Protocol-aligned captured entities",
}: CapturedEntitiesTableProps) {
  const searchParams = useSearchParams();
  const router = useRouter();

  const clientId = searchParams.get("client") || "";
  const projectId = searchParams.get("project") || "";
  const batchId = searchParams.get("batch") || "";

  const initialView =
    searchParams.get("view") === "final" ? "final" : "raw";

  const [entityView, setEntityView] =
    useState<"raw" | "final">(initialView);

  const [entityData, setEntityData] =
    useState<CapturedEntitiesResponse>({
      headers: [],
      rows: [],
    });

  const [protocolColumns, setProtocolColumns] =
    useState<ProtocolColumn[]>([]);

  const [message, setMessage] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  const [columnFilters, setColumnFilters] =
    useState<Record<string, string>>({});

  const [columnValueFilters, setColumnValueFilters] =
    useState<Record<string, string[]>>({});

  const [pendingColumnValueFilters, setPendingColumnValueFilters] =
    useState<Record<string, string[]>>({});

  const [sortState, setSortState] =
    useState<SortState>(null);

  const [selectedExportRows, setSelectedExportRows] =
    useState<Record<string, boolean>>({});

  const [isExporting, setIsExporting] = useState(false);

  useEffect(() => {
    if (!projectId) return;

    setIsLoading(true);
    setMessage("");
    setColumnFilters({});
    setColumnValueFilters({});
    setPendingColumnValueFilters({});
    setSelectedExportRows({});
    setSortState(null);
    setProtocolColumns([]);
    setEntityData({
      headers: [],
      rows: [],
    });

    const protocolUrl =
      `/api/${workspace}/projects/${encodeURIComponent(
        projectId
      )}/protocol` +
      (clientId
        ? `?client=${encodeURIComponent(clientId)}`
        : "");

    apiGet(protocolUrl)
      .then((response: ProtocolResponse) => {
        setProtocolColumns(getProtocolColumns(response));
      })
      .catch((error) => {
        console.error(error);
        setMessage("Protocol headers could not be loaded.");
      });

    const batchQuery = batchId
      ? `&batch=${encodeURIComponent(batchId)}`
      : "";

    const clientQuery = clientId
      ? `client=${encodeURIComponent(clientId)}&`
      : "";

    const entitiesUrl =
      `/api/entities/?${clientQuery}workspace=${encodeURIComponent(
        workspace
      )}&project=${encodeURIComponent(
        projectId
      )}&view=${encodeURIComponent(
        entityView
      )}${batchQuery}`;

    const overlayUrl =
      `/api/document-overlays/${encodeURIComponent(
        projectId
      )}/latest?workspace=${encodeURIComponent(
        workspace
      )}&client=${encodeURIComponent(
        clientId
      )}&overlay_view=${encodeURIComponent(entityView)}`;

    Promise.allSettled([
      apiGet(entitiesUrl),
      apiGet(overlayUrl),
    ])
      .then(([entitiesResult, overlayResult]) => {
        let headers: string[] = [];
        let rows: Record<string, string>[] = [];

        if (entitiesResult.status === "fulfilled") {
          const response =
            entitiesResult.value as CapturedEntitiesResponse;

          headers = response.headers || [];
          rows = response.rows || [];
        }

        if (overlayResult.status === "fulfilled") {
          const overlay = overlayResult.value as any;

          const overlayHeaders =
            overlay.committed_headers ||
            overlay.headers ||
            [];

          const overlayRows = (overlay.records || []).map(
            (record: any) => ({
              "Doc ID": record.doc_id,
              doc_ids: record.doc_ids || [],
              final_entity_id: record.final_entity_id || "",
              ...(record.metadata || {}),
            })
          );

          headers = uniqueHeaders([
            ...headers,
            "Doc ID",
            ...overlayHeaders,
          ]);

          rows =
            entityView === "final"
              ? overlayRows
              : [...rows, ...overlayRows];
        }

        if (
          entitiesResult.status === "rejected" &&
          overlayResult.status === "rejected"
        ) {
          console.error(entitiesResult.reason);
          console.error(overlayResult.reason);
          setMessage("Captured entities could not be loaded.");
        } else if (entitiesResult.status === "rejected") {
          console.error(entitiesResult.reason);
          setMessage("Manual captured entities could not be loaded. Showing latest overlay data.");
        }

        setEntityData({
          headers,
          rows,
        });
      })
      .finally(() => {
        setIsLoading(false);
      });
    
  }, [workspace, clientId, projectId, batchId, entityView]);

  const headers = useMemo(() => {
    return uniqueHeaders([
      "Doc ID",
      ...protocolColumns.map((column) => column.header),
      ...entityData.headers,
    ]);
  }, [protocolColumns, entityData.headers]);

  const visibleRows = useMemo(() => {
    const filteredRows = entityData.rows.filter((row) => {
      const matchesTextFilters = headers.every((header) => {
        const filterValue = columnFilters[header];

        if (!filterValue) {
          return true;
        }

        const cellValue = getCellValue(row, header).toLowerCase();

        return cellValue.includes(filterValue.toLowerCase());
      });

      if (!matchesTextFilters) return false;

      return Object.entries(columnValueFilters).every(
        ([header, selectedValues]) => {
          if (!selectedValues || selectedValues.length === 0) {
            return true;
          }

          const rowValue = normalizeFilterValue(
            getCellValue(row, header)
          );

          return selectedValues.includes(rowValue);
        }
      );
    });

    if (!sortState) {
      return filteredRows;
    }

    return [...filteredRows].sort((a, b) => {
      const aValue = getCellValue(a, sortState.header);
      const bValue = getCellValue(b, sortState.header);

      const result = compareValues(aValue, bValue);

      return sortState.direction === "asc" ? result : -result;
    });
  }, [
    entityData.rows,
    headers,
    columnFilters,
    columnValueFilters,
    sortState,
  ]);

  const headerGroups = useMemo(() => {
    const groupByHeader = new Map<string, string>();

    groupByHeader.set("Doc ID", "Document");

    protocolColumns.forEach((column) => {
      groupByHeader.set(column.header, column.group);
    });

    entityData.headers.forEach((header) => {
      if (!groupByHeader.has(header)) {
        groupByHeader.set(header, "Captured Data");
      }
    });

    const groups: { label: string; span: number }[] = [];

    headers.forEach((header) => {
      const label = groupByHeader.get(header) || "Captured Data";
      const last = groups[groups.length - 1];

      if (last && last.label === label) {
        last.span += 1;
      } else {
        groups.push({
          label,
          span: 1,
        });
      }
    });

    return groups;
  }, [headers, protocolColumns, entityData.headers]);

  function toggleSort(header: string) {
    setSortState((current) => {
      if (!current || current.header !== header) {
        return {
          header,
          direction: "asc",
        };
      }

      if (current.direction === "asc") {
        return {
          header,
          direction: "desc",
        };
      }

      return null;
    });
  }

function getPendingColumnValues(header: string) {
  return pendingColumnValueFilters[header] ?? columnValueFilters[header] ?? [];
}

function isPendingColumnValueSelected(header: string, value: string) {
  return Boolean(getPendingColumnValues(header).includes(value));
}

function togglePendingColumnValueFilter(header: string, value: string) {
  setPendingColumnValueFilters((current) => {
    const existing =
      current[header] ?? columnValueFilters[header] ?? [];

    const nextValues = existing.includes(value)
      ? existing.filter((item) => item !== value)
      : [...existing, value];

    const next = {
      ...current,
      [header]: nextValues,
    };

    if (nextValues.length === 0) {
      delete next[header];
    }

    return next;
  });
}

function applyColumnValueFilter(header: string) {
  setColumnValueFilters((current) => {
    const selectedValues =
      pendingColumnValueFilters[header] ??
      columnValueFilters[header] ??
      [];

    const next = {
      ...current,
      [header]: selectedValues,
    };

    if (selectedValues.length === 0) {
      delete next[header];
    }

    return next;
  });

  setPendingColumnValueFilters((current) => {
    const next = { ...current };
    delete next[header];
    return next;
  });
}

function clearColumnValueFilter(header: string) {
  setColumnValueFilters((current) => {
    const next = { ...current };
    delete next[header];
    return next;
  });

  setPendingColumnValueFilters((current) => {
    const next = { ...current };
    delete next[header];
    return next;
  });
}

function resetPendingColumnValueFilter(header: string) {
  setPendingColumnValueFilters((current) => {
    const next = { ...current };
    next[header] = columnValueFilters[header] || [];
    return next;
  });
}

function clearAllColumnValueFilters() {
  setColumnFilters({});
  setColumnValueFilters({});
  setPendingColumnValueFilters({});
}

  function openDocument(docId: string) {
    if (!docId) return;

    router.push(
      buildReviewHref(
        workspace,
        clientId,
        projectId,
        "",
        docId
      )
    );
  }

  function getFinalEntityDisplayName(row: Record<string, any>) {
  return (
    row["Full Name"] ||
    row["Entity Name"] ||
    row["Name"] ||
    [
      row["First Name"],
      row["First Name\n(or Initial)"],
      row["Middle Name"],
      row["Middle(or Initial) - If Present"],
      row["Last Name"],
      row["Last Name (FULL)"],
    ]
      .map((item) => String(item || "").trim())
      .filter(Boolean)
      .join(" ")
  );
}

function getRowExportKey(row: Record<string, any>, index: number) {
  const docIds = getExportDocIdsFromRow(row);

  return docIds.length > 0
    ? docIds.join("|")
    : `row-${index}`;
}

function getExportDocIdsFromRow(row: Record<string, any>) {
  return splitFinalDocIds(
    row.doc_ids?.length > 0
      ? row.doc_ids
      : row["Doc ID"]
  );
}

function getUniqueDocIdsForRows(rows: Record<string, any>[]) {
  return Array.from(
    new Set(
      rows
        .flatMap((row) => getExportDocIdsFromRow(row))
        .map((docId) => String(docId || "").trim())
        .filter(Boolean)
    )
  );
}

function getSelectedExportRows() {
  return visibleRows.filter((row, index) => {
    const key = getRowExportKey(row, index);
    return Boolean(selectedExportRows[key]);
  });
}

function toggleExportRow(row: Record<string, any>, index: number) {
  const key = getRowExportKey(row, index);

  setSelectedExportRows((current) => ({
    ...current,
    [key]: !current[key],
  }));
}

function selectAllVisibleExportRows() {
  const next: Record<string, boolean> = {};

  visibleRows.forEach((row, index) => {
    const key = getRowExportKey(row, index);
    next[key] = true;
  });

  setSelectedExportRows(next);
}

function clearSelectedExportRows() {
  setSelectedExportRows({});
}

function buildZipLabelFromFilters() {
  const parts: string[] = [];

  Object.entries(columnValueFilters).forEach(([header, values]) => {
    values.forEach((value) => {
      parts.push(String(value || "").trim());
    });
  });

  Object.entries(columnFilters).forEach(([header, value]) => {
    const cleanValue = String(value || "").trim();

    if (cleanValue) {
      parts.push(`${header}_${cleanValue}`);
    }
  });

  const cleanLabel = parts
    .filter(Boolean)
    .join("_")
    .replace(/[^a-zA-Z0-9_-]+/g, "_")
    .replace(/_+/g, "_")
    .replace(/^_+|_+$/g, "")
    .slice(0, 80);

  return cleanLabel || "Filtered_Source_Documents";
}

async function exportSourceDocsZip(
  mode: "selected" | "all_filtered"
) {
  const rowsToExport =
    mode === "selected"
      ? getSelectedExportRows()
      : visibleRows;

  const docIds = getUniqueDocIdsForRows(rowsToExport);

  if (docIds.length === 0) {
    setMessage("No source Doc IDs were found for the current export selection.");
    return;
  }

  setIsExporting(true);
  setMessage("");

  try {
    const token = localStorage.getItem("insyt_token");
    const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL || "";

    const response = await fetch(
      `${apiBase}/api/entities/export-source-docs-zip`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          workspace,
          client: clientId,
          project: projectId,
          doc_ids: docIds,
          zip_label: buildZipLabelFromFilters(),
        }),
      }
    );

    if (!response.ok) {
      const text = await response.text();
      throw new Error(`ZIP export failed ${response.status}: ${text}`);
    }

    const blob = await response.blob();
    const downloadUrl = window.URL.createObjectURL(blob);

    const contentDisposition =
      response.headers.get("Content-Disposition") || "";

    const filenameMatch = contentDisposition.match(/filename="(.+)"/);

    const filename =
      filenameMatch?.[1] || `${buildZipLabelFromFilters()}.zip`;

    const link = document.createElement("a");
    link.href = downloadUrl;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();

    window.URL.revokeObjectURL(downloadUrl);

    setMessage(`ZIP export created for ${docIds.length} source document(s).`);
  } catch (error) {
    console.error(error);
    setMessage("Failed to export source documents ZIP.");
  } finally {
    setIsExporting(false);
  }
}

function getFinalEntityUid(row: Record<string, any>) {
  return (
    row["INSYT UID"] ||
    row["Insyt UID"] ||
    row["insyt_uid"] ||
    row["UCID"] ||
    row["ucid"] ||
    row["CDS ID"] ||
    row["CDS Raw ID"] ||
    row.final_entity_id ||
    ""
  );
}

function openFinalSourceDocs(row: Record<string, any>) {
  const docIds = splitFinalDocIds(
    row.doc_ids?.length > 0
      ? row.doc_ids
      : row["Doc ID"]
  );

  if (docIds.length === 0) {
    setMessage("No source Doc IDs were found for this Final entity.");
    return;
  }

  const capturedEntity = getFinalEntityDisplayName(row);
  const entityUid = getFinalEntityUid(row);

  const params = new URLSearchParams();

  if (clientId) params.set("client", clientId);
  if (projectId) params.set("project", projectId);
  if (capturedEntity) params.set("entity", capturedEntity);
  if (entityUid) params.set("entityUid", entityUid);

  params.set("docIds", docIds.join(";"));
  params.set("startDoc", docIds[0]);
  params.set("source", "final");

  router.push(`/${workspace}/entities/final-viewer?${params.toString()}`);
}

  if (!projectId) {
    return (
      <AppShell>
        <PageContainer>
          <PageHeader
            title="No Project Selected"
            subtitle="Return to Projects and select a project first."
          />
        </PageContainer>
      </AppShell>
    );
  }

  return (
    <AppShell>
      <PageContainer>
        <PageHeader
          title={title}
          subtitle={`${subtitlePrefix} for ${projectId.replaceAll(
            "_",
            " "
          )}${batchId ? ` / ${batchId.replaceAll("_", " ")}` : ""}.`}
        />

        {message && (
          <p className="text-sm text-amber-300 mb-6">
            {message}
          </p>
        )}

        <ContentCard title="Captured Entity Table">
          <div className="mb-4 flex flex-col md:flex-row md:items-center md:justify-between gap-3">
            <p className="text-sm text-slate-400">
              Headers are loaded from the saved project protocol before captured rows are available.
            </p>

            <p className="text-xs text-slate-500">
              Rows: {visibleRows.length} of {entityData.rows.length} | Selected: {getSelectedExportRows().length} | Headers: {headers.length}
            </p>
          </div>

          <div className="flex flex-wrap gap-2 mb-4">
            <button
              type="button"
              onClick={() => setEntityView("raw")}
              className={
                entityView === "raw"
                  ? "rounded-lg bg-sky-600 px-4 py-2 text-sm font-semibold text-white"
                  : "rounded-lg bg-slate-800 px-4 py-2 text-sm font-semibold text-slate-300 hover:bg-slate-700"
              }
            >
              Raw
            </button>

            <button
              type="button"
              onClick={() => setEntityView("final")}
              className={
                entityView === "final"
                  ? "rounded-lg bg-sky-600 px-4 py-2 text-sm font-semibold text-white"
                  : "rounded-lg bg-slate-800 px-4 py-2 text-sm font-semibold text-slate-300 hover:bg-slate-700"
              }
            >
              Final
            </button>

            <button
              type="button"
              onClick={clearAllColumnValueFilters}
              className="rounded-lg bg-slate-800 px-4 py-2 text-sm font-semibold text-slate-300 hover:bg-slate-700"
            >
              Clear Filters
            </button>

            <button
              type="button"
              onClick={selectAllVisibleExportRows}
              className="rounded-lg bg-slate-800 px-4 py-2 text-sm font-semibold text-slate-300 hover:bg-slate-700"
            >
              Select Visible
            </button>

            <button
              type="button"
              onClick={clearSelectedExportRows}
              className="rounded-lg bg-slate-800 px-4 py-2 text-sm font-semibold text-slate-300 hover:bg-slate-700"
            >
              Clear Selected
            </button>

            <button
              type="button"
              onClick={() => exportSourceDocsZip("selected")}
              disabled={isExporting || getSelectedExportRows().length === 0}
              className="rounded-lg bg-emerald-700 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-600 disabled:cursor-not-allowed disabled:opacity-50"
            >
              Export Selected
            </button>

            <button
              type="button"
              onClick={() => exportSourceDocsZip("all_filtered")}
              disabled={isExporting || visibleRows.length === 0}
              className="rounded-lg bg-sky-700 px-4 py-2 text-sm font-semibold text-white hover:bg-sky-600 disabled:cursor-not-allowed disabled:opacity-50"
            >
              Export All Filtered
            </button>

          </div>

          <div className="bg-slate-950 border border-slate-800 rounded-xl overflow-auto max-h-[70vh]">
            <table className="min-w-max w-full text-xs">
              <thead className="bg-slate-900 text-slate-400">
                <tr>
                  <th className="sticky left-0 top-0 z-[70] w-[72px] min-w-[72px] bg-slate-900 p-3 text-left whitespace-nowrap border-b border-r border-slate-800 text-sky-300">
                    Export
                  </th>

                  {headerGroups.map((group, index) => (
                    <th
                      key={`${group.label}-${index}`}
                      colSpan={group.span}
                      className={
                        index === 0
                          ? "sticky left-[72px] top-0 z-[60] w-[220px] min-w-[220px] bg-slate-900 p-3 text-left border-l border-r border-b border-slate-800 whitespace-nowrap text-sky-300"
                          : "sticky top-0 z-40 bg-slate-900 p-3 text-left border-l border-b border-slate-800 whitespace-nowrap text-sky-300"
                      }
                    >
                      {group.label}
                    </th>
                  ))}
                </tr>

                <tr>
                  <th className="sticky left-0 top-[42px] z-[70] w-[72px] min-w-[72px] bg-slate-900 p-3 text-left whitespace-nowrap border-b border-r border-slate-800 text-slate-300">
                    Select
                  </th>

                  {headers.map((header) => {
                    const isSorted = sortState?.header === header;

                    return (
                      <th
                        key={header}
                        className={
                          header === "Doc ID"
                            ? "sticky left-[72px] top-[42px] z-[60] w-[220px] min-w-[220px] bg-slate-900 p-3 text-left border-l border-r border-slate-800 whitespace-nowrap"
                            : "sticky top-[42px] z-40 bg-slate-900 p-3 text-left border-l border-slate-800 whitespace-nowrap"
                        }
                      >
                        <div className="flex items-start justify-between gap-2">
                          <button
                            type="button"
                            onClick={() => toggleSort(header)}
                            className="flex items-center gap-1 text-left hover:text-sky-300"
                            title={`Sort by ${header}`}
                          >
                            <span>{header}</span>
                            <span className="text-[10px] text-slate-500">
                              {isSorted
                                ? sortState?.direction === "asc"
                                  ? "▲"
                                  : "▼"
                                : "↕"}
                            </span>
                          </button>

                          {shouldRenderColumnValueFilter(entityData.rows, header) && (
                            <details className="relative">
                              <summary className="cursor-pointer list-none rounded-md border border-slate-700 px-2 py-1 text-[10px] text-slate-300 hover:bg-slate-800">
                                Filter
                                {columnValueFilters[header]?.length ? (
                                  <span className="ml-1 text-sky-300">
                                    ({columnValueFilters[header].length})
                                  </span>
                                ) : null}
                              </summary>

                              <div className="absolute right-0 z-[90] mt-2 max-h-72 w-72 overflow-auto rounded-xl border border-slate-700 bg-slate-950 p-3 shadow-2xl">
                                <div className="mb-3 space-y-2">
                                  <div className="flex items-center justify-between gap-2">
                                    <span className="text-xs font-semibold text-white">
                                      {header}
                                    </span>

                                    <span className="text-[10px] text-slate-500">
                                      {getPendingColumnValues(header).length} selected
                                    </span>
                                  </div>

                                  <div className="flex items-center gap-2">
                                    <button
                                      type="button"
                                      onClick={() => applyColumnValueFilter(header)}
                                      className="rounded-md bg-sky-600 px-3 py-1 text-xs font-semibold text-white hover:bg-sky-500"
                                    >
                                      Go
                                    </button>

                                    <button
                                      type="button"
                                      onClick={() => clearColumnValueFilter(header)}
                                      className="rounded-md border border-slate-700 px-3 py-1 text-xs text-slate-300 hover:bg-slate-800"
                                    >
                                      Clear
                                    </button>

                                    <button
                                      type="button"
                                      onClick={() => resetPendingColumnValueFilter(header)}
                                      className="rounded-md border border-slate-700 px-3 py-1 text-xs text-slate-300 hover:bg-slate-800"
                                    >
                                      Reset
                                    </button>
                                  </div>
                                </div>

                                <div className="space-y-2">
                                  {getUniqueColumnValues(entityData.rows, header).map(
                                    (value) => (
                                      <label
                                        key={`${header}-${value}`}
                                        className="flex items-center gap-2 text-xs text-slate-300"
                                      >
                                        <input
                                          type="checkbox"
                                          checked={isPendingColumnValueSelected(
                                            header,
                                            value
                                          )}
                                          onChange={() =>
                                            togglePendingColumnValueFilter(header, value)
                                          }
                                        />

                                        <span className="truncate" title={value}>
                                          {value}
                                        </span>
                                      </label>
                                    )
                                  )}
                                </div>
                              </div>
                            </details>
                          )}
                        </div>
                      </th>
                    );
                  })}
                </tr>

                <tr>
                  <th className="sticky left-0 top-[90px] z-[70] w-[72px] min-w-[72px] bg-slate-900 p-2 whitespace-nowrap border-r border-slate-800">
                    <span className="sr-only">Export selection filter spacer</span>
                  </th>

                  {headers.map((header) => (
                    <th
                      key={`${header}-filter`}
                      className={
                        header === "Doc ID"
                          ? "sticky left-[72px] top-[90px] z-[60] w-[220px] min-w-[220px] bg-slate-900 p-2 border-l border-r border-slate-800 whitespace-nowrap"
                          : "sticky top-[90px] z-40 bg-slate-900 p-2 border-l border-slate-800 whitespace-nowrap"
                      }
                    >
                      <input
                        value={columnFilters[header] || ""}
                        onChange={(event) =>
                          setColumnFilters((current) => ({
                            ...current,
                            [header]: event.target.value,
                          }))
                        }
                        placeholder="Search..."
                        className="w-full min-w-[120px] rounded-md border border-slate-700 bg-slate-950 px-2 py-1 text-[11px] text-slate-100 placeholder:text-slate-600"
                      />
                    </th>
                  ))}
                </tr>
              </thead>

              <tbody>
                {visibleRows.length === 0 ? (
                  <tr>
                    <td
                      colSpan={Math.max(headers.length + 1, 1)}
                      className="p-6 text-slate-500"
                    >
                      {isLoading
                        ? "Loading captured entities..."
                        : entityData.rows.length === 0
                          ? "No captured entities found yet. Protocol headers are ready for incoming review data."
                          : "No rows match the current filters."}
                    </td>
                  </tr>
                ) : (
                  visibleRows.map((row, rowIndex) => (
                    <tr
                      key={rowIndex}
                      className="border-t border-slate-800"
                    >
                      <td className="sticky left-0 z-30 w-[72px] min-w-[72px] bg-slate-950 p-3 whitespace-nowrap border-r border-slate-800">
                        <input
                          type="checkbox"
                          checked={Boolean(
                            selectedExportRows[getRowExportKey(row, rowIndex)]
                          )}
                          onChange={() => toggleExportRow(row, rowIndex)}
                          className="h-4 w-4 rounded border-slate-600 bg-slate-950"
                        />
                      </td>

                      {headers.map((header, index) => {
                        const value = row[header] || "";

                        if (header === "Doc ID") {
                          const finalDocIds = splitFinalDocIds(
                            row.doc_ids?.length > 0
                              ? row.doc_ids
                              : value
                          );

                          const displayValue =
                            entityView === "final" && finalDocIds.length > 0
                              ? finalDocIds.join("; ")
                              : value || "Open Doc";

                          return (
                            <td
                              key={header}
                              className="sticky left-[72px] z-20 w-[220px] min-w-[220px] bg-slate-950 p-3 whitespace-nowrap border-r border-slate-800"
                            >
                              <button
                                className="text-sky-400 hover:text-sky-300 underline"
                                onClick={() =>
                                  entityView === "final"
                                    ? openFinalSourceDocs(row)
                                    : openDocument(value)
                                }
                                title={
                                  entityView === "final"
                                    ? finalDocIds.join("; ")
                                    : value
                                }
                              >
                                {displayValue || "Open Doc"}
                              </button>
                            </td>
                          );
                        }

                        return (
                          <td
                            key={header}
                            className="p-3 text-slate-300 border-l border-slate-800 whitespace-nowrap"
                          >
                            {value}
                          </td>
                        );
                      })}
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </ContentCard>
      </PageContainer>
    </AppShell>
  );
}