"use client";

import {
  Suspense,
  useEffect,
  useMemo,
  useState,
  type Dispatch,
  type SetStateAction,
} from "react";

import { useSearchParams } from "next/navigation";

import AppShell from "../../../../components/AppShell";
import PageContainer from "../../../../components/PageContainer";
import PageHeader from "../../../../components/PageHeader";
import ContentCard from "../../../../components/ContentCard";
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
  in_progress_files: SpreadsheetFile[];
  completed_files: SpreadsheetFile[];
  headers_row_1_csvs: SpreadsheetFile[];
  no_headers_row_1_csvs: SpreadsheetFile[];
  output_csvs: SpreadsheetFile[];
  merged_outputs: SpreadsheetFile[];
  needs_header_review: SpreadsheetFile[];
  deleted_files: SpreadsheetFile[];
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

function EmptyTableRow({ colSpan, message }: { colSpan: number; message: string }) {
  return (
    <tr>
      <td colSpan={colSpan} className="px-3 py-4 text-center text-sm text-slate-500">
        {message}
      </td>
    </tr>
  );
}

function SourceFilesTable({
  files,
  selectedSourceFiles,
  setSelectedSourceFiles,
  isAdmin,
}: {
  files: SpreadsheetFile[];
  selectedSourceFiles: Record<string, boolean>;
  setSelectedSourceFiles: Dispatch<SetStateAction<Record<string, boolean>>>;
  isAdmin: boolean;
}) {
  return (
    <div className="max-h-72 overflow-auto rounded-md border border-slate-800">
      <table className="w-full text-left text-sm">
        <thead className="bg-slate-900 text-slate-300">
          <tr>
            {isAdmin ? <th className="px-3 py-2"></th> : null}
            <th className="px-3 py-2">File Name</th>
            <th className="px-3 py-2">Type</th>
            <th className="px-3 py-2">Size</th>
            <th className="px-3 py-2">Last Modified</th>
            <th className="px-3 py-2">Status</th>
          </tr>
        </thead>

        <tbody>
          {files.length ? (
            files.map((file) => (
              <tr key={file.blob_path} className="border-t border-slate-800">
                {isAdmin ? (
                  <td className="px-3 py-2">
                    <input
                      type="checkbox"
                      checked={!!selectedSourceFiles[file.blob_path]}
                      onChange={(event) =>
                        setSelectedSourceFiles((current) => ({
                          ...current,
                          [file.blob_path]: event.target.checked,
                        }))
                      }
                    />
                  </td>
                ) : null}
                <td className="px-3 py-2 text-slate-100">{file.file_name}</td>
                <td className="px-3 py-2 text-slate-300">{file.extension || ""}</td>
                <td className="px-3 py-2 text-slate-300">{fileSizeLabel(file.size)}</td>
                <td className="px-3 py-2 text-slate-300">{formatDate(file.last_modified)}</td>
                <td className="px-3 py-2 text-slate-300">{file.status || ""}</td>
              </tr>
            ))
          ) : (
            <EmptyTableRow colSpan={isAdmin ? 6 : 5} message="No source XL or CSV files found." />
          )}
        </tbody>
      </table>
    </div>
  );
}

function JobsTable({
  jobs,
  onOpenHeaderReview,
}: {
  jobs: XlJob[];
  onOpenHeaderReview: (job: XlJob) => void | Promise<void>;
}) {
  return (
    <div className="max-h-72 overflow-auto rounded-md border border-slate-800">
      <table className="w-full text-left text-sm">
        <thead className="bg-slate-900 text-slate-300">
          <tr>
            <th className="px-3 py-2">Job ID</th>
            <th className="px-3 py-2">Status</th>
            <th className="px-3 py-2">Message</th>
            <th className="px-3 py-2">Updated</th>
            <th className="px-3 py-2">Actions</th>
          </tr>
        </thead>

        <tbody>
          {jobs.length ? (
            jobs.map((job) => (
              <tr key={job.job_id} className="border-t border-slate-800">
                <td className="px-3 py-2 font-mono text-xs text-slate-200">{job.job_id}</td>
                <td className="px-3 py-2 text-slate-300">{job.status}</td>
                <td className="px-3 py-2 text-slate-300">{job.message || ""}</td>
                <td className="px-3 py-2 text-slate-300">{formatDate(job.updated_at)}</td>
                <td className="px-3 py-2">
                  {job.status === "header_review_required" && job.extracted_headers?.length ? (
                    <button
                      className="rounded-md bg-emerald-700 px-2 py-1 text-xs text-white hover:bg-emerald-600"
                      onClick={() => onOpenHeaderReview(job)}
                    >
                      Open Header Review
                    </button>
                  ) : null}
                </td>
              </tr>
            ))
          ) : (
            <EmptyTableRow colSpan={5} message="No XL Processing jobs found." />
          )}
        </tbody>
      </table>
    </div>
  );
}

function OutputCsvsTable({
  files,
  selectedOutputCsvs,
  setSelectedOutputCsvs,
}: {
  files: SpreadsheetFile[];
  selectedOutputCsvs: Record<string, boolean>;
  setSelectedOutputCsvs: React.Dispatch<React.SetStateAction<Record<string, boolean>>>;
}) {
  return (
    <div className="max-h-72 overflow-auto rounded-md border border-slate-800">
      <table className="w-full text-left text-sm">
        <thead className="bg-slate-900 text-slate-300">
          <tr>
            <th className="px-3 py-2"></th>
            <th className="px-3 py-2">CSV Name</th>
            <th className="px-3 py-2">Size</th>
            <th className="px-3 py-2">Last Modified</th>
          </tr>
        </thead>

        <tbody>
          {files.length ? (
            files.map((file) => (
              <tr key={file.blob_path} className="border-t border-slate-800">
                <td className="px-3 py-2">
                  <input
                    type="checkbox"
                    checked={!!selectedOutputCsvs[file.blob_path]}
                    onChange={(event) =>
                      setSelectedOutputCsvs((current) => ({
                        ...current,
                        [file.blob_path]: event.target.checked,
                      }))
                    }
                  />
                </td>
                <td className="px-3 py-2 text-slate-100">{file.file_name}</td>
                <td className="px-3 py-2 text-slate-300">{fileSizeLabel(file.size)}</td>
                <td className="px-3 py-2 text-slate-300">{formatDate(file.last_modified)}</td>
              </tr>
            ))
          ) : (
            <EmptyTableRow colSpan={4} message="No converted CSV outputs found." />
          )}
        </tbody>
      </table>
    </div>
  );
}

function SimpleFilesTable({
  files,
  emptyMessage,
  pathLabel,
  onOpenFile,
}: {
  files: SpreadsheetFile[];
  emptyMessage: string;
  pathLabel: string;
  onOpenFile?: (blobPath: string) => void;
}) {
  return (
    <div className="max-h-72 overflow-auto rounded-md border border-slate-800">
      <table className="w-full text-left text-sm">
        <thead className="bg-slate-900 text-slate-300">
          <tr>
            <th className="px-3 py-2">File Name</th>
            <th className="px-3 py-2">{pathLabel}</th>
            <th className="px-3 py-2">Size</th>
            <th className="px-3 py-2">Last Modified</th>
            {onOpenFile ? <th className="px-3 py-2">Actions</th> : null}
          </tr>
        </thead>

        <tbody>
          {files.length ? (
            files.map((file) => (
              <tr key={file.blob_path} className="border-t border-slate-800">
                <td className="px-3 py-2 text-slate-100">{file.file_name}</td>
                <td className="px-3 py-2 font-mono text-xs text-slate-400">
                  {file.blob_path}
                </td>
                <td className="px-3 py-2 text-slate-300">{fileSizeLabel(file.size)}</td>
                <td className="px-3 py-2 text-slate-300">{formatDate(file.last_modified)}</td>
                {onOpenFile ? (
                  <td className="px-3 py-2">
                    <button
                      className="rounded-md bg-slate-800 px-2 py-1 text-xs text-white hover:bg-slate-700"
                      onClick={() => onOpenFile(file.blob_path)}
                    >
                      Open
                    </button>
                  </td>
                ) : null}
              </tr>
            ))
          ) : (
            <EmptyTableRow colSpan={onOpenFile ? 5 : 4} message={emptyMessage} />
          )}
        </tbody>
      </table>
    </div>
  );
}

function DeletedFilesTable({
  files,
  selectedDeletedFiles,
  setSelectedDeletedFiles,
  isAdmin,
}: {
  files: SpreadsheetFile[];
  selectedDeletedFiles: Record<string, boolean>;
  setSelectedDeletedFiles: Dispatch<SetStateAction<Record<string, boolean>>>;
  isAdmin: boolean;
}) {
  return (
    <div className="max-h-72 overflow-auto rounded-md border border-slate-800">
      <table className="w-full text-left text-sm">
        <thead className="bg-slate-900 text-slate-300">
          <tr>
            {isAdmin ? <th className="px-3 py-2"></th> : null}
            <th className="px-3 py-2">File Name</th>
            <th className="px-3 py-2">Type</th>
            <th className="px-3 py-2">Deleted Blob Path</th>
            <th className="px-3 py-2">Size</th>
            <th className="px-3 py-2">Last Modified</th>
          </tr>
        </thead>

        <tbody>
          {files.length ? (
            files.map((file) => (
              <tr key={file.blob_path} className="border-t border-slate-800">
                {isAdmin ? (
                  <td className="px-3 py-2">
                    <input
                      type="checkbox"
                      checked={!!selectedDeletedFiles[file.blob_path]}
                      onChange={(event) =>
                        setSelectedDeletedFiles((current) => ({
                          ...current,
                          [file.blob_path]: event.target.checked,
                        }))
                      }
                    />
                  </td>
                ) : null}

                <td className="px-3 py-2 text-slate-100">{file.file_name}</td>
                <td className="px-3 py-2 text-slate-300">{file.extension || ""}</td>
                <td className="px-3 py-2 font-mono text-xs text-slate-400">
                  {file.blob_path}
                </td>
                <td className="px-3 py-2 text-slate-300">{fileSizeLabel(file.size)}</td>
                <td className="px-3 py-2 text-slate-300">{formatDate(file.last_modified)}</td>
              </tr>
            ))
          ) : (
            <EmptyTableRow colSpan={isAdmin ? 6 : 5} message="No deleted spreadsheet files found." />
          )}
        </tbody>
      </table>
    </div>
  );
}

function WorkflowFilesTable({
  files,
  selectedFiles,
  setSelectedFiles,
  isAdmin,
  emptyMessage,
}: {
  files: SpreadsheetFile[];
  selectedFiles?: Record<string, boolean>;
  setSelectedFiles?: Dispatch<SetStateAction<Record<string, boolean>>>;
  isAdmin?: boolean;
  emptyMessage: string;
}) {
  const showCheckboxes = Boolean(isAdmin && selectedFiles && setSelectedFiles);

  return (
    <div className="max-h-72 overflow-auto rounded-md border border-slate-800">
      <table className="w-full text-left text-sm">
        <thead className="bg-slate-900 text-slate-300">
          <tr>
            {showCheckboxes ? <th className="px-3 py-2"></th> : null}
            <th className="px-3 py-2">File Name</th>
            <th className="px-3 py-2">Type</th>
            <th className="px-3 py-2">Blob Path</th>
            <th className="px-3 py-2">Size</th>
            <th className="px-3 py-2">Last Modified</th>
            <th className="px-3 py-2">Status</th>
          </tr>
        </thead>

        <tbody>
          {files.length ? (
            files.map((file) => (
              <tr key={file.blob_path} className="border-t border-slate-800">
                {showCheckboxes ? (
                  <td className="px-3 py-2">
                    <input
                      type="checkbox"
                      checked={!!selectedFiles?.[file.blob_path]}
                      onChange={(event) =>
                        setSelectedFiles?.((current) => ({
                          ...current,
                          [file.blob_path]: event.target.checked,
                        }))
                      }
                    />
                  </td>
                ) : null}

                <td className="px-3 py-2 text-slate-100">{file.file_name}</td>
                <td className="px-3 py-2 text-slate-300">{file.extension || ""}</td>
                <td className="px-3 py-2 font-mono text-xs text-slate-400">
                  {file.blob_path}
                </td>
                <td className="px-3 py-2 text-slate-300">{fileSizeLabel(file.size)}</td>
                <td className="px-3 py-2 text-slate-300">{formatDate(file.last_modified)}</td>
                <td className="px-3 py-2 text-slate-300">{file.status || ""}</td>
              </tr>
            ))
          ) : (
            <EmptyTableRow
              colSpan={showCheckboxes ? 7 : 6}
              message={emptyMessage}
            />
          )}
        </tbody>
      </table>
    </div>
  );
}

function normalizeHeaderText(value: string) {
  return String(value || "")
    .trim()
    .toLowerCase()
    .replace(/[_-]/g, " ")
    .replace(/[^a-z0-9 ]+/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

function bestHeaderOptionMatch(sourceHeader: string, options: string[]) {
  const normalizedSource = normalizeHeaderText(sourceHeader);

  if (!normalizedSource || !options.length) {
    return sourceHeader || "";
  }

  const exact = options.find(
    (option) => normalizeHeaderText(option) === normalizedSource
  );

  if (exact) {
    return exact;
  }

  let best = "";
  let bestScore = 0;

  for (const option of options) {
    const normalizedOption = normalizeHeaderText(option);

    if (!normalizedOption) continue;

    let score = 0;

    if (normalizedOption.includes(normalizedSource)) {
      score = normalizedSource.length / normalizedOption.length;
    } else if (normalizedSource.includes(normalizedOption)) {
      score = normalizedOption.length / normalizedSource.length;
    } else {
      const sourceParts = new Set(normalizedSource.split(" "));
      const optionParts = normalizedOption.split(" ");
      const overlap = optionParts.filter((part) => sourceParts.has(part)).length;
      score = overlap / Math.max(sourceParts.size, optionParts.length);
    }

    if (score > bestScore) {
      bestScore = score;
      best = option;
    }
  }

  return bestScore >= 0.5 ? best : sourceHeader || "";
}

function normalizeHeaderReviewRows(
  rows: HeaderReviewRow[],
  options: string[]
): HeaderReviewRow[] {
  return rows.map((row) => {
    const suggested =
      row.suggested_header ||
      bestHeaderOptionMatch(row.source_header, options);

    const finalHeader =
      row.final_header ||
      suggested ||
      bestHeaderOptionMatch(row.source_header, options);

    return {
      ...row,
      suggested_header: suggested,
      final_header: finalHeader,
    };
  });
}

function SpreadsheetProcessingCenterPageContent() {
  const searchParams = useSearchParams();

  const clientId = searchParams.get("client") || "";
  const projectId = searchParams.get("project") || "";
  const workspace = "capture";

  const storedUser =
    typeof window !== "undefined"
      ? window.localStorage.getItem("insyt_user")
      : null;

  const currentUser = storedUser ? JSON.parse(storedUser) : null;

  const isAdmin =
    currentUser?.role === "Admin" ||
    currentUser?.role === "INSYT Admin";

  const [state, setState] = useState<XlProcessingCenterState | null>(null);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  const [selectedSourceFiles, setSelectedSourceFiles] = useState<Record<string, boolean>>({});
  const [selectedOutputCsvs, setSelectedOutputCsvs] = useState<Record<string, boolean>>({});

  const [selectedDeletedFiles, setSelectedDeletedFiles] = useState<Record<string, boolean>>({});
  const [selectedCompletedFiles, setSelectedCompletedFiles] = useState<Record<string, boolean>>({});

  const [activeHeaderJob, setActiveHeaderJob] = useState<XlJob | null>(null);
  const [headerRows, setHeaderRows] = useState<HeaderReviewRow[]>([]);

  const [projectHeaderOptions, setProjectHeaderOptions] = useState<string[]>([]);
  const [headerLibraryMessage, setHeaderLibraryMessage] = useState("");

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

  const selectedDeletedBlobPaths = useMemo(
    () =>
      Object.entries(selectedDeletedFiles)
        .filter(([, selected]) => selected)
        .map(([blob]) => blob),
    [selectedDeletedFiles]
  );

  const selectedCompletedBlobPaths = useMemo(
    () =>
      Object.entries(selectedCompletedFiles)
        .filter(([, selected]) => selected)
        .map(([blob]) => blob),
    [selectedCompletedFiles]
  );

  async function loadProjectHeaderOptions() {
    if (!clientId || !projectId) {
      setProjectHeaderOptions([]);
      setHeaderLibraryMessage("");
      return [];
    }

    try {
      const data = await apiGet(
        `/api/cyber-utility/xl-processing/header-library?workspace=${encodeURIComponent(
          workspace
        )}&client=${encodeURIComponent(clientId)}&project=${encodeURIComponent(projectId)}`
      );

      const headers = Array.isArray(data.headers) ? data.headers : [];

      setProjectHeaderOptions(headers);
      setHeaderLibraryMessage(data.warning || "");

      return headers;
    } catch (err: any) {
      setProjectHeaderOptions([]);
      setHeaderLibraryMessage(err?.message || "Unable to load project header library.");
      return [];
    }
  }

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
      await loadProjectHeaderOptions();

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

  async function deleteSelectedSourceFiles() {
    if (!isAdmin) {
      setMessage("Only Admin users can delete spreadsheet source files.");
      return;
    }

    if (!selectedSourceBlobPaths.length) {
      setMessage("Select one or more source files to delete.");
      return;
    }

    const confirmed = window.confirm(
      `Delete ${selectedSourceBlobPaths.length} selected file(s) from the active Files view? They will be moved to Deleted Files for restore.`
    );

    if (!confirmed) return;

    setBusy(true);
    setMessage("");

    try {
      const result = await apiPost("/api/cyber-utility/xl-processing/delete-files", {
        workspace,
        client: clientId,
        project_id: projectId,
        selected_blob_paths: selectedSourceBlobPaths,
      });

      setMessage(result.message || "Selected files deleted.");
      setSelectedSourceFiles({});
      await refreshCenter();
    } catch (err: any) {
      setMessage(err?.message || "Failed to delete selected files.");
    } finally {
      setBusy(false);
    }
  }

  async function restoreSelectedDeletedFiles() {
    if (!isAdmin) {
      setMessage("Only Admin users can restore deleted spreadsheet files.");
      return;
    }

    if (!selectedDeletedBlobPaths.length) {
      setMessage("Select one or more deleted files to restore.");
      return;
    }

    const confirmed = window.confirm(
      `Reupload ${selectedDeletedBlobPaths.length} selected deleted file(s) back to the project source files?`
    );

    if (!confirmed) return;

    setBusy(true);
    setMessage("");

    try {
      const result = await apiPost("/api/cyber-utility/xl-processing/restore-files", {
        workspace,
        client: clientId,
        project_id: projectId,
        selected_blob_paths: selectedDeletedBlobPaths,
      });

      setMessage(result.message || "Selected deleted files restored.");
      setSelectedDeletedFiles({});
      await refreshCenter();
    } catch (err: any) {
      setMessage(err?.message || "Failed to restore selected files.");
    } finally {
      setBusy(false);
    }
  }

  async function reworkSelectedCompletedFiles() {
    if (!isAdmin) {
      setMessage("Only Admin users can move completed spreadsheet files back to In Progress.");
      return;
    }

    if (!selectedCompletedBlobPaths.length) {
      setMessage("Select one or more completed files to move back to In Progress.");
      return;
    }

    const confirmed = window.confirm(
      `Move ${selectedCompletedBlobPaths.length} completed file(s) back to In Progress for redo?`
    );

    if (!confirmed) return;

    setBusy(true);
    setMessage("");

    try {
      const result = await apiPost("/api/cyber-utility/xl-processing/rework-completed", {
        workspace,
        client: clientId,
        project_id: projectId,
        selected_blob_paths: selectedCompletedBlobPaths,
      });

      setMessage(result.message || "Selected completed files moved back to In Progress.");
      setSelectedCompletedFiles({});
      await refreshCenter();
    } catch (err: any) {
      setMessage(err?.message || "Failed to move completed files back to In Progress.");
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

          const options = await loadProjectHeaderOptions();
          const rows = normalizeHeaderReviewRows(job.extracted_headers || [], options);

          setActiveHeaderJob(job);
          setHeaderRows(rows);
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

  function toggleAllDeletedFiles(selected: boolean) {
    const next: Record<string, boolean> = {};

    for (const file of state?.deleted_files || []) {
      next[file.blob_path] = selected;
    }

    setSelectedDeletedFiles(next);
  }

  function toggleAllCompletedFiles(selected: boolean) {
    const next: Record<string, boolean> = {};

    for (const file of state?.completed_files || []) {
      next[file.blob_path] = selected;
    }

    setSelectedCompletedFiles(next);
  }

  function openMergedOutput(blobPath: string) {
    const url =
      `/api/cyber-utility/xl-processing/open-output?workspace=${encodeURIComponent(
        workspace
      )}&client=${encodeURIComponent(clientId)}&project=${encodeURIComponent(
        projectId
      )}&blob_path=${encodeURIComponent(blobPath)}`;

    window.open(url, "_blank", "noopener,noreferrer");
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
            {isAdmin ? (
              <>
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

                <button
                  className="rounded-md bg-red-700 px-3 py-2 text-sm text-white hover:bg-red-600 disabled:opacity-50"
                  onClick={deleteSelectedSourceFiles}
                  disabled={!selectedSourceBlobPaths.length || busy}
                >
                  Delete Files
                </button>
              </>
            ) : null}

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

            {headerLibraryMessage ? (
              <div className="mb-3 rounded-md border border-amber-700 bg-amber-950/40 px-3 py-2 text-sm text-amber-200">
                {headerLibraryMessage}
              </div>
            ) : null}

            <div className="max-h-72 overflow-auto rounded-md border border-slate-800">
              <table className="w-full text-left text-sm">
                <thead className="bg-slate-900 text-slate-300">
                  <tr>
                    <th className="px-3 py-2">Detected Header</th>
                    <th className="px-3 py-2">Suggested Header</th>
                    <th className="px-3 py-2">Final Header / Project Library</th>
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
                        <select
                          className="w-full rounded-md border border-slate-700 bg-slate-950 px-2 py-1 text-slate-100"
                          value={row.final_header || ""}
                          onChange={(event) => updateHeaderRow(index, event.target.value)}
                        >
                          <option value="">-- Select Header --</option>

                          {row.final_header &&
                          !projectHeaderOptions.includes(row.final_header) ? (
                            <option value={row.final_header}>{row.final_header}</option>
                          ) : null}

                          {projectHeaderOptions.map((header) => (
                            <option key={header} value={header}>
                              {header}
                            </option>
                          ))}
                        </select>
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
          <SourceFilesTable
            files={state?.source_files || []}
            selectedSourceFiles={selectedSourceFiles}
            setSelectedSourceFiles={setSelectedSourceFiles}
            isAdmin={isAdmin}
          />
        </ContentCard>

        <ContentCard title="In Progress">
          <WorkflowFilesTable
            files={state?.in_progress_files || []}
            emptyMessage="No spreadsheet files are currently in progress."
          />
        </ContentCard>

        <ContentCard title="Headers in Row 1">
          <SimpleFilesTable
            files={state?.headers_row_1_csvs || []}
            emptyMessage="No converted CSVs with headers in Row 1 found."
            pathLabel="CSV Blob Path"
          />
        </ContentCard>

        <ContentCard title="No Headers in Row 1">
          <SimpleFilesTable
            files={state?.no_headers_row_1_csvs || []}
            emptyMessage="No converted CSVs without headers in Row 1 found."
            pathLabel="CSV Blob Path"
          />
        </ContentCard>

        {isAdmin ? (
          <ContentCard title="Completed">
            <div className="mb-3 flex flex-wrap gap-2">
              <button
                className="rounded-md bg-slate-800 px-3 py-2 text-sm text-white hover:bg-slate-700 disabled:opacity-50"
                onClick={() => toggleAllCompletedFiles(true)}
                disabled={!state?.completed_files?.length}
              >
                Select All
              </button>

              <button
                className="rounded-md bg-slate-800 px-3 py-2 text-sm text-white hover:bg-slate-700 disabled:opacity-50"
                onClick={() => toggleAllCompletedFiles(false)}
                disabled={!state?.completed_files?.length}
              >
                Clear All
              </button>

              <button
                className="rounded-md bg-amber-700 px-3 py-2 text-sm text-white hover:bg-amber-600 disabled:opacity-50"
                onClick={reworkSelectedCompletedFiles}
                disabled={!selectedCompletedBlobPaths.length || busy}
              >
                Send Back to In Progress
              </button>
            </div>

            <WorkflowFilesTable
              files={state?.completed_files || []}
              selectedFiles={selectedCompletedFiles}
              setSelectedFiles={setSelectedCompletedFiles}
              isAdmin={isAdmin}
              emptyMessage="No completed spreadsheet files found."
            />
          </ContentCard>
        ) : (
          <ContentCard title="Completed">
            <WorkflowFilesTable
              files={state?.completed_files || []}
              emptyMessage="No completed spreadsheet files found."
            />
          </ContentCard>
        )}

        <ContentCard title="XL Processing Jobs">
          <JobsTable
            jobs={state?.jobs || []}
            onOpenHeaderReview={async (job) => {
              const options = await loadProjectHeaderOptions();
              setActiveHeaderJob(job);
              setHeaderRows(normalizeHeaderReviewRows(job.extracted_headers || [], options));
            }}
          />
        </ContentCard>

        <ContentCard title="Ready for Header Mapping / Merge">
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

          <OutputCsvsTable
            files={state?.output_csvs || []}
            selectedOutputCsvs={selectedOutputCsvs}
            setSelectedOutputCsvs={setSelectedOutputCsvs}
          />
        </ContentCard>

        <ContentCard title="Merged Outputs">
          <SimpleFilesTable
            files={state?.merged_outputs || []}
            emptyMessage="No merged outputs found."
            pathLabel="Blob Path"
            onOpenFile={openMergedOutput}
          />
        </ContentCard>

        <ContentCard title="Needs Header Review">
          <SimpleFilesTable
            files={state?.needs_header_review || []}
            emptyMessage="No files currently need header review."
            pathLabel="Review Blob Path"
          />
        </ContentCard>

        {isAdmin ? (
          <ContentCard title="Deleted Files">
            <div className="mb-3 flex flex-wrap gap-2">
              <button
                className="rounded-md bg-slate-800 px-3 py-2 text-sm text-white hover:bg-slate-700 disabled:opacity-50"
                onClick={() => toggleAllDeletedFiles(true)}
                disabled={!state?.deleted_files?.length}
              >
                Select All
              </button>

              <button
                className="rounded-md bg-slate-800 px-3 py-2 text-sm text-white hover:bg-slate-700 disabled:opacity-50"
                onClick={() => toggleAllDeletedFiles(false)}
                disabled={!state?.deleted_files?.length}
              >
                Clear All
              </button>

              <button
                className="rounded-md bg-emerald-700 px-3 py-2 text-sm text-white hover:bg-emerald-600 disabled:opacity-50"
                onClick={restoreSelectedDeletedFiles}
                disabled={!selectedDeletedBlobPaths.length || busy}
              >
                Reupload to Project
              </button>
            </div>

            <DeletedFilesTable
              files={state?.deleted_files || []}
              selectedDeletedFiles={selectedDeletedFiles}
              setSelectedDeletedFiles={setSelectedDeletedFiles}
              isAdmin={isAdmin}
            />
          </ContentCard>
        ) : null}
      </PageContainer>
    </AppShell>
  );
}

export default function SpreadsheetProcessingCenterPage() {
  return (
    <Suspense
      fallback={
        <AppShell>
          <PageContainer>
            <PageHeader
              title="Processing Center - Spreadsheets"
              subtitle="Loading spreadsheet processing center..."
            />
          </PageContainer>
        </AppShell>
      }
    >
      <SpreadsheetProcessingCenterPageContent />
    </Suspense>
  );
}