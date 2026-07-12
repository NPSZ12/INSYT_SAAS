"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";

import AppShell from "../../../../components/AppShell";
import PageContainer from "../../../../components/PageContainer";
import PageHeader from "../../../../components/PageHeader";
import ContentCard from "../../../../components/ContentCard";
import { apiGet, apiPost } from "../../../../lib/api";

type CsvRow = Record<string, string>;

function normalizeCell(value: unknown) {
  return String(value ?? "");
}

function OutputEditorContent() {
  const searchParams = useSearchParams();

  const workspace = searchParams.get("workspace") || "capture";
  const clientId = searchParams.get("client") || "";
  const projectId = searchParams.get("project") || "";
  const blobPath = searchParams.get("blob_path") || "";

  const [columns, setColumns] = useState<string[]>([]);
  const [rows, setRows] = useState<CsvRow[]>([]);
  const [selectedRows, setSelectedRows] = useState<Record<number, boolean>>({});
  const [selectedColumns, setSelectedColumns] = useState<Record<string, boolean>>({});
  const [filterText, setFilterText] = useState("");
  const [sortColumn, setSortColumn] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [fileName, setFileName] = useState("");

  const visibleRows = useMemo(() => {
    let working = [...rows];

    const filter = filterText.trim().toLowerCase();

    if (filter) {
      working = working.filter((row) =>
        columns.some((column) =>
          normalizeCell(row[column]).toLowerCase().includes(filter)
        )
      );
    }

    if (sortColumn) {
      working.sort((a, b) =>
        normalizeCell(a[sortColumn]).localeCompare(normalizeCell(b[sortColumn]))
      );
    }

    return working;
  }, [rows, columns, filterText, sortColumn]);

  async function loadData() {
    if (!clientId || !projectId || !blobPath) {
      setMessage("Missing client, project, or blob path.");
      return;
    }

    setBusy(true);
    setMessage("");

    try {
      const data = await apiGet(
        `/api/cyber-utility/xl-processing/csv-editor-data?workspace=${encodeURIComponent(
          workspace
        )}&client=${encodeURIComponent(clientId)}&project=${encodeURIComponent(
          projectId
        )}&blob_path=${encodeURIComponent(blobPath)}`
      );

      setColumns(data.columns || []);
      setRows(data.rows || []);
      setFileName(data.file_name || "");
      setSelectedRows({});
      setSelectedColumns({});

      if (data.truncated) {
        setMessage(
          `Loaded first ${data.row_count} rows out of ${data.total_rows}. Save carefully if the file is very large.`
        );
      }
    } catch (err: any) {
      setMessage(err?.message || "Failed to load CSV editor data.");
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    loadData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workspace, clientId, projectId, blobPath]);

  function updateCell(rowIndex: number, column: string, value: string) {
    setRows((current) =>
      current.map((row, index) =>
        index === rowIndex
          ? {
              ...row,
              [column]: value,
            }
          : row
      )
    );
  }

  function toggleAllRows(selected: boolean) {
    const next: Record<number, boolean> = {};

    rows.forEach((_, index) => {
      next[index] = selected;
    });

    setSelectedRows(next);
  }

  function deleteSelectedRows() {
    const selectedIndexes = new Set(
      Object.entries(selectedRows)
        .filter(([, selected]) => selected)
        .map(([index]) => Number(index))
    );

    if (!selectedIndexes.size) {
      setMessage("Select one or more rows to delete.");
      return;
    }

    if (!window.confirm(`Delete ${selectedIndexes.size} selected row(s)?`)) {
      return;
    }

    setRows((current) => current.filter((_, index) => !selectedIndexes.has(index)));
    setSelectedRows({});
    setMessage(`Deleted ${selectedIndexes.size} row(s).`);
  }

  function toggleColumn(column: string, selected: boolean) {
    setSelectedColumns((current) => ({
      ...current,
      [column]: selected,
    }));
  }

  function deleteSelectedColumns() {
    const colsToDelete = columns.filter((column) => selectedColumns[column]);

    if (!colsToDelete.length) {
      setMessage("Select one or more columns to delete.");
      return;
    }

    if (!window.confirm(`Delete ${colsToDelete.length} selected column(s)?`)) {
      return;
    }

    setColumns((current) => current.filter((column) => !colsToDelete.includes(column)));

    setRows((current) =>
      current.map((row) => {
        const next = { ...row };

        for (const column of colsToDelete) {
          delete next[column];
        }

        return next;
      })
    );

    setSelectedColumns({});
    setMessage(`Deleted ${colsToDelete.length} column(s).`);
  }

  function removeDuplicates() {
    const dedupeColumns = columns.filter((column) => selectedColumns[column]);

    if (!dedupeColumns.length) {
      setMessage("Select one or more columns for duplicate removal.");
      return;
    }

    const seen = new Set<string>();
    const nextRows: CsvRow[] = [];

    for (const row of rows) {
      const key = dedupeColumns.map((column) => normalizeCell(row[column]).trim()).join("||");

      if (!seen.has(key)) {
        seen.add(key);
        nextRows.push(row);
      }
    }

    const removed = rows.length - nextRows.length;

    setRows(nextRows);
    setSelectedRows({});
    setMessage(`Removed ${removed} duplicate row(s).`);
  }

  async function saveChanges() {
    setBusy(true);
    setMessage("");

    try {
      const result = await apiPost("/api/cyber-utility/xl-processing/csv-editor-save", {
        workspace,
        client: clientId,
        project_id: projectId,
        blob_path: blobPath,
        columns,
        rows,
      });

      setMessage(result.message || "Changes saved.");
    } catch (err: any) {
      setMessage(err?.message || "Failed to save changes.");
    } finally {
      setBusy(false);
    }
  }

  async function saveToCompleted() {
    if (!window.confirm("Save this reviewed file to Completed?")) {
      return;
    }

    setBusy(true);
    setMessage("");

    try {
      const result = await apiPost("/api/cyber-utility/xl-processing/save-deduped-to-completed", {
        workspace,
        client: clientId,
        project_id: projectId,
        blob_path: blobPath,
        columns,
        rows,
      });

      setMessage(result.message || "Saved to Completed.");
    } catch (err: any) {
      setMessage(err?.message || "Failed to save to Completed.");
    } finally {
      setBusy(false);
    }
  }

  async function deleteFile() {
    if (!window.confirm("Delete this deduplicated output file? This cannot be undone.")) {
      return;
    }

    setBusy(true);
    setMessage("");

    try {
      const result = await apiPost("/api/cyber-utility/xl-processing/delete-deduped-output", {
        workspace,
        client: clientId,
        project_id: projectId,
        blob_path: blobPath,
        columns,
        rows,
      });

      setMessage(result.message || "File deleted.");
      setRows([]);
      setColumns([]);
    } catch (err: any) {
      setMessage(err?.message || "Failed to delete file.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AppShell>
      <PageContainer>
        <PageHeader
          title="Spreadsheet Output Editor"
          subtitle={fileName || "Review and edit deduplicated spreadsheet output before saving to Completed."}
        />

        {message ? (
          <div className="mb-4 rounded-md border border-slate-700 bg-slate-900 px-4 py-3 text-sm text-slate-100">
            {message}
          </div>
        ) : null}

        <ContentCard title="Editor Controls">
          <div className="flex flex-wrap gap-2">
            <button
              className="rounded-md bg-slate-800 px-3 py-2 text-sm text-white hover:bg-slate-700 disabled:opacity-50"
              onClick={loadData}
              disabled={busy}
            >
              Reload
            </button>

            <button
              className="rounded-md bg-slate-800 px-3 py-2 text-sm text-white hover:bg-slate-700 disabled:opacity-50"
              onClick={() => toggleAllRows(true)}
              disabled={!rows.length}
            >
              Select All Rows
            </button>

            <button
              className="rounded-md bg-slate-800 px-3 py-2 text-sm text-white hover:bg-slate-700 disabled:opacity-50"
              onClick={() => toggleAllRows(false)}
              disabled={!rows.length}
            >
              Clear Row Selection
            </button>

            <button
              className="rounded-md bg-red-700 px-3 py-2 text-sm text-white hover:bg-red-600 disabled:opacity-50"
              onClick={deleteSelectedRows}
              disabled={busy}
            >
              Delete Selected Rows
            </button>

            <button
              className="rounded-md bg-red-700 px-3 py-2 text-sm text-white hover:bg-red-600 disabled:opacity-50"
              onClick={deleteSelectedColumns}
              disabled={busy}
            >
              Delete Selected Columns
            </button>

            <button
              className="rounded-md bg-amber-700 px-3 py-2 text-sm text-white hover:bg-amber-600 disabled:opacity-50"
              onClick={removeDuplicates}
              disabled={busy}
            >
              Remove Duplicates by Selected Columns
            </button>

            <button
              className="rounded-md bg-slate-800 px-3 py-2 text-sm text-white hover:bg-slate-700 disabled:opacity-50"
              onClick={saveChanges}
              disabled={busy}
            >
              Save Changes
            </button>

            <button
              className="rounded-md bg-emerald-700 px-3 py-2 text-sm text-white hover:bg-emerald-600 disabled:opacity-50"
              onClick={saveToCompleted}
              disabled={busy}
            >
              Save to Completed
            </button>

            <button
              className="rounded-md bg-red-800 px-3 py-2 text-sm text-white hover:bg-red-700 disabled:opacity-50"
              onClick={deleteFile}
              disabled={busy}
            >
              Delete File
            </button>
          </div>

          <div className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-3">
            <label className="text-sm text-slate-300">
              Filter
              <input
                className="mt-1 w-full rounded-md border border-slate-700 bg-slate-950 px-2 py-2 text-slate-100"
                value={filterText}
                onChange={(event) => setFilterText(event.target.value)}
                placeholder="Search any cell..."
              />
            </label>

            <label className="text-sm text-slate-300">
              Sort Column
              <select
                className="mt-1 w-full rounded-md border border-slate-700 bg-slate-950 px-2 py-2 text-slate-100"
                value={sortColumn}
                onChange={(event) => setSortColumn(event.target.value)}
              >
                <option value="">No Sort</option>
                {columns.map((column) => (
                  <option key={column} value={column}>
                    {column}
                  </option>
                ))}
              </select>
            </label>
          </div>
        </ContentCard>

        <ContentCard title={`Columns (${columns.length})`}>
          <div className="max-h-40 overflow-auto rounded-md border border-slate-800 p-3">
            <div className="grid grid-cols-1 gap-2 md:grid-cols-3">
              {columns.map((column) => (
                <label key={column} className="flex items-center gap-2 text-sm text-slate-200">
                  <input
                    type="checkbox"
                    checked={!!selectedColumns[column]}
                    onChange={(event) => toggleColumn(column, event.target.checked)}
                  />
                  {column}
                </label>
              ))}
            </div>
          </div>
        </ContentCard>

        <ContentCard title={`Rows (${rows.length})`}>
          <div className="max-h-[650px] overflow-auto rounded-md border border-slate-800">
            <table className="w-full min-w-max text-left text-xs">
              <thead className="sticky top-0 bg-slate-900 text-slate-300">
                <tr>
                  <th className="px-2 py-2"></th>
                  <th className="px-2 py-2">#</th>
                  {columns.map((column) => (
                    <th key={column} className="min-w-40 px-2 py-2">
                      {column}
                    </th>
                  ))}
                </tr>
              </thead>

              <tbody>
                {visibleRows.map((row, visibleIndex) => {
                  const rowIndex = rows.indexOf(row);

                  return (
                    <tr key={`${rowIndex}-${visibleIndex}`} className="border-t border-slate-800">
                      <td className="px-2 py-1">
                        <input
                          type="checkbox"
                          checked={!!selectedRows[rowIndex]}
                          onChange={(event) =>
                            setSelectedRows((current) => ({
                              ...current,
                              [rowIndex]: event.target.checked,
                            }))
                          }
                        />
                      </td>
                      <td className="px-2 py-1 text-slate-500">{rowIndex + 1}</td>

                      {columns.map((column) => (
                        <td key={column} className="px-2 py-1">
                          <input
                            className="w-full min-w-40 rounded border border-slate-800 bg-slate-950 px-2 py-1 text-slate-100"
                            value={normalizeCell(row[column])}
                            onChange={(event) => updateCell(rowIndex, column, event.target.value)}
                          />
                        </td>
                      ))}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </ContentCard>
      </PageContainer>
    </AppShell>
  );
}

export default function OutputEditorPage() {
  return (
    <Suspense
      fallback={
        <AppShell>
          <PageContainer>
            <PageHeader
              title="Spreadsheet Output Editor"
              subtitle="Loading spreadsheet output editor..."
            />
          </PageContainer>
        </AppShell>
      }
    >
      <OutputEditorContent />
    </Suspense>
  );
}