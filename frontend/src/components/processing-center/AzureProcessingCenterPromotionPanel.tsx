"use client";

import { useEffect, useMemo, useState } from "react";
import { apiGet, apiPost } from "../../lib/api";

type Workspace = "capture" | "discovery" | "summaries";

type StagedJobSummary = {
  job_id: string;
  tracked_job_id?: string;
  status?: string;
  promotion_status?: string;
  promotion_result?: string;
  promoted_at?: string;
  completed_at?: string;
  doc_count?: number;
  ready_to_promote_count?: number;
  promoted_count?: number;
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
  promotion_status?: string;
  promotion_result?: string;
  promoted_at?: string;
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
  error_count?: number;
  promotion_status?: string;
  message?: string;
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

type SummaryExtractionUploadResult = {
  uploaded_count?: number;
  skipped_count?: number;
  error_count?: number;
  message?: string;
  uploaded?: Array<{
    doc_id?: string;
    status?: string;
    native_destination?: string;
    text_destination?: string;
  }>;
  skipped?: Array<{
    doc_id?: string;
    status?: string;
    message?: string;
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

function isPromotedValue(value?: string) {
  const clean = String(value || "").toLowerCase().trim();

  return (
    clean === "promoted" ||
    clean === "already_promoted" ||
    clean === "already promoted"
  );
}

function isPromotedJob(job: StagedJobSummary) {
  return (
    isPromotedValue(job.promotion_status) ||
    isPromotedValue(job.promotion_result) ||
    Number(job.promoted_count || 0) > 0 ||
    (
      Number(job.ready_to_promote_count || 0) === 0 &&
      String(job.status || "").toLowerCase().includes("promoted")
    )
  );
}

function getJobStatusLabel(job: StagedJobSummary) {
  if (isPromotedJob(job)) return "Promoted";

  if (Number(job.ready_to_promote_count || 0) > 0) {
    return "Ready";
  }

  return job.status || "unknown";
}

function isPromotedDoc(doc: StagedDoc) {
  return (
    isPromotedValue(doc.promotion_status) ||
    isPromotedValue(doc.promotion_result) ||
    Boolean(doc.promoted_at)
  );
}

export default function AzureProcessingCenterPromotionPanel({
  workspace,
  clientId,
  projectId,
  onPromoted,
}: Props) {
  const isSummaries = workspace === "summaries";

  const [jobs, setJobs] = useState<StagedJobSummary[]>([]);
  const [selectedJobId, setSelectedJobId] = useState("");
  const [selectedJob, setSelectedJob] = useState<StagedJobDetail | null>(null);
  const [selectedDocIds, setSelectedDocIds] = useState<string[]>([]);
  const [promotionResult, setPromotionResult] =
    useState<PromotionResult | null>(null);
  const [summaryExtractionResult, setSummaryExtractionResult] =
    useState<SummaryExtractionUploadResult | null>(null);
  const [loadingJobs, setLoadingJobs] = useState(false);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [refreshingDetail, setRefreshingDetail] = useState(false);
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

  const readyDocs = docs.filter(
    (doc) => doc.ready_to_promote && !isPromotedDoc(doc)
  );

  const promotedDocs = docs.filter((doc) => isPromotedDoc(doc));

  const readyJobs = jobs.filter((job) => !isPromotedJob(job));

  const promotedJobs = jobs.filter((job) => isPromotedJob(job));

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

  async function loadStagedJob(
    jobId: string,
    isRefresh = false
  ) {
    if (!jobId) return;

    if (isRefresh) {
      setRefreshingDetail(true);
    } else {
      setLoadingDetail(true);
    }

    setError("");

    if (!isRefresh) {
      setPromotionResult(null);
      setSummaryExtractionResult(null);
    }

    try {
      const data =
        (await apiGet(
          stagedJobDetailUrl(jobId)
        )) as StagedJobDetail;

      setSelectedJobId(jobId);
      setSelectedJob(data);

      if (!isRefresh) {
        setSelectedDocIds([]);
      } else {
        const availableDocIds =
          new Set(
            (data.docs || []).map(
              (doc) => doc.doc_id
            )
          );

        setSelectedDocIds(
          (current) =>
            current.filter(
              (docId) =>
                availableDocIds.has(
                  docId
                )
            )
        );
      }

    } catch (err: any) {
      setError(
        cleanError(
          err?.message ||
            "Unable to load staged job."
        )
      );

    } finally {
      setLoadingDetail(false);
      setRefreshingDetail(false);
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
        `/api/${workspace}/processing-center/jobs/${encodeURIComponent(
          selectedJobId
        )}/promote`,
        {
          client: clientId,
          project_id: projectId,
          doc_ids: promoteAll ? [] : selectedDocIds,
          promote_all: promoteAll,
        }
      )) as PromotionResult;

      setPromotionResult(result);
      setSelectedDocIds([]);

      await loadStagedJob(
        selectedJobId,
        true
      );

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

  async function uploadToSummaryExtraction(uploadAll: boolean) {
    if (!isInsytAdmin()) {
      setError("Only INSYT Admin users can upload staged APC results to Summary Extraction.");
      return;
    }

    if (!selectedJobId) {
      setError("Select a staged processing job before uploading to Summary Extraction.");
      return;
    }

    if (!uploadAll && selectedDocIds.length === 0) {
      setError("Select at least one staged document to upload to Summary Extraction.");
      return;
    }

    setPromoting(true);
    setError("");
    setPromotionResult(null);
    setSummaryExtractionResult(null);

    try {
      const docsForExtraction = (uploadAll
        ? readyDocs
        : docs.filter((doc) => selectedDocIds.includes(doc.doc_id))
      ).map((doc) => ({
        doc_id: doc.doc_id,
        original_filename: doc.original_filename || "",
        native_staged_blob_path: doc.native_staged_blob_path || "",
        text_staged_blob_path: doc.text_staged_blob_path || "",
      }));

      const result = (await apiPost(
        "/api/summaries/processing-center/upload-to-summary-extraction",
        {
          client: clientId,
          project_id: projectId,
          job_id: selectedJobId,
          doc_ids: uploadAll ? [] : selectedDocIds,
          docs: docsForExtraction,
          upload_all: uploadAll,
        }
      )) as SummaryExtractionUploadResult;

      setSummaryExtractionResult(result);
      setSelectedDocIds([]);

      await loadStagedJob(
        selectedJobId,
        true
      );

      await refreshStagedJobs();

      if (onPromoted) {
        await onPromoted();
      }
    } catch (err: any) {
      setError(
        cleanError(
          err?.message || "Unable to upload staged results to Summary Extraction."
        )
      );
    } finally {
      setPromoting(false);
    }
  }

  useEffect(() => {
    refreshStagedJobs();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stagedJobsUrl]);

  return (
    <div className="insyt-pane">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="font-medium insyt-text-primary">
            {isSummaries
              ? "Processed Results / Summary Extraction Landing"
              : "Processed Results / Promotion Landing"}
          </div>
          <div className="mt-1 text-sm insyt-text-muted">
            {isSummaries
              ? "Review staged APC Native/Text outputs before uploading them into the Summaries extraction workflow."
              : "Review staged APC Native/Text outputs before promoting them into live project source folders."}
          </div>
        </div>

        <button
          type="button"
          onClick={refreshStagedJobs}
          disabled={loadingJobs}
          className="insyt-btn insyt-btn-secondary insyt-btn-sm"
        >
          {loadingJobs ? "Refreshing..." : "Refresh Processed Results"}
        </button>
      </div>

      {error ? (
        <div className="insyt-message insyt-message-danger mb-3">
          {error}
        </div>
      ) : null}

      {promotionResult ? (
        <div className="insyt-message insyt-message-success mb-3">
          Promotion completed. Promoted {promotionResult.promoted_count ?? 0} doc(s).{" "}
          {promotionResult.skipped_count ?? 0} already promoted / skipped.
        </div>
      ) : null}

      {summaryExtractionResult ? (
        <div className="insyt-message insyt-message-info mb-3">
          Summary Extraction upload completed. Uploaded{" "}
          {summaryExtractionResult.uploaded_count ?? 0} doc(s).{" "}
          {summaryExtractionResult.skipped_count ?? 0} skipped.
        </div>
      ) : null}

      {jobs.length === 0 ? (
        <div className="insyt-subpanel px-4 py-4 text-sm insyt-text-muted">
          No staged review-ready documents are waiting for promotion.
        </div>
      ) : (
        <div className="grid gap-4 lg:grid-cols-[360px_1fr]">
          <div className="space-y-4">
            <div>
              <div className="mb-2 text-xs font-semibold uppercase tracking-wide insyt-text-muted">
                {isSummaries ? "Ready for Summary Extraction" : "Ready for Promotion"}
              </div>

              {readyJobs.length === 0 ? (
                <div className="insyt-subpanel px-4 py-3 text-sm insyt-text-muted">
                  No jobs are currently ready for promotion.
                </div>
              ) : (
                <div className="space-y-2">
                  {readyJobs.map((job) => {
                    const selected = job.job_id === selectedJobId;

                    return (
                      <button
                        key={job.job_id}
                        type="button"
                        onClick={() => loadStagedJob(job.job_id)}
                        className={`w-full rounded-xl border px-4 py-3 text-left text-sm transition ${
                          selected
                            ? "border-[var(--insyt-brand)] bg-[var(--insyt-brand-soft)]"
                            : "border-[var(--insyt-border)] bg-[var(--insyt-surface-2)] hover:border-[var(--insyt-border-hover)] hover:bg-[var(--insyt-surface-hover)]"
                        }`}
                      >
                        <div className="flex items-start justify-between gap-3">
                          <div className="font-semibold insyt-text-primary">
                            {job.job_id}
                          </div>
                          <div className="insyt-status insyt-status-success">
                            {getJobStatusLabel(job)}
                          </div>
                        </div>

                        <div className="mt-1 text-xs insyt-text-muted">
                          Completed: {formatDateTime(job.completed_at)}
                        </div>

                        <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
                          <div className="insyt-metric px-2 py-1">
                            <div className="insyt-text-muted">Docs</div>
                            <div className="font-semibold insyt-text-primary">
                              {job.doc_count ?? 0}
                            </div>
                          </div>
                          <div className="insyt-metric px-2 py-1">
                            <div className="insyt-text-muted">Ready</div>
                            <div className="font-semibold text-[var(--insyt-success)]">
                              {job.ready_to_promote_count ?? 0}
                            </div>
                          </div>
                        </div>
                      </button>
                    );
                  })}
                </div>
              )}
            </div>

            <div>
              <div className="mb-2 text-xs font-semibold uppercase tracking-wide insyt-text-muted">
                {isSummaries ? "Uploaded / Promoted" : "Promoted"}
              </div>

              {promotedJobs.length === 0 ? (
                <div className="insyt-subpanel px-4 py-3 text-sm insyt-text-muted">
                  No promoted APC jobs yet.
                </div>
              ) : (
                <div className="space-y-2">
                  {promotedJobs.map((job) => {
                    const selected = job.job_id === selectedJobId;

                    return (
                      <button
                        key={job.job_id}
                        type="button"
                        onClick={() => loadStagedJob(job.job_id)}
                        className={`w-full rounded-xl border px-4 py-3 text-left text-sm transition ${
                          selected
                            ? "border-[var(--insyt-success)] bg-[rgba(13,148,136,0.10)]"
                            : "border-[var(--insyt-border)] bg-[var(--insyt-surface-2)] hover:border-[var(--insyt-border-hover)] hover:bg-[var(--insyt-surface-hover)]"
                        }`}
                      >
                        <div className="flex items-start justify-between gap-3">
                          <div className="font-semibold insyt-text-primary">
                            {job.job_id}
                          </div>
                          <div className="insyt-status insyt-status-success">
                            Promoted
                          </div>
                        </div>

                        <div className="mt-1 text-xs insyt-text-muted">
                          Promoted: {formatDateTime(job.promoted_at || job.completed_at)}
                        </div>

                        <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
                          <div className="insyt-metric px-2 py-1">
                            <div className="insyt-text-muted">Docs</div>
                            <div className="font-semibold insyt-text-primary">
                              {job.doc_count ?? 0}
                            </div>
                          </div>
                          <div className="insyt-metric px-2 py-1">
                            <div className="insyt-text-muted">Promoted</div>
                            <div className="font-semibold text-[var(--insyt-success)]">
                              {job.promoted_count ?? job.doc_count ?? 0}
                            </div>
                          </div>
                        </div>
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          </div>

          <div className="insyt-subpanel p-4">
            {!selectedJob ? (
              <div className="text-sm insyt-text-muted">
                Select a staged job to review documents.
              </div>
            ) : (
              <>
                <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <div className="flex items-center gap-2">
                      <div className="font-semibold insyt-text-primary">
                        {selectedJob.job_id}
                      </div>

                      {refreshingDetail ? (
                        <span className="text-xs text-[var(--insyt-info)]">
                          Refreshing...
                        </span>
                      ) : null}
                    </div>

                    <div className="mt-1 break-all text-xs insyt-text-muted">
                      {selectedJob.staged_prefix}
                    </div>
                  </div>

                  <div className="flex flex-wrap gap-2">
                    <button
                      type="button"
                      onClick={selectAllReadyDocs}
                      disabled={readyDocs.length === 0 || promoting}
                      className="insyt-btn insyt-btn-secondary insyt-btn-sm"
                    >
                      Select All Ready
                    </button>

                    <button
                      type="button"
                      onClick={clearSelection}
                      disabled={selectedDocIds.length === 0 || promoting}
                      className="insyt-btn insyt-btn-secondary insyt-btn-sm"
                    >
                      Clear
                    </button>

                    <button
                      type="button"
                      onClick={() =>
                        isSummaries
                          ? uploadToSummaryExtraction(false)
                          : promoteDocs(false)
                      }
                      disabled={
                        promoting ||
                        selectedDocIds.length === 0 ||
                        !isInsytAdmin()
                      }
                      className="insyt-btn insyt-btn-success insyt-btn-sm"
                    >
                      {promoting
                        ? isSummaries
                          ? "Uploading..."
                          : "Promoting..."
                        : isSummaries
                          ? "Upload Selected to Summary Extraction"
                          : "Promote Selected"}
                    </button>

                    <button
                      type="button"
                      onClick={() =>
                        isSummaries
                          ? uploadToSummaryExtraction(true)
                          : promoteDocs(true)
                      }
                      disabled={
                        promoting ||
                        readyDocs.length === 0 ||
                        !isInsytAdmin()
                      }
                      className="insyt-btn insyt-btn-info insyt-btn-sm"
                    >
                      {promoting
                        ? isSummaries
                          ? "Uploading..."
                          : "Promoting..."
                        : isSummaries
                          ? "Upload All to Summary Extraction"
                          : "Promote All Review-Ready"}
                    </button>
                  </div>

                  {isSummaries ? (
                    <div className="insyt-message insyt-message-warning w-full text-xs leading-5">
                      Summaries staged files are not promoted directly into live source folders.
                      Upload them to Summary Extraction first so INSYT can perform the proper
                      extraction, chunking, merging, and review-ready preparation.
                    </div>
                  ) : null}
                </div>

                <div className="mb-3 grid gap-2 md:grid-cols-7">
                  <div className="insyt-metric">
                    <div className="text-xs insyt-text-muted">Docs</div>
                    <div className="font-semibold insyt-text-primary">
                      {selectedJob.doc_count ?? 0}
                    </div>
                  </div>
                  <div className="insyt-metric">
                    <div className="text-xs insyt-text-muted">Ready</div>
                    <div className="font-semibold text-[var(--insyt-success)]">
                      {readyDocs.length}
                    </div>
                  </div>
                  <div className="insyt-metric">
                    <div className="text-xs insyt-text-muted">Promoted</div>
                    <div className="font-semibold text-[var(--insyt-success)]">
                      {promotedDocs.length}
                    </div>
                  </div>
                  <div className="insyt-metric">
                    <div className="text-xs insyt-text-muted">OCR pages</div>
                    <div className="font-semibold insyt-text-primary">
                      {selectedJob.summary?.ocr_page_count ?? "—"}
                    </div>
                  </div>
                  <div className="insyt-metric">
                    <div className="text-xs insyt-text-muted">OCR quote</div>
                    <div className="font-semibold text-[var(--insyt-info)]">
                      {typeof selectedJob.summary?.ocr_estimated_cost_usd ===
                      "number"
                        ? `$${selectedJob.summary.ocr_estimated_cost_usd.toFixed(
                            6
                          )}`
                        : "—"}
                    </div>
                  </div>
                  <div className="insyt-metric">
                    <div className="text-xs insyt-text-muted">Azure quote</div>
                    <div className="font-semibold insyt-text-primary">
                      {typeof selectedJob.summary?.estimated_azure_cost_usd ===
                      "number"
                        ? `$${selectedJob.summary.estimated_azure_cost_usd.toFixed(
                            6
                          )}`
                        : "—"}
                    </div>
                  </div>
                  <div className="insyt-metric">
                    <div className="text-xs insyt-text-muted">Selected</div>
                    <div className="font-semibold insyt-text-primary">
                      {selectedDocIds.length}
                    </div>
                  </div>
                </div>

                {loadingDetail ? (
                  <div className="text-sm insyt-text-muted">
                    Loading staged documents...
                  </div>
                ) : docs.length === 0 ? (
                  <div className="text-sm insyt-text-muted">
                    No staged documents found for this job.
                  </div>
                ) : (
                  <div className="insyt-table-shell max-h-[420px]">
                    <table className="insyt-table min-w-full text-left text-xs">
                      <thead className="insyt-table-header sticky top-0">
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
                            className="insyt-table-row"
                          >
                            <td className="px-3 py-2">
                              <input
                                type="checkbox"
                                checked={selectedDocIds.includes(doc.doc_id)}
                                disabled={!doc.ready_to_promote || promoting}
                                onChange={() => toggleDoc(doc.doc_id)}
                                className="insyt-check"
                              />
                            </td>
                            <td className="whitespace-nowrap px-3 py-2 font-semibold insyt-text-primary">
                              {doc.doc_id}
                            </td>
                            <td className="max-w-[280px] truncate px-3 py-2 insyt-text-secondary">
                              {doc.original_filename || "—"}
                            </td>
                            <td className="px-3 py-2 insyt-text-muted">
                              {doc.extension || "—"}
                            </td>
                            <td className="px-3 py-2 insyt-text-muted">
                              {doc.page_count ?? "—"}
                            </td>
                            <td className="px-3 py-2 insyt-text-muted">
                              {doc.requires_ocr ? "Yes" : "No"}
                            </td>
                            <td className="px-3 py-2">
                              <span
                                className={`insyt-status ${
                                  isPromotedDoc(doc)
                                    ? "insyt-status-info"
                                    : doc.ready_to_promote
                                      ? "insyt-status-success"
                                      : "insyt-status-warning"
                                }`}
                              >
                                {isPromotedDoc(doc)
                                  ? "Promoted"
                                  : doc.ready_to_promote
                                    ? "Ready"
                                    : "Missing Pair"}
                              </span>
                            </td>
                            <td className="whitespace-nowrap px-3 py-2 insyt-text-muted">
                              {formatBytes(doc.source_bytes)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}

                {promotionResult?.skipped?.length ? (
                  <div className="insyt-message insyt-message-warning mt-3 text-xs">
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