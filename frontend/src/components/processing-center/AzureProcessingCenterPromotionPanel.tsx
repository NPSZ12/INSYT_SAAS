"use client";

import { useEffect, useMemo, useState } from "react";
import { apiGet, apiPost } from "../../lib/api";

type Workspace = "capture" | "discovery" | "summaries";

type StagedJobSummary = {
  job_id: string;
  tracked_job_id?: string;
  status?: string;
  completed_at?: string;
  doc_count?: number;
  ready_to_promote_count?: number;
  summary?: {
    source_file_count?: number;
    expanded_file_count?: number;
    unique_doc_count?: number;
    duplicate_doc_count?: number;
    ocr_page_count?: number;
    ocr_estimated_cost_usd?: number;
    estimated_azure_cost_usd?: number;
  };
};

type StagedDoc = {
  doc_id: string;
  original_filename?: string;
  extension?: string;
  source_bytes?: number;
  page_count?: number;
  requires_ocr?: boolean;
  is_duplicate?: boolean;
  is_denisted?: boolean;
  family_id?: string;
  native_staged_blob_path?: string;
  text_staged_blob_path?: string;
  native_staged_bytes?: number;
  text_staged_bytes?: number;
  final_native_blob_path?: string;
  final_text_blob_path?: string;
  ready_to_promote?: boolean;
};

type StagedJobDetail = {
  workspace: Workspace;
  client: string;
  project: string;
  job_id: string;
  storage_account?: string;
  container?: string;
  staged_prefix?: string;
  native_prefix?: string;
  text_prefix?: string;
  doc_count?: number;
  ready_to_promote_count?: number;
  docs?: StagedDoc[];
  summary?: StagedJobSummary["summary"];
};

type PromotionResult = {
  promoted_count?: number;
  skipped_count?: number;
  promoted?: Array<{
    doc_id?: string;
    status?: string;
  }>;
  skipped?: Array<{
    doc_id?: string;
    status?: string;
    message?: string;
    native_destination_exists?: boolean;
    text_destination_exists?: boolean;
  }>;
};

type Props = {
  workspace: Workspace;
  clientId: string;
  projectId: string;
  onPromoted?: () => void | Promise<void>;
};

function formatDateTime(value?: string) {
  if (!value) return "—";

  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
}

function formatBytes(value?: number) {
  const bytes = Number(value || 0);

  if (bytes < 1024) return `${bytes} bytes`;

  const kb = bytes / 1024;
  if (kb < 1024) return `${kb.toFixed(1)} KB`;

  const mb = kb / 1024;
  if (mb < 1024) return `${mb.toFixed(2)} MB`;

  const gb = mb / 1024;
  return `${gb.toFixed(2)} GB`;
}

function cleanError(message: string) {
  try {
    const parsed = JSON.parse(message);
    return parsed?.detail || message;
  } catch {
    return message;
  }
}

function getStoredUser() {
  try {
    const raw = localStorage.getItem("insyt_user");
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function isInsytAdmin() {
  const user = getStoredUser();

  const roleValues = [
    user?.role,
    user?.user_role,
    user?.access_role,
    user?.type,
    ...(Array.isArray(user?.roles) ? user.roles : []),
  ]
    .filter(Boolean)
    .map((value) => String(value).toLowerCase());

  return roleValues.some(
    (role) =>
      role === "insyt admin" ||
      role === "insyt_admin" ||
      role === "super admin"
  );
}

export default function AzureProcessingCenterPromotionPanel({
  workspace,
  clientId,
  projectId,
  onPromoted,
}: Props) {
  const [jobs, setJobs] = useState<StagedJobSummary[]>([]);
  const [selectedJobId, setSelectedJobId] = useState("");
  const [selectedJob, setSelectedJob] = useState<StagedJobDetail | null>(null);
  const [selectedDocIds, setSelectedDocIds] = useState<string[]>([]);
  const [promotionResult, setPromotionResult] =
    useState<PromotionResult | null>(null);
  const [loadingJobs, setLoadingJobs] = useState(false);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [promoting, setPromoting] = useState(false);
  const [error, setError] = useState("");

  const stagedJobsUrl = useMemo(
    () =>
      `/api/${workspace}/processing-center/staged-results?client=${encodeURIComponent(
        clientId
      )}&project=${encodeURIComponent(projectId)}`,
    [workspace, clientId, projectId]
  );

  function stagedJobDetailUrl(jobId: string) {
    return (
      `/api/${workspace}/processing-center/staged-results/${encodeURIComponent(
        jobId
      )}` +
      `?client=${encodeURIComponent(clientId)}` +
      `&project=${encodeURIComponent(projectId)}`
    );
  }

  const docs = selectedJob?.docs || [];
  const readyDocs = docs.filter((doc) => doc.ready_to_promote);

  function toggleDoc(docId: string) {
    setSelectedDocIds((current) =>
      current.includes(docId)
        ? current.filter((item) => item !== docId)
        : [...current, docId]
    );
  }

  function selectAllReadyDocs() {
    setSelectedDocIds(readyDocs.map((doc) => doc.doc_id));
  }

  function clearSelection() {
    setSelectedDocIds([]);
  }

  async function refreshStagedJobs() {
    setLoadingJobs(true);
    setError("");

    try {
      const data = (await apiGet(stagedJobsUrl)) as {
        jobs?: StagedJobSummary[];
      };

      const nextJobs = data.jobs || [];
      setJobs(nextJobs);

      if (!selectedJobId && nextJobs.length > 0) {
        await loadStagedJob(nextJobs[0].job_id);
      }

      if (
        selectedJobId &&
        !nextJobs.some((job) => job.job_id === selectedJobId)
      ) {
        setSelectedJobId("");
        setSelectedJob(null);
        setSelectedDocIds([]);
      }
    } catch (err: any) {
      setError(cleanError(err?.message || "Unable to load staged results."));
    } finally {
      setLoadingJobs(false);
    }
  }

  async function loadStagedJob(jobId: string) {
    if (!jobId) return;

    setLoadingDetail(true);
    setError("");
    setPromotionResult(null);

    try {
      const data = (await apiGet(stagedJobDetailUrl(jobId))) as StagedJobDetail;

      setSelectedJobId(jobId);
      setSelectedJob(data);
      setSelectedDocIds([]);
    } catch (err: any) {
      setError(cleanError(err?.message || "Unable to load staged job."));
    } finally {
      setLoadingDetail(false);
    }
  }

  async function promoteDocs(promoteAll: boolean) {
    if (!isInsytAdmin()) {
      setError("Only INSYT Admin users can promote staged APC results.");
      return;
    }

    if (!selectedJobId) {
      setError("Select a staged processing job before promoting.");
      return;
    }

    if (!promoteAll && selectedDocIds.length === 0) {
      setError("Select at least one staged document to promote.");
      return;
    }

    setPromoting(true);
    setError("");
    setPromotionResult(null);

    try {
      const result = (await apiPost(
        `/api/${workspace}/processing-center/promote`,
        {
          client: clientId,
          project: projectId,
          job_id: selectedJobId,
          doc_ids: promoteAll ? [] : selectedDocIds,
          promote_all: promoteAll,
          overwrite: false,
        }
      )) as PromotionResult;

      setPromotionResult(result);
      setSelectedDocIds([]);

      await loadStagedJob(selectedJobId);
      await refreshStagedJobs();

      if (onPromoted) {
        await onPromoted();
      }
    } catch (err: any) {
      setError(cleanError(err?.message || "Unable to promote staged results."));
    } finally {
      setPromoting(false);
    }
  }

  useEffect(() => {
    refreshStagedJobs();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stagedJobsUrl]);

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="font-medium">Processed Results / Promotion Landing</div>
          <div className="mt-1 text-sm text-slate-400">
            Review staged APC Native/Text outputs before promoting them into live
            project source folders.
          </div>
        </div>

        <button
          type="button"
          onClick={refreshStagedJobs}
          disabled={loadingJobs}
          className="inline-flex h-9 min-w-[150px] items-center justify-center whitespace-nowrap rounded-full border border-blue-400/60 bg-blue-500/10 px-4 text-xs font-semibold text-blue-200 shadow-sm transition hover:-translate-y-0.5 hover:border-blue-300 hover:bg-blue-500/20 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
        >
          {loadingJobs ? "Refreshing..." : "Refresh Processed Results"}
        </button>
      </div>

      {error ? (
        <div className="mb-3 rounded-xl border border-red-500/40 bg-red-950/40 p-3 text-sm text-red-200">
          {error}
        </div>
      ) : null}

      {promotionResult ? (
        <div className="mb-3 rounded-xl border border-emerald-400/30 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-100">
          Promoted {promotionResult.promoted_count ?? 0} doc(s). Skipped{" "}
          {promotionResult.skipped_count ?? 0} doc(s).
        </div>
      ) : null}

      {jobs.length === 0 ? (
        <div className="rounded-xl border border-slate-800 bg-slate-950 px-4 py-4 text-sm text-slate-500">
          No staged review-ready documents are waiting for promotion.
        </div>
      ) : (
        <div className="grid gap-4 lg:grid-cols-[360px_1fr]">
          <div className="space-y-2">
            {jobs.map((job) => {
              const selected = job.job_id === selectedJobId;

              return (
                <button
                  key={job.job_id}
                  type="button"
                  onClick={() => loadStagedJob(job.job_id)}
                  className={`w-full rounded-xl border px-4 py-3 text-left text-sm transition ${
                    selected
                      ? "border-violet-400/70 bg-violet-500/15"
                      : "border-slate-800 bg-slate-950 hover:border-slate-600"
                  }`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="font-semibold text-slate-100">
                      {job.job_id}
                    </div>
                    <div className="rounded-full border border-emerald-400/40 bg-emerald-500/10 px-2 py-0.5 text-xs font-semibold text-emerald-200">
                      {job.status || "unknown"}
                    </div>
                  </div>

                  <div className="mt-1 text-xs text-slate-500">
                    Completed: {formatDateTime(job.completed_at)}
                  </div>

                  <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
                    <div className="rounded-lg bg-slate-900 px-2 py-1">
                      <div className="text-slate-500">Docs</div>
                      <div className="font-semibold text-slate-100">
                        {job.doc_count ?? 0}
                      </div>
                    </div>
                    <div className="rounded-lg bg-slate-900 px-2 py-1">
                      <div className="text-slate-500">Ready</div>
                      <div className="font-semibold text-emerald-100">
                        {job.ready_to_promote_count ?? 0}
                      </div>
                    </div>
                  </div>
                </button>
              );
            })}
          </div>

          <div className="rounded-xl border border-slate-800 bg-slate-950 p-4">
            {!selectedJob ? (
              <div className="text-sm text-slate-500">
                Select a staged job to review documents.
              </div>
            ) : (
              <>
                <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <div className="font-semibold text-slate-100">
                      {selectedJob.job_id}
                    </div>
                    <div className="mt-1 break-all text-xs text-slate-500">
                      {selectedJob.staged_prefix}
                    </div>
                  </div>

                  <div className="flex flex-wrap gap-2">
                    <button
                      type="button"
                      onClick={selectAllReadyDocs}
                      disabled={readyDocs.length === 0 || promoting}
                      className="inline-flex h-9 items-center justify-center rounded-full border border-slate-500/60 bg-slate-800/70 px-4 text-xs font-semibold text-slate-100 transition hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      Select All Ready
                    </button>

                    <button
                      type="button"
                      onClick={clearSelection}
                      disabled={selectedDocIds.length === 0 || promoting}
                      className="inline-flex h-9 items-center justify-center rounded-full border border-slate-500/60 bg-slate-800/70 px-4 text-xs font-semibold text-slate-100 transition hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      Clear
                    </button>

                    <button
                      type="button"
                      onClick={() => promoteDocs(false)}
                      disabled={
                        promoting ||
                        selectedDocIds.length === 0 ||
                        !isInsytAdmin()
                      }
                      className="inline-flex h-9 items-center justify-center rounded-full border border-emerald-400/60 bg-emerald-500/15 px-4 text-xs font-semibold text-emerald-100 shadow-sm transition hover:-translate-y-0.5 hover:border-emerald-300 hover:bg-emerald-500/25 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {promoting ? "Promoting..." : "Promote Selected"}
                    </button>

                    <button
                      type="button"
                      onClick={() => promoteDocs(true)}
                      disabled={
                        promoting ||
                        readyDocs.length === 0 ||
                        !isInsytAdmin()
                      }
                      className="inline-flex h-9 items-center justify-center rounded-full border border-violet-400/60 bg-violet-500/20 px-4 text-xs font-semibold text-violet-100 shadow-sm transition hover:-translate-y-0.5 hover:border-violet-300 hover:bg-violet-500/30 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {promoting ? "Promoting..." : "Promote All Review-Ready"}
                    </button>
                  </div>
                </div>

                <div className="mb-3 grid gap-2 md:grid-cols-6">
                  <div className="rounded-lg bg-slate-900 px-3 py-2">
                    <div className="text-xs text-slate-500">Docs</div>
                    <div className="font-semibold text-slate-100">
                      {selectedJob.doc_count ?? 0}
                    </div>
                  </div>
                  <div className="rounded-lg bg-slate-900 px-3 py-2">
                    <div className="text-xs text-slate-500">Ready</div>
                    <div className="font-semibold text-emerald-100">
                      {selectedJob.ready_to_promote_count ?? 0}
                    </div>
                  </div>
                  <div className="rounded-lg bg-slate-900 px-3 py-2">
                    <div className="text-xs text-slate-500">OCR pages</div>
                    <div className="font-semibold text-slate-100">
                      {selectedJob.summary?.ocr_page_count ?? "—"}
                    </div>
                  </div>
                  <div className="rounded-lg bg-slate-900 px-3 py-2">
                    <div className="text-xs text-slate-500">OCR quote</div>
                    <div className="font-semibold text-violet-100">
                      {typeof selectedJob.summary?.ocr_estimated_cost_usd ===
                      "number"
                        ? `$${selectedJob.summary.ocr_estimated_cost_usd.toFixed(
                            6
                          )}`
                        : "—"}
                    </div>
                  </div>
                  <div className="rounded-lg bg-slate-900 px-3 py-2">
                    <div className="text-xs text-slate-500">Azure quote</div>
                    <div className="font-semibold text-slate-100">
                      {typeof selectedJob.summary?.estimated_azure_cost_usd ===
                      "number"
                        ? `$${selectedJob.summary.estimated_azure_cost_usd.toFixed(
                            6
                          )}`
                        : "—"}
                    </div>
                  </div>
                  <div className="rounded-lg bg-slate-900 px-3 py-2">
                    <div className="text-xs text-slate-500">Selected</div>
                    <div className="font-semibold text-slate-100">
                      {selectedDocIds.length}
                    </div>
                  </div>
                </div>

                {loadingDetail ? (
                  <div className="text-sm text-slate-500">
                    Loading staged documents...
                  </div>
                ) : docs.length === 0 ? (
                  <div className="text-sm text-slate-500">
                    No staged documents found for this job.
                  </div>
                ) : (
                  <div className="max-h-[420px] overflow-auto rounded-xl border border-slate-800">
                    <table className="min-w-full text-left text-xs">
                      <thead className="sticky top-0 bg-slate-900 text-slate-400">
                        <tr>
                          <th className="px-3 py-2">Select</th>
                          <th className="px-3 py-2">Doc ID</th>
                          <th className="px-3 py-2">Original File</th>
                          <th className="px-3 py-2">Ext</th>
                          <th className="px-3 py-2">Pages</th>
                          <th className="px-3 py-2">OCR</th>
                          <th className="px-3 py-2">Ready</th>
                          <th className="px-3 py-2">Size</th>
                        </tr>
                      </thead>
                      <tbody>
                        {docs.map((doc) => (
                          <tr
                            key={doc.doc_id}
                            className="border-t border-slate-800 bg-slate-950"
                          >
                            <td className="px-3 py-2">
                              <input
                                type="checkbox"
                                checked={selectedDocIds.includes(doc.doc_id)}
                                disabled={!doc.ready_to_promote || promoting}
                                onChange={() => toggleDoc(doc.doc_id)}
                                className="h-4 w-4 rounded border-slate-500 bg-slate-950"
                              />
                            </td>
                            <td className="whitespace-nowrap px-3 py-2 font-semibold text-slate-100">
                              {doc.doc_id}
                            </td>
                            <td className="max-w-[280px] truncate px-3 py-2 text-slate-300">
                              {doc.original_filename || "—"}
                            </td>
                            <td className="px-3 py-2 text-slate-400">
                              {doc.extension || "—"}
                            </td>
                            <td className="px-3 py-2 text-slate-400">
                              {doc.page_count ?? "—"}
                            </td>
                            <td className="px-3 py-2 text-slate-400">
                              {doc.requires_ocr ? "Yes" : "No"}
                            </td>
                            <td className="px-3 py-2">
                              <span
                                className={`rounded-full border px-2 py-0.5 font-semibold ${
                                  doc.ready_to_promote
                                    ? "border-emerald-400/40 bg-emerald-500/10 text-emerald-200"
                                    : "border-amber-400/40 bg-amber-500/10 text-amber-200"
                                }`}
                              >
                                {doc.ready_to_promote ? "Ready" : "Missing Pair"}
                              </span>
                            </td>
                            <td className="whitespace-nowrap px-3 py-2 text-slate-400">
                              {formatBytes(doc.source_bytes)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}

                {promotionResult?.skipped?.length ? (
                  <div className="mt-3 rounded-xl border border-amber-400/30 bg-amber-500/10 px-4 py-3 text-xs text-amber-100">
                    <div className="mb-2 font-semibold">Promotion notices</div>
                    <div className="space-y-1">
                      {promotionResult.skipped.map((item, index) => (
                        <div key={`${item.doc_id}-${index}`}>
                          {item.doc_id}: {item.status}
                          {item.message ? ` — ${item.message}` : ""}
                        </div>
                      ))}
                    </div>
                  </div>
                ) : null}
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}