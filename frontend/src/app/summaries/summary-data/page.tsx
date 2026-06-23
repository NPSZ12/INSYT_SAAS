"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";

import AppShell from "../../../components/AppShell";
import PageContainer from "../../../components/PageContainer";
import PageHeader from "../../../components/PageHeader";
import ContentCard from "../../../components/ContentCard";
import { apiGet } from "../../../lib/api";

type SummaryDataRow = {
  pdf_name: string;
  batch_id?: string;
  summary_doc_id?: string;
  summary_key?: string;
  title: string;
  citation: string;
  original_summary: string;
  qc_summary: string;
  last_modified: string;
  source?: string;
};

type SortDirection = "asc" | "desc";

type SortState = {
  key: keyof SummaryDataRow;
  direction: SortDirection;
} | null;

type DraftFilters = {
  pdf_name: string[];
  batch_id: string[];
  source: string[];
  title: string;
  citation: string;
  original_summary: string;
  qc_summary: string;
  last_modified: string;
};

function SummaryDataPageContent() {
  const searchParams = useSearchParams();

  const clientId = searchParams.get("client") || "";
  const projectId = searchParams.get("project") || "";

  const [rows, setRows] = useState<SummaryDataRow[]>([]);
  const [message, setMessage] = useState("");

  const emptyFilters: DraftFilters = {
    pdf_name: [],
    batch_id: [],
    source: [],
    title: "",
    citation: "",
    original_summary: "",
    qc_summary: "",
    last_modified: "",
  };

  const [sortState, setSortState] = useState<SortState>(null);
  const [draftFilters, setDraftFilters] = useState<DraftFilters>(emptyFilters);
  const [appliedFilters, setAppliedFilters] = useState<DraftFilters>(emptyFilters);
  const [openFilterKey, setOpenFilterKey] = useState<keyof DraftFilters | "">("");

  function cleanValue(value: unknown) {
    return String(value ?? "").trim();
  }

  function getUniqueValues(key: keyof SummaryDataRow) {
    const values = rows
      .map((row) => cleanValue(row[key]))
      .filter(Boolean);

    return Array.from(new Set(values)).sort((a, b) =>
      a.localeCompare(b, undefined, {
        numeric: true,
        sensitivity: "base",
      })
    );
  }

  function toggleDraftCheckbox(
    key: "pdf_name" | "batch_id" | "source",
    value: string
  ) {
    setDraftFilters((current) => {
      const existing = current[key] || [];
      const nextValues = existing.includes(value)
        ? existing.filter((item) => item !== value)
        : [...existing, value];

      return {
        ...current,
        [key]: nextValues,
      };
    });
  }

  function updateDraftSearch(
    key:
      | "title"
      | "citation"
      | "original_summary"
      | "qc_summary"
      | "last_modified",
    value: string
  ) {
    setDraftFilters((current) => ({
      ...current,
      [key]: value,
    }));
  }

  function applyFilters() {
    setAppliedFilters(draftFilters);
    setOpenFilterKey("");
  }

  function clearFilter(key: keyof DraftFilters) {
    const clearedValue = Array.isArray(emptyFilters[key])
      ? []
      : "";

    setDraftFilters((current) => ({
      ...current,
      [key]: clearedValue,
    }));

    setAppliedFilters((current) => ({
      ...current,
      [key]: clearedValue,
    }));

    setOpenFilterKey("");
  }

  function clearAllFilters() {
    setDraftFilters(emptyFilters);
    setAppliedFilters(emptyFilters);
    setOpenFilterKey("");
  }

  function toggleSort(key: keyof SummaryDataRow) {
    setSortState((current) => {
      if (!current || current.key !== key) {
        return {
          key,
          direction: "asc",
        };
      }

      if (current.direction === "asc") {
        return {
          key,
          direction: "desc",
        };
      }

      return null;
    });
  }

  function sortIndicator(key: keyof SummaryDataRow) {
    if (!sortState || sortState.key !== key) {
      return "↕";
    }

    return sortState.direction === "asc" ? "↑" : "↓";
  }

  function hasActiveFilter(key: keyof DraftFilters) {
    const value = appliedFilters[key];

    return Array.isArray(value)
      ? value.length > 0
      : Boolean(String(value || "").trim());
  }

  useEffect(() => {
    if (!clientId || !projectId) {
      setRows([]);
      return;
    }

    apiGet(
      `/api/summaries/summary-data?client=${encodeURIComponent(
        clientId
      )}&project=${encodeURIComponent(projectId)}`
    )
      .then((response) => {
        setRows(response.rows || []);
      })
      .catch((error) => {
        console.error(error);
        setMessage("Failed to load saved QC summaries.");
        setRows([]);
      });
  }, [clientId, projectId]);

  const filteredRows = useMemo(() => {
    let nextRows = [...rows];

    const checkboxKeys: Array<"pdf_name" | "batch_id" | "source"> = [
      "pdf_name",
      "batch_id",
      "source",
    ];

    checkboxKeys.forEach((key) => {
      const selected = appliedFilters[key];

      if (selected.length > 0) {
        nextRows = nextRows.filter((row) =>
          selected.includes(cleanValue(row[key]))
        );
      }
    });

    const searchKeys: Array<
      | "title"
      | "citation"
      | "original_summary"
      | "qc_summary"
      | "last_modified"
    > = [
      "title",
      "citation",
      "original_summary",
      "qc_summary",
      "last_modified",
    ];

    searchKeys.forEach((key) => {
      const searchValue = appliedFilters[key].trim().toLowerCase();

      if (searchValue) {
        nextRows = nextRows.filter((row) =>
          cleanValue(row[key]).toLowerCase().includes(searchValue)
        );
      }
    });

    if (sortState) {
      nextRows.sort((a, b) => {
        const aValue = cleanValue(a[sortState.key]);
        const bValue = cleanValue(b[sortState.key]);

        const compared = aValue.localeCompare(bValue, undefined, {
          numeric: true,
          sensitivity: "base",
        });

        return sortState.direction === "asc" ? compared : -compared;
      });
    }

    return nextRows;
  }, [rows, appliedFilters, sortState]);

  const columns = [
    { key: "pdf_name", label: "PDF Name" },
    { key: "batch_id", label: "Summary Set" },
    { key: "title", label: "Title" },
    { key: "citation", label: "Citation" },
    { key: "original_summary", label: "Original Summary" },
    { key: "qc_summary", label: "QC Summary" },
    { key: "source", label: "Source" },
    { key: "last_modified", label: "Last Modified" },
  ];

  function renderCheckboxFilter(
    key: "pdf_name" | "batch_id" | "source",
    label: string
  ) {
    const values = getUniqueValues(key);

    return (
      <div className="relative">
        <button
          type="button"
          onClick={() =>
            setOpenFilterKey(openFilterKey === key ? "" : key)
          }
          className={[
            "flex w-full items-center justify-between gap-2 rounded-lg border px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide",
            hasActiveFilter(key)
              ? "border-lime-500 bg-lime-950 text-lime-200"
              : "border-slate-700 bg-slate-900 text-slate-300",
          ].join(" ")}
        >
          <span>{label}</span>
          <span>{sortIndicator(key)}</span>
        </button>

        {openFilterKey === key && (
          <div className="absolute left-0 top-full z-30 mt-2 w-72 rounded-xl border border-slate-700 bg-slate-950 p-3 shadow-xl">
            <button
              type="button"
              onClick={() => toggleSort(key)}
              className="mb-3 w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-left text-xs text-slate-200 hover:bg-slate-800"
            >
              Sort {sortIndicator(key)}
            </button>

            <div className="max-h-60 space-y-2 overflow-y-auto pr-1">
              {values.length === 0 ? (
                <p className="text-xs text-slate-500">No values found.</p>
              ) : (
                values.map((value) => (
                  <label
                    key={value}
                    className="flex items-center gap-2 text-xs text-slate-300"
                  >
                    <input
                      type="checkbox"
                      checked={draftFilters[key].includes(value)}
                      onChange={() => toggleDraftCheckbox(key, value)}
                    />
                    <span className="truncate">{value}</span>
                  </label>
                ))
              )}
            </div>

            <div className="mt-3 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => clearFilter(key)}
                className="rounded-full border border-slate-700 px-3 py-1 text-xs text-slate-300 hover:bg-slate-800"
              >
                Clear
              </button>

              <button
                type="button"
                onClick={applyFilters}
                className="rounded-full bg-lime-400 px-3 py-1 text-xs font-semibold text-slate-950 hover:bg-lime-300"
              >
                OK
              </button>
            </div>
          </div>
        )}
      </div>
    );
  }

  function renderSearchFilter(
    key:
      | "title"
      | "citation"
      | "original_summary"
      | "qc_summary"
      | "last_modified",
    label: string
  ) {
    return (
      <div className="relative">
        <button
          type="button"
          onClick={() =>
            setOpenFilterKey(openFilterKey === key ? "" : key)
          }
          className={[
            "flex w-full items-center justify-between gap-2 rounded-lg border px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide",
            hasActiveFilter(key)
              ? "border-lime-500 bg-lime-950 text-lime-200"
              : "border-slate-700 bg-slate-900 text-slate-300",
          ].join(" ")}
        >
          <span>{label}</span>
          <span>{sortIndicator(key)}</span>
        </button>

        {openFilterKey === key && (
          <div className="absolute left-0 top-full z-30 mt-2 w-80 rounded-xl border border-slate-700 bg-slate-950 p-3 shadow-xl">
            <button
              type="button"
              onClick={() => toggleSort(key)}
              className="mb-3 w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-left text-xs text-slate-200 hover:bg-slate-800"
            >
              Sort {sortIndicator(key)}
            </button>

            <input
              value={draftFilters[key]}
              onChange={(event) =>
                updateDraftSearch(key, event.target.value)
              }
              placeholder={`Search ${label}`}
              className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-white outline-none focus:border-lime-400"
            />

            <p className="mt-2 text-[11px] text-slate-500">
              Results update only after OK is clicked.
            </p>

            <div className="mt-3 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => clearFilter(key)}
                className="rounded-full border border-slate-700 px-3 py-1 text-xs text-slate-300 hover:bg-slate-800"
              >
                Clear
              </button>

              <button
                type="button"
                onClick={applyFilters}
                className="rounded-full bg-lime-400 px-3 py-1 text-xs font-semibold text-slate-950 hover:bg-lime-300"
              >
                OK
              </button>
            </div>
          </div>
        )}
      </div>
    );
  }

  if (!projectId) {
    return (
      <AppShell>
        <PageContainer>
          <PageHeader
            title="Saved QC Summaries"
            subtitle="Select a project first."
          />
        </PageContainer>
      </AppShell>
    );
  }

  return (
    <AppShell>
      <PageContainer>
        <PageHeader
          title="Saved QC Summaries"
          subtitle={`Saved summary edits for ${projectId.replaceAll(
            "_",
            " "
          )}.`}
        />

        {message && (
          <p className="mb-4 text-sm text-red-400">
            {message}
          </p>
        )}

        <ContentCard title="Updated Summary Data Table">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
            <p className="text-sm text-slate-400">
              Showing {filteredRows.length} of {rows.length} saved QC summaries.
            </p>

            <button
              type="button"
              onClick={clearAllFilters}
              className="rounded-full border border-slate-700 px-4 py-2 text-xs font-semibold text-slate-300 hover:bg-slate-800"
            >
              Clear All Filters
            </button>
          </div>

          <div className="max-h-[70vh] overflow-auto rounded-xl border border-slate-800">
            <table className="w-full min-w-[1600px] text-left text-sm">
              <thead className="sticky top-0 z-20 bg-slate-950">
                <tr className="border-b border-slate-800">
                  <th className="min-w-[180px] px-3 py-3 align-top">
                    {renderCheckboxFilter("pdf_name", "PDF Name")}
                  </th>

                  <th className="min-w-[180px] px-3 py-3 align-top">
                    {renderCheckboxFilter("batch_id", "Summary Set")}
                  </th>

                  <th className="min-w-[260px] px-3 py-3 align-top">
                    {renderSearchFilter("title", "Title")}
                  </th>

                  <th className="min-w-[280px] px-3 py-3 align-top">
                    {renderSearchFilter("citation", "Citation")}
                  </th>

                  <th className="min-w-[420px] px-3 py-3 align-top">
                    {renderSearchFilter("original_summary", "Original Summary")}
                  </th>

                  <th className="min-w-[420px] px-3 py-3 align-top">
                    {renderSearchFilter("qc_summary", "QC Summary")}
                  </th>

                  <th className="min-w-[160px] px-3 py-3 align-top">
                    {renderCheckboxFilter("source", "Source")}
                  </th>

                  <th className="min-w-[220px] px-3 py-3 align-top">
                    {renderSearchFilter("last_modified", "Last Modified")}
                  </th>
                </tr>
              </thead>

              <tbody>
                {filteredRows.length === 0 ? (
                  <tr>
                    <td
                      colSpan={8}
                      className="px-4 py-8 text-center text-sm text-slate-400"
                    >
                      No saved QC summaries match the applied filters.
                    </td>
                  </tr>
                ) : (
                  filteredRows.map((row, index) => (
                    <tr
                      key={`${row.pdf_name}-${row.summary_doc_id || row.title}-${index}`}
                      className="border-b border-slate-800 last:border-b-0 hover:bg-slate-900/70"
                    >
                      <td className="px-3 py-3 align-top text-slate-200">
                        {row.pdf_name || "—"}
                      </td>

                      <td className="px-3 py-3 align-top text-slate-300">
                        {row.batch_id || "—"}
                      </td>

                      <td className="px-3 py-3 align-top text-slate-200">
                        {row.title || "—"}
                      </td>

                      <td className="px-3 py-3 align-top text-slate-300">
                        {row.citation || "—"}
                      </td>

                      <td className="max-w-[520px] whitespace-pre-wrap px-3 py-3 align-top text-slate-300">
                        {row.original_summary || "—"}
                      </td>

                      <td className="max-w-[520px] whitespace-pre-wrap px-3 py-3 align-top text-slate-200">
                        {row.qc_summary || "—"}
                      </td>

                      <td className="px-3 py-3 align-top text-slate-400">
                        {row.source || "—"}
                      </td>

                      <td className="px-3 py-3 align-top text-slate-400">
                        {row.last_modified || "—"}
                      </td>
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

export default function SummaryDataPage() {
  return (
    <Suspense fallback={<div>Loading saved QC summaries...</div>}>
      <SummaryDataPageContent />
    </Suspense>
  );
}