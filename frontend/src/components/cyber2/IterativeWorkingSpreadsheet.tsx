"use client";

import { useMemo, useState } from "react";

export type IterativeSpreadsheetRow = {
  working_record_id: string;
  classification: string;
  group_number: number | null;
  source_ucids: string[];
  source_doc_ids: string[];
  cells: Record<string, unknown>;
  field_provenance: Record<string, Array<{
    ucid: string;
    doc_id?: string;
    source_row_number?: number | null;
    source_column_index?: number | null;
    source_header?: string | null;
    original_value?: unknown;
  }>>;
};

export type IterativeSpreadsheetData = {
  status: string;
  header_set_id: string;
  parent_merge_set_id: string;
  merge_index: string[];
  snapshot_fingerprint: string;
  preview_columns: string[];
  preview_rows: IterativeSpreadsheetRow[];
  preview_row_count: number;
  preview_rows_complete: boolean;
  execution_enabled: boolean;
};

function display(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return JSON.stringify(value);
}

export default function IterativeWorkingSpreadsheet({
  data,
}: {
  data: IterativeSpreadsheetData;
}) {
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(100);
  const [selectedId, setSelectedId] = useState("");

  const rows = useMemo(() => {
    const rank: Record<string, number> = {
      exact_duplicate: 0,
      qc_conflict: 1,
      unmatched: 2,
      excluded: 3,
    };
    return [...data.preview_rows].sort(
      (a, b) =>
        (rank[a.classification] ?? 9) -
          (rank[b.classification] ?? 9) ||
        (a.group_number ?? 0) - (b.group_number ?? 0) ||
        a.working_record_id.localeCompare(b.working_record_id)
    );
  }, [data.preview_rows]);

  const pages = Math.max(1, Math.ceil(rows.length / pageSize));
  const current = Math.min(page, pages - 1);
  const visible = rows.slice(
    current * pageSize,
    (current + 1) * pageSize
  );
  const selected = rows.find(
    row => row.working_record_id === selectedId
  );

  return (
    <section className="mt-5 space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h4 className="font-semibold text-white">
          Second-Pass Working Spreadsheet
        </h4>
        <span className="text-xs text-slate-400">
          {rows.length.toLocaleString()} working records |
          {" "}{data.preview_columns.length} columns
        </span>
      </div>

      <div className="flex flex-wrap items-center gap-3 text-xs">
        <label>
          Rows per page{" "}
          <select
            aria-label="Working spreadsheet rows per page"
            value={pageSize}
            onChange={event => {
              setPageSize(Number(event.target.value));
              setPage(0);
            }}
            className="rounded border border-slate-700 bg-slate-950 p-2"
          >
            {[50, 100, 200, 500].map(size => (
              <option key={size} value={size}>{size}</option>
            ))}
          </select>
        </label>
        <span>Page {current + 1} of {pages}</span>
        <button
          type="button"
          disabled={current === 0}
          onClick={() => setPage(v => Math.max(0, v - 1))}
          className="rounded border border-slate-700 px-3 py-2 disabled:opacity-40"
        >
          Previous
        </button>
        <button
          type="button"
          disabled={current + 1 >= pages}
          onClick={() => setPage(v => v + 1)}
          className="rounded border border-slate-700 px-3 py-2 disabled:opacity-40"
        >
          Next
        </button>
      </div>

      <div className="max-h-[450px] overflow-auto rounded-lg border border-slate-700">
        <table className="min-w-max text-left text-xs">
          <thead className="sticky top-0 z-10 bg-slate-900 text-slate-200">
            <tr>
              {["Working Record", "Classification", "Group", "Source Count",
                ...data.preview_columns].map(field => (
                <th key={field} className="whitespace-nowrap p-3">
                  {field}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {visible.map(row => (
              <tr key={row.working_record_id}
                  className="border-t border-slate-800">
                <td className="p-2">
                  <button
                    type="button"
                    className="text-sky-300 underline"
                    onClick={() => setSelectedId(row.working_record_id)}
                  >
                    {row.working_record_id}
                  </button>
                </td>
                <td className="p-2">{row.classification}</td>
                <td className="p-2">{row.group_number ?? ""}</td>
                <td className="p-2">{row.source_ucids.length}</td>
                {data.preview_columns.map(field => (
                  <td key={field} className="max-w-[260px] p-2">
                    <span
                      className="block max-w-[260px] truncate"
                      title={display(row.cells[field])}
                    >
                      {display(row.cells[field])}
                    </span>
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {selected && (
        <div className="rounded-lg border border-slate-700 bg-slate-950 p-4">
          <div className="mb-3 flex items-center justify-between gap-3">
            <h5 className="font-semibold text-white">
              Source Evidence — {selected.working_record_id}
            </h5>
            <button
              type="button"
              className="text-sky-300 underline"
              onClick={() => setSelectedId("")}
            >
              Close
            </button>
          </div>
          <div className="max-h-[350px] overflow-auto">
            <table className="min-w-max text-left text-xs">
              <thead className="sticky top-0 bg-slate-900">
                <tr>
                  {["Field", "UCID", "Document", "Row", "Column",
                    "Source Header", "Original Value"].map(name => (
                    <th key={name} className="p-2">{name}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.preview_columns.flatMap(field =>
                  (selected.field_provenance[field] || []).map(
                    (entry, index) => (
                      <tr key={`${field}-${index}`}
                          className="border-t border-slate-800">
                        <td className="p-2">{field}</td>
                        <td className="p-2">{entry.ucid}</td>
                        <td className="p-2">{entry.doc_id ?? ""}</td>
                        <td className="p-2">{entry.source_row_number ?? ""}</td>
                        <td className="p-2">{entry.source_column_index ?? ""}</td>
                        <td className="p-2">{entry.source_header ?? ""}</td>
                        <td className="max-w-[400px] whitespace-pre-wrap p-2">
                          {display(entry.original_value)}
                        </td>
                      </tr>
                    )
                  )
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </section>
  );
}
