"use client";

import { useEffect, useMemo, useState } from "react";

export type SpreadsheetRow = {
  ucid: string;
  doc_id: string;
  classification: string;
  group_number: number | null;
  cells: Record<string, unknown>;
  source?: {
    header_set_id?: string;
    source_row_number?: number | null;
  };
};

export type SpreadsheetPreview = {
  status: string;
  header_set_id: string;
  merge_index: string[];
  preview_columns: string[];
  preview_rows: SpreadsheetRow[];
  preview_row_count: number;
  preview_rows_complete: boolean;
  execution_enabled: boolean;
};

type Props = {
  data: SpreadsheetPreview;
  onClose: () => void;
};

function displayValue(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "string") return value;
  if (
    typeof value === "number" ||
    typeof value === "boolean"
  ) {
    return String(value);
  }
  return JSON.stringify(value);
}

function labelFor(row: SpreadsheetRow): string {
  if (row.classification === "exact_duplicate") {
    return `Exact group ${row.group_number ?? ""}`;
  }
  if (row.classification === "qc_conflict") {
    return `QC conflict ${row.group_number ?? ""}`;
  }
  if (row.classification === "excluded") {
    return "Excluded";
  }
  return "Unmatched";
}

export default function ExactMatchSpreadsheetModal({
  data,
  onClose,
}: Props) {
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(100);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const orderedRows = useMemo(() => {
    const rank: Record<string, number> = {
      exact_duplicate: 0,
      qc_conflict: 1,
      unmatched: 2,
      excluded: 3,
    };

    return [...data.preview_rows].sort((a, b) => {
      const category =
        (rank[a.classification] ?? 9) -
        (rank[b.classification] ?? 9);

      if (category !== 0) return category;

      return (
        (a.group_number ?? 0) -
        (b.group_number ?? 0)
      );
    });
  }, [data.preview_rows]);

  const totalPages = Math.max(
    1,
    Math.ceil(orderedRows.length / pageSize)
  );

  const currentPage = Math.min(page, totalPages - 1);
  const visibleRows = orderedRows.slice(
    currentPage * pageSize,
    (currentPage + 1) * pageSize
  );

  const indexFields = new Set(data.merge_index);

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center bg-black/85 p-2 md:p-4"
      role="presentation"
    >
      <section
        role="dialog"
        aria-modal="true"
        aria-labelledby="cyber2-spreadsheet-title"
        className="flex h-[94vh] w-[98vw] min-h-0 flex-col overflow-hidden rounded-xl border border-slate-600 bg-slate-950 shadow-2xl"
      >
        <header className="flex shrink-0 flex-wrap items-center justify-between gap-3 border-b border-slate-700 p-4">
          <div>
            <h2
              id="cyber2-spreadsheet-title"
              className="text-xl font-bold text-white"
            >
              3. Exact-Match Spreadsheet Preview
            </h2>
            <p className="mt-1 text-sm text-slate-400">
              {data.header_set_id} | {data.preview_row_count} RAW rows
              {" | "}
              {data.preview_columns.length} protocol columns
            </p>
          </div>

          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border border-slate-600 px-4 py-2 text-sm text-white hover:bg-slate-800"
          >
            Close Spreadsheet
          </button>
        </header>

        <div className="shrink-0 border-b border-slate-800 px-4 py-3">
          <p className="text-sm text-slate-300">
            All approved captured values are displayed without masking.
            Blue headers identify Merge Index fields. Rows are grouped
            by exact matches, QC conflicts, unmatched records, and
            excluded records.
          </p>

          <div className="mt-2 flex flex-wrap gap-2 text-xs">
            <span className="rounded bg-sky-900 px-2 py-1 text-sky-200">
              Exact duplicate
            </span>
            <span className="rounded bg-amber-900 px-2 py-1 text-amber-200">
              QC conflict
            </span>
            <span className="rounded bg-slate-800 px-2 py-1 text-slate-200">
              Unmatched
            </span>
            <span className="rounded bg-rose-950 px-2 py-1 text-rose-300">
              Excluded
            </span>
          </div>
        </div>

        <div className="min-h-0 flex-1 overflow-auto">
          <table className="w-max min-w-full border-collapse text-left text-xs">
            <thead className="sticky top-0 z-20">
              <tr className="bg-slate-900">
                {[
                  "Match Status",
                  "UCID",
                  "Source Doc ID",
                  "Source Row",
                ].map((name) => (
                  <th
                    key={name}
                    className="min-w-[135px] whitespace-nowrap border border-slate-700 bg-slate-900 p-3 font-semibold text-white"
                  >
                    {name}
                  </th>
                ))}

                {data.preview_columns.map((field) => (
                  <th
                    key={field}
                    className={`min-w-[170px] max-w-[300px] border border-slate-700 p-3 align-top font-semibold ${
                      indexFields.has(field)
                        ? "bg-sky-900 text-sky-100"
                        : "bg-slate-900 text-slate-200"
                    }`}
                  >
                    {field}
                  </th>
                ))}
              </tr>
            </thead>

            <tbody>
              {visibleRows.map((row) => {
                const rowClass =
                  row.classification === "exact_duplicate"
                    ? "bg-sky-950/30"
                    : row.classification === "qc_conflict"
                      ? "bg-amber-950/30"
                      : row.classification === "excluded"
                        ? "bg-rose-950/20"
                        : "bg-slate-950";

                return (
                  <tr
                    key={row.ucid}
                    className={`${rowClass} hover:bg-slate-800/70`}
                  >
                    <td className="whitespace-nowrap border border-slate-800 p-3 font-medium text-white">
                      {labelFor(row)}
                    </td>
                    <td className="whitespace-nowrap border border-slate-800 p-3 text-sky-300">
                      {row.ucid}
                    </td>
                    <td className="whitespace-nowrap border border-slate-800 p-3 text-slate-200">
                      {row.doc_id}
                    </td>
                    <td className="border border-slate-800 p-3 text-slate-200">
                      {row.source?.source_row_number ?? ""}
                    </td>

                    {data.preview_columns.map((field) => (
                      <td
                        key={`${row.ucid}:${field}`}
                        className={`max-w-[300px] whitespace-pre-wrap break-words border border-slate-800 p-3 align-top ${
                          indexFields.has(field)
                            ? "text-sky-200"
                            : "text-slate-200"
                        }`}
                      >
                        {displayValue(row.cells[field])}
                      </td>
                    ))}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        <footer className="shrink-0 border-t border-slate-700 bg-slate-900 p-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex flex-wrap items-center gap-3 text-sm text-slate-300">
              <span>
                Rows {orderedRows.length === 0 ? 0 : currentPage * pageSize + 1}
                {" - "}
                {Math.min((currentPage + 1) * pageSize, orderedRows.length)}
                {" of "}
                {orderedRows.length}
              </span>

              <select
                aria-label="Spreadsheet rows per page"
                value={pageSize}
                onChange={(event) => {
                  setPageSize(Number(event.target.value));
                  setPage(0);
                }}
                className="rounded border border-slate-600 bg-slate-950 p-2 text-white"
              >
                <option value={100}>100 rows</option>
                <option value={500}>500 rows</option>
              </select>

              <button
                type="button"
                disabled={currentPage === 0}
                onClick={() => setPage((value) => Math.max(0, value - 1))}
                className="rounded border border-slate-600 px-3 py-2 text-white disabled:opacity-30"
              >
                Previous
              </button>

              <span>
                Page {currentPage + 1} of {totalPages}
              </span>

              <button
                type="button"
                disabled={currentPage >= totalPages - 1}
                onClick={() => setPage((value) => value + 1)}
                className="rounded border border-slate-600 px-3 py-2 text-white disabled:opacity-30"
              >
                Next
              </button>
            </div>

            <div className="flex items-center gap-3">
              <span className="text-xs text-slate-400">
                4. Execute & Continue
              </span>
              <button
                type="button"
                disabled
                title="Merge-set persistence and provenance validation are not yet enabled."
                className="rounded-lg bg-sky-700 px-5 py-3 text-sm font-semibold text-white opacity-40"
              >
                Execute & Continue
              </button>
            </div>
          </div>
        </footer>
      </section>
    </div>
  );
}