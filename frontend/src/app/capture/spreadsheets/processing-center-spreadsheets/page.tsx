"use client";

import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";

import AppShell from "../../../../components/AppShell";
import PageContainer from "../../../../components/PageContainer";
import PageHeader from "../../../../components/PageHeader";
import ContentCard from "../../../../components/ContentCard";
import DataTable from "../../../../components/DataTable";
import { apiGet, apiPost } from "../../../../lib/api";

type SpreadsheetFile = {
  doc_id?: string;
  file_name: string;
  extension?: string;
  blob_path: string;
  size?: string;
  last_modified?: string;
  status?: string;
  matched_prefix?: string;
};

type XlJob = {
  job_id: string;
  status: string;
  message?: string;
  created_at?: string;
  updated_at?: string;
  processed_files?: number;
  total_files?: number;
  extracted_headers?: HeaderReviewRow[];
  files_needing_header_review?: any[];
  output_files?: string[];
  final_output_blob?: string;
  header_map_blob?: string;
};

type HeaderReviewRow = {
  source_header: string;
  suggested_header: string;
  final_header: string;
  protocol?: string;
  header_library_blob?: string;
  ai_suggestion?: string;
  confidence?: string;
};

type XlProcessingCenterState = {
  workspace: string;
  client: string;
  project: string;
  source_files: SpreadsheetFile[];
  output_csvs: SpreadsheetFile[];
  merged_outputs: SpreadsheetFile[];
  needs_header_review: SpreadsheetFile[];
  jobs: XlJob[];
};

function formatDate(value?: string) {
  if (!value) return "";
  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
}

function fileSizeLabel(value?: string) {
  const size = Number(value || 0);

  if (!size) return "";

  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${Math.round(size / 1024)} KB`;

  return `${(size / (1024 * 1024)).toFixed(2)} MB`;
}

export default function SpreadsheetProcessingCenterPage() {
  const searchParams = useSearchParams();

  const clientId = searchParams.get("client") || "";
  const projectId = searchParams.get("project") || "";
  const workspace = "capture";

  const [state, setState] = useState<XlProcessingCenterState | null>(null);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  const [selectedSourceFiles, setSelectedSourceFiles] = useState<Record<string, boolean>>({});
  const [selectedOutputCsvs, setSelectedOutputCsvs] = useState<Record<string, boolean>>({});

  const [activeHeaderJob, setActiveHeaderJob] = useState<XlJob | null>(null);
  const [headerRows, setHeaderRows] = useState<HeaderReviewRow[]>([]);

  const selectedSourceBlobPaths = useMemo(
    () =>
      Object.entries(selectedSourceFiles)
        .filter(([, selected]) => selected)
        .map(([blob]) => blob),
    [selectedSourceFiles]
  );

  const selectedOutputBlobPaths = useMemo(
    () =>
      Object.entries(selectedOutputCsvs)
        .filter(([, selected]) => selected)
        .map(([blob]) => blob),
    [selectedOutputCsvs]
  );

  async function refreshCenter() {
    if (!clientId || !projectId) {
      setState(null);
      setMessage("Select a client and project first.");
      return;
    }

    setBusy(true);
    setMessage("");

    try {
      const data = await apiGet(
        `/api/cyber-utility/xl-processing/center?workspace=${encodeURIComponent(
          workspace
        )}&client=${encodeURIComponent(clientId)}&project=${encodeURIComponent(projectId)}`
      );

      setState(data);

      const reviewJob = (data.jobs || []).find(
        (job: XlJob) => job.status === "header_review_required"
      );

      if (reviewJob?.extracted_headers?.length) {
        setActiveHeaderJob(reviewJob);
        setHeaderRows(reviewJob.extracted_headers);
      }
    } catch (err: any) {
      setMessage(err?.message || "Failed to load Spreadsheet Processing Center.");
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    refreshCenter();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clientId, projectId]);

  async function runProcessing() {
    if (!clientId || !projectId) {
      setMessage("Select a client and project first.");
      return;
    }

    setBusy(true);
    setMessage("");

    try {
      const selectedFiles = selectedSourceBlobPaths;

      const job = await apiPost("/api/cyber-utility/jobs", {
        workspace,
        client: clientId,
        project_id: projectId,
        tool_name: "XL Processing",
        options: {
          build_master: true,
          extract_headers: true,
          delimiter: ",",
          selected_files: selectedFiles.length ? selectedFiles : undefined,
        },
      });

      setMessage(`XL Processing queued. Job ID: ${job.job_id}`);

      await refreshCenter();
      pollJob(job.job_id);
    } catch (err: any) {
      setMessage(err?.message || "Failed to start XL Processing.");
    } finally {
      setBusy(false);
    }
  }

  async function pollJob(jobId: string) {
    let attempts = 0;

    const timer = window.setInterval(async () => {
      attempts += 1;

      try {
        const job = await apiGet(`/api/cyber-utility/jobs/${encodeURIComponent(jobId)}`);

        if (job.status === "header_review_required") {
          window.clearInterval(timer);
          setActiveHeaderJob(job);
          setHeaderRows(job.extracted_headers || []);
          setMessage(job.message || "Header review required.");
          await refreshCenter();
          return;
        }

        if (
          job.status === "completed" ||
          job.status === "completed_with_errors" ||
          job.status === "failed" ||
          job.status === "final_merge_failed"
        ) {
          window.clearInterval(timer);
          setMessage(job.message || `Job ${job.status}.`);
          await refreshCenter();
          return;
        }

        if (attempts > 120) {
          window.clearInterval(timer);
          await refreshCenter();
        }
      } catch {
        window.clearInterval(timer);
      }
    }, 3000);
  }

  function updateHeaderRow(index: number, value: string) {
    setHeaderRows((rows) =>
      rows.map((row, idx) =>
        idx === index
          ? {
              ...row,
              final_header: value,
            }
          : row
      )
    );
  }

  async function applyHeaders() {
    if (!activeHeaderJob) {
      setMessage("No header review job is active.");
      return;
    }

    const headerMap: Record<string, string> = {};

    for (const row of headerRows) {
      if (row.source_header?.trim() && row.final_header?.trim()) {
        headerMap[row.source_header.trim()] = row.final_header.trim();
      }
    }

    setBusy(true);
    setMessage("");

    try {
      const result = await apiPost("/api/cyber-utility/xl-processing/apply-headers", {
        workspace,
        client: clientId,
        project_id: projectId,
        job_id: activeHeaderJob.job_id,
        header_map: headerMap,
        delimiter: ",",
      });

      setMessage(result.message || "Headers applied and final CSV rebuilt.");
      setActiveHeaderJob(null);
      setHeaderRows([]);
      await refreshCenter();
    } catch (err: any) {
      setMessage(err?.message || "Failed to apply headers.");
    } finally {
      setBusy(false);
    }
  }

  async function mergeSelectedOutputs() {
    if (!selectedOutputBlobPaths.length) {
      setMessage("Select one or more converted CSVs to merge.");
      return;
    }

    const outputName = window.prompt(
      "Output filename for this merged CSV:",
      `FINAL_MERGED_OUTPUT_${new Date()
        .toISOString()
        .slice(0, 19)
        .replace(/[-:T]/g, "")}.csv`
    );

    if (!outputName) return;

    setBusy(true);
    setMessage("");

    try {
      const result = await apiPost("/api/cyber-utility/xl-processing/merge-selected", {
        workspace,
        client: clientId,
        project_id: projectId,
        selected_csv_blobs: selectedOutputBlobPaths,
        header_map: {},
        delimiter: ",",
        output_name: outputName,
      });

      setMessage(result.message || "Selected CSV files merged.");
      setSelectedOutputCsvs({});
      await refreshCenter();
    } catch (err: any) {
      setMessage(err?.message || "Failed to merge selected CSVs.");
    } finally {
      setBusy(false);
    }
  }

  function toggleAllSourceFiles(selected: boolean) {
    const next: Record<string, boolean> = {};

    for (const file of state?.source_files || []) {
      next[file.blob_path] = selected;
    }

    setSelectedSourceFiles(next);
  }

  function toggleAllOutputCsvs(selected: boolean) {
    const next: Record<string, boolean> = {};

    for (const file of state?.output_csvs || []) {
      next[file.blob_path] = selected;
    }

    setSelectedOutputCsvs(next);
  }

  return (
    <AppShell>
      <PageContainer>
        <PageHeader
          title="Processing Center - Spreadsheets"
          subtitle="Convert Excel files to CSV, review headers, build merged outputs, and re-merge spreadsheet phases."
        />

        {message ? (
          <div className="mb-4 rounded-md border border-slate-700 bg-slate-900 px-4 py-3 text-sm text-slate-100">
            {message}
          </div>
        ) : null}

        <ContentCard title="Spreadsheet Processing Controls">
          <div className="flex flex-wrap gap-2">
            <button
              className="rounded-md bg-slate-800 px-3 py-2 text-sm text-white hover:bg-slate-700 disabled:opacity-50"
              onClick={refreshCenter}
              disabled={busy}
            >
              Refresh
            </button>

            <button
              className="rounded-md bg-emerald-700 px-3 py-2 text-sm text-white hover:bg-emerald-600 disabled:opacity-50"
              onClick={runProcessing}
              disabled={busy}
            >
              Run Processing
            </button>

            <button
              className="rounded-md bg-slate-800 px-3 py-2 text-sm text-white hover:bg-slate-700 disabled:opacity-50"
              onClick={() => toggleAllSourceFiles(true)}
              disabled={!state?.source_files?.length}
            >
              Select All Source Files
            </button>

            <button
              className="rounded-md bg-slate-800 px-3 py-2 text-sm text-white hover:bg-slate-700 disabled:opacity-50"
              onClick={() => toggleAllSourceFiles(false)}
              disabled={!state?.source_files?.length}
            >
              Clear Source Selection
            </button>
          </div>

          <div className="mt-3 text-xs text-slate-400">
            Source path:{" "}
            <span className="font-mono">
              {clientId}/capture/{projectId}/source/native/
            </span>
          </div>
        </ContentCard>

        {activeHeaderJob && headerRows.length ? (
          <ContentCard title="Header Review Required">
            <div className="mb-3 text-sm text-slate-300">
              Job ID: <span className="font-mono">{activeHeaderJob.job_id}</span>
            </div>

            <div className="max-h-[480px] overflow-auto rounded-md border border-slate-800">
              <table className="w-full text-left text-sm">
                <thead className="bg-slate-900 text-slate-300">
                  <tr>
                    <th className="px-3 py-2">Detected Header</th>
                    <th className="px-3 py-2">Suggested Header</th>
                    <th className="px-3 py-2">Final Header</th>
                  </tr>
                </thead>
                <tbody>
                  {headerRows.map((row, index) => (
                    <tr key={`${row.source_header}-${index}`} className="border-t border-slate-800">
                      <td className="px-3 py-2 font-mono text-xs text-slate-200">
                        {row.source_header}
                      </td>
                      <td className="px-3 py-2 text-slate-200">{row.suggested_header}</td>
                      <td className="px-3 py-2">
                        <input
                          className="w-full rounded-md border border-slate-700 bg-slate-950 px-2 py-1 text-slate-100"
                          value={row.final_header || ""}
                          onChange={(event) => updateHeaderRow(index, event.target.value)}
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="mt-4 flex gap-2">
              <button
                className="rounded-md bg-emerald-700 px-3 py-2 text-sm text-white hover:bg-emerald-600 disabled:opacity-50"
                onClick={applyHeaders}
                disabled={busy}
              >
                Apply Headers & Build Final CSV
              </button>

              <button
                className="rounded-md bg-slate-800 px-3 py-2 text-sm text-white hover:bg-slate-700"
                onClick={() => {
                  setActiveHeaderJob(null);
                  setHeaderRows([]);
                }}
              >
                Close
              </button>
            </div>
          </ContentCard>
        ) : null}

        <ContentCard title="Source XL / CSV Files">
          <DataTable
            columns={[
              {
                key: "select",
                label: "",
                render: (_: any, row: SpreadsheetFile) => (
                  <input
                    type="checkbox"
                    checked={!!selectedSourceFiles[row.blob_path]}
                    onChange={(event) =>
                      setSelectedSourceFiles((current) => ({
                        ...current,
                        [row.blob_path]: event.target.checked,
                      }))
                    }
                  />
                ),
              },
              { key: "file_name", label: "File Name" },
              { key: "extension", label: "Type" },
              {
                key: "size",
                label: "Size",
                render: (value: string) => fileSizeLabel(value),
              },
              {
                key: "last_modified",
                label: "Last Modified",
                render: (value: string) => formatDate(value),
              },
              { key: "status", label: "Status" },
            ]}
            rows={state?.source_files || []}
          />
        </ContentCard>

        <ContentCard title="XL Processing Jobs">
          <DataTable
            columns={[
              { key: "job_id", label: "Job ID" },
              { key: "status", label: "Status" },
              { key: "message", label: "Message" },
              {
                key: "updated_at",
                label: "Updated",
                render: (value: string) => formatDate(value),
              },
              {
                key: "actions",
                label: "Actions",
                render: (_: any, row: XlJob) =>
                  row.status === "header_review_required" && row.extracted_headers?.length ? (
                    <button
                      className="rounded-md bg-emerald-700 px-2 py-1 text-xs text-white"
                      onClick={() => {
                        setActiveHeaderJob(row);
                        setHeaderRows(row.extracted_headers || []);
                      }}
                    >
                      Open Header Review
                    </button>
                  ) : null,
              },
            ]}
            rows={state?.jobs || []}
          />
        </ContentCard>

        <ContentCard title="Converted CSV Outputs">
          <div className="mb-3 flex flex-wrap gap-2">
            <button
              className="rounded-md bg-slate-800 px-3 py-2 text-sm text-white hover:bg-slate-700 disabled:opacity-50"
              onClick={() => toggleAllOutputCsvs(true)}
              disabled={!state?.output_csvs?.length}
            >
              Select All
            </button>

            <button
              className="rounded-md bg-slate-800 px-3 py-2 text-sm text-white hover:bg-slate-700 disabled:opacity-50"
              onClick={() => toggleAllOutputCsvs(false)}
              disabled={!state?.output_csvs?.length}
            >
              Clear
            </button>

            <button
              className="rounded-md bg-emerald-700 px-3 py-2 text-sm text-white hover:bg-emerald-600 disabled:opacity-50"
              onClick={mergeSelectedOutputs}
              disabled={!selectedOutputBlobPaths.length || busy}
            >
              Merge Selected CSVs
            </button>
          </div>

          <DataTable
            columns={[
              {
                key: "select",
                label: "",
                render: (_: any, row: SpreadsheetFile) => (
                  <input
                    type="checkbox"
                    checked={!!selectedOutputCsvs[row.blob_path]}
                    onChange={(event) =>
                      setSelectedOutputCsvs((current) => ({
                        ...current,
                        [row.blob_path]: event.target.checked,
                      }))
                    }
                  />
                ),
              },
              { key: "file_name", label: "CSV Name" },
              {
                key: "size",
                label: "Size",
                render: (value: string) => fileSizeLabel(value),
              },
              {
                key: "last_modified",
                label: "Last Modified",
                render: (value: string) => formatDate(value),
              },
            ]}
            rows={state?.output_csvs || []}
          />
        </ContentCard>

        <ContentCard title="Merged Outputs">
          <DataTable
            columns={[
              { key: "file_name", label: "Merged File" },
              { key: "blob_path", label: "Blob Path" },
              {
                key: "size",
                label: "Size",
                render: (value: string) => fileSizeLabel(value),
              },
              {
                key: "last_modified",
                label: "Last Modified",
                render: (value: string) => formatDate(value),
              },
            ]}
            rows={state?.merged_outputs || []}
          />
        </ContentCard>

        <ContentCard title="Needs Header Review">
          <DataTable
            columns={[
              { key: "file_name", label: "File Name" },
              { key: "blob_path", label: "Review Blob Path" },
              {
                key: "size",
                label: "Size",
                render: (value: string) => fileSizeLabel(value),
              },
              {
                key: "last_modified",
                label: "Last Modified",
                render: (value: string) => formatDate(value),
              },
            ]}
            rows={state?.needs_header_review || []}
          />
        </ContentCard>
      </PageContainer>
    </AppShell>
  );
}