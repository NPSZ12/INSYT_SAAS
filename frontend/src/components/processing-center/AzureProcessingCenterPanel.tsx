"use client";

import { useEffect, useMemo, useState } from "react";
import { apiGet, apiPost } from "../../lib/api";

type UploadItem = {
  name?: string;
  blob_name?: string;
  size?: number;
  last_modified?: string;
  content_type?: string;
};

type ProcessingSettings = {
  workspace?: string;
  db_path?: string;
  allow_azure_write?: boolean;
  allow_live_ocr?: boolean;
  processing_account?: string;
  review_account?: string;
};

type JobHistoryItem = {
  job_id?: string;
  status?: string;
  message?: string;
  matter_id?: string;
  generated_at?: string;
  created_at?: string;
  completed_at?: string;
  source_file_count?: number;
  expanded_file_count?: number;
  unique_doc_count?: number;
  duplicate_doc_count?: number;
  ocr_page_count?: number;
  estimated_azure_cost_usd?: number;
  ocr_candidate_files?: number;
  ocr_candidate_bytes?: number;
  ocr_candidate_gb?: number;
  ocr_estimated_pages?: number;
  ocr_estimated_cost_usd?: number;
  ocr_cost_pct_of_total?: number;
  ocr_reason_counts?: Record<string, number>;
  non_ocr_estimated_cost_usd?: number;
  downloaded_count?: number;
  native_text_upload_count?: number;
  report_upload_count?: number;
  warning_count?: number;
  status_blob_path?: string;
  last_modified?: string;
};

type Props = {
  workspace: "capture" | "discovery" | "summaries";
  clientId: string;
  projectId: string;
  apiBase?: string;
};


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

function formatDateTime(value?: string) {
  if (!value) return "—";

  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
}

function cleanError(message: string) {
  try {
    const parsed = JSON.parse(message);
    return parsed?.detail || message;
  } catch {
    return message;
  }
}

async function withTimeout<T>(
  promise: Promise<T>,
  message: string,
  timeoutMs = 20000
): Promise<T> {
  let timeoutId: ReturnType<typeof setTimeout> | null = null;

  const timeoutPromise = new Promise<never>((_, reject) => {
    timeoutId = setTimeout(() => {
      reject(new Error(message));
    }, timeoutMs);
  });

  try {
    return await Promise.race([promise, timeoutPromise]);
  } finally {
    if (timeoutId) {
      clearTimeout(timeoutId);
    }
  }
}

export default function AzureProcessingCenterPanel({
  workspace,
  clientId,
  projectId,
  apiBase = "",
}: Props) {
  const [settings, setSettings] = useState<ProcessingSettings | null>(null);
  const [uploads, setUploads] = useState<UploadItem[]>([]);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [loadingSettings, setLoadingSettings] = useState(false);
  const [loadingUploads, setLoadingUploads] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [starting, setStarting] = useState(false);
  const [job, setJob] = useState<any>(null);
  const [jobReport, setJobReport] = useState<any>(null);
  const [loadingReport, setLoadingReport] = useState(false);
  const [error, setError] = useState<string>("");
  const [uploadMessage, setUploadMessage] = useState<string>("");
  const [showStartConfirm, setShowStartConfirm] = useState(false);
  const [costThresholdAcknowledged, setCostThresholdAcknowledged] =
    useState(false);
  const [archivingUploads, setArchivingUploads] = useState(false);
  const [archiveMessage, setArchiveMessage] = useState("");
  const [jobHistory, setJobHistory] = useState<JobHistoryItem[]>([]);
  const [loadingJobHistory, setLoadingJobHistory] = useState(false);
  const [selectedUploadNames, setSelectedUploadNames] = useState<string[]>([]);
  const [removingUploads, setRemovingUploads] = useState(false);
  const [removeMessage, setRemoveMessage] = useState("");
  const [trackedJob, setTrackedJob] = useState<any>(null);
  const [pollingJob, setPollingJob] = useState(false);
  
  

  const settingsUrl = useMemo(
    () => `/api/${workspace}/processing-center/settings`,
    [workspace]
  );
  const uploadsUrl = useMemo(
    () =>
      `/api/${workspace}/processing-center/uploads?client=${encodeURIComponent(
        clientId
      )}&project=${encodeURIComponent(projectId)}`,
    [workspace, clientId, projectId]
  );

  const jobHistoryUrl = useMemo(
    () =>
      `/api/${workspace}/processing-center/job-history?client=${encodeURIComponent(
        clientId
      )}&project=${encodeURIComponent(projectId)}`,
    [workspace, clientId, projectId]
  );

  const trackedStartUrl = useMemo(
    () => `/api/${workspace}/processing-center/tracked-jobs/start`,
    [workspace]
  );

  const reportLookupJobId =
    job?.routing?.job_id ||
    job?.review_upload?.job_id ||
    job?.report_upload?.job_id ||
    job?.job_id ||
    "";

  const reportUrl = useMemo(() => {
    if (!reportLookupJobId) return "";

    return `/api/${workspace}/processing-center/jobs/${encodeURIComponent(
      reportLookupJobId
    )}/report`;
  }, [workspace, reportLookupJobId]);

  
  const totalUploadBytes = uploads.reduce(
    (sum, item) => sum + Number(item.size || 0),
    0
  );

  const nativeTextUploadCount = job?.review_upload?.uploads?.length ?? 0;
  const reportUploadCount = job?.report_upload?.uploaded_reports?.length ?? 0;
  const downloadedCount = job?.downloads?.length ?? 0;
  const warningCount = job?.warnings?.length ?? 0;

  const activeJobStatus = trackedJob || job;

  const processingProgressPct =
    typeof activeJobStatus?.progress_pct === "number"
      ? activeJobStatus.progress_pct
      : starting || pollingJob
        ? 15
        : activeJobStatus?.status === "completed"
          ? 100
          : 0;

  const processingStatusLabel =
    activeJobStatus?.message ||
    (starting || pollingJob
      ? "Processing in progress..."
      : activeJobStatus?.status === "completed"
        ? "Processing completed"
        : "Ready");

  const reportSummary =
    jobReport?.report ||
    jobReport?.summary ||
    jobReport?.job_report ||
    jobReport ||
    null;

  const uploadCount = uploads.length;

  const uploadSizeBytes = uploads.reduce((total, item: any) => {
    const size =
      item.size ??
      item.size_bytes ??
      item.content_length ??
      item.contentLength ??
      0;

    return total + Number(size || 0);
  }, 0);

  const uploadSizeGb = uploadSizeBytes / 1024 / 1024 / 1024;

  // Demo/preflight estimate.
  // Actual cost telemetry is finalized after the APC job runs.
  const estimatedPreRunCostUsd =
    uploadCount > 0
      ? Math.max(0.00005, uploadSizeGb * 35 + uploadCount * 0.00001)
      : 0;

  // Keep intentionally low for now so we can confirm the warning works.
  const costThresholdUsd = 0.00005;

  const exceedsCostThreshold =
    uploadCount > 0 && estimatedPreRunCostUsd >= costThresholdUsd;

  const reportJob = reportSummary?.job || {};
  const reportOcr = reportSummary?.ocr || {};
  const reportCost = reportSummary?.cost || {};

  const sourceFiles =
    reportJob?.source_file_count ??
    reportSummary?.source_file_count ??
    reportSummary?.source_files ??
    reportSummary?.source_data?.source_files ??
    reportSummary?.sourceData?.sourceFiles ??
    null;

  const expandedFiles =
    reportJob?.expanded_file_count ??
    reportSummary?.expanded_file_count ??
    reportSummary?.containers?.expanded_file_count ??
    null;

  const duplicateDocs =
    reportJob?.duplicate_doc_count ??
    reportSummary?.duplicate_doc_count ??
    null;

  const uniqueDocs =
    reportJob?.unique_doc_count ??
    reportSummary?.unique_doc_count ??
    reportSummary?.unique_docs ??
    reportSummary?.source_data?.unique_docs ??
    reportSummary?.sourceData?.uniqueDocs ??
    null;

  const ocrPages =
    reportJob?.ocr_page_count ??
    reportOcr?.estimated_pages ??
    reportSummary?.ocr_page_count ??
    reportSummary?.ocr_estimated_pages ??
    reportSummary?.ocr?.estimated_pages ??
    reportSummary?.ocr?.pages ??
    null;

  const ocrCost =
    reportOcr?.estimated_cost_usd ??
    reportSummary?.ocr_estimated_cost ??
    reportSummary?.ocr_cost_estimated_usd ??
    reportSummary?.ocr?.estimated_cost_usd ??
    null;

  const totalAzureCost =
    reportJob?.estimated_azure_cost_usd ??
    reportCost?.total_estimated_azure_cost_usd ??
    reportSummary?.estimated_azure_cost_usd ??
    reportSummary?.total_estimated_azure_cost ??
    reportSummary?.azure_cost?.total_estimated_cost ??
    null;

  const promotedDocs =
    reportSummary?.review_promotion?.promoted_docs ??
    reportSummary?.reviewPromotion?.promotedDocs ??
    null;

  const projectHistoryTotals = jobHistory.reduce(
    (totals, historyJob) => {
      totals.jobs += 1;
      totals.sourceFiles += Number(historyJob.source_file_count || 0);
      totals.expandedFiles += Number(historyJob.expanded_file_count || 0);
      totals.uniqueDocs += Number(historyJob.unique_doc_count || 0);
      totals.duplicateDocs += Number(historyJob.duplicate_doc_count || 0);
      totals.ocrPages += Number(historyJob.ocr_page_count || 0);
      totals.azureEstimate += Number(historyJob.estimated_azure_cost_usd || 0);
      totals.ocrCandidates += Number(historyJob.ocr_candidate_files || 0);
      totals.ocrEstimatedPages += Number(
        historyJob.ocr_estimated_pages ?? historyJob.ocr_page_count ?? 0
      );
      totals.ocrEstimate += Number(historyJob.ocr_estimated_cost_usd || 0);
      totals.nonOcrEstimate += Number(historyJob.non_ocr_estimated_cost_usd || 0);

      if (String(historyJob.status || "").toLowerCase().includes("fail")) {
        totals.failedJobs += 1;
      }

      return totals;
    },
    {
      jobs: 0,
      failedJobs: 0,
      sourceFiles: 0,
      expandedFiles: 0,
      uniqueDocs: 0,
      duplicateDocs: 0,
      ocrPages: 0,
      ocrCandidates: 0,
      ocrEstimatedPages: 0,
      ocrEstimate: 0,
      nonOcrEstimate: 0,
      azureEstimate: 0,
    }
  );

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

  function toggleSelectedUpload(name: string) {
    setSelectedUploadNames((current) =>
      current.includes(name)
        ? current.filter((item) => item !== name)
        : [...current, name]
    );
  }

  function buildTrackedStatusUrl(jobId: string) {
    return (
      `/api/${workspace}/processing-center/tracked-jobs/${encodeURIComponent(
        jobId
      )}/status` +
      `?client=${encodeURIComponent(clientId)}` +
      `&project=${encodeURIComponent(projectId)}`
    );
  }

  function clearSelectedUploads() {
    setSelectedUploadNames([]);
  }

  async function removeProcessingUploads(clearAll = false) {
    if (!isInsytAdmin()) {
      setError("Only INSYT Admin can remove Processing Center uploads.");
      return;
    }

    if (!clearAll && selectedUploadNames.length === 0) {
      setError("Select at least one upload to remove.");
      return;
    }

    setRemovingUploads(true);
    setError("");
    setRemoveMessage("");

    try {
      const result = (await apiPost(
        `/api/${workspace}/processing-center/uploads/remove`,
        {
          client: clientId,
          project: projectId,
          blob_names: clearAll ? [] : selectedUploadNames,
          clear_all: clearAll,
          reason: clearAll
            ? "clear_all_pending_processing_uploads"
            : "remove_selected_pending_processing_uploads",
        }
      )) as any;

      setRemoveMessage(
        clearAll
          ? `Cleared ${result?.removed_count ?? 0} pending upload(s).`
          : `Removed ${result?.removed_count ?? 0} selected upload(s).`
      );

      setSelectedUploadNames([]);

      if (clearAll || selectedUploadNames.length > 0) {
        setJob(null);
        setTrackedJob(null);
        setJobReport(null);
        setArchiveMessage("");
      }

      await refreshUploads();
      await refreshJobHistory();
    } catch (err: any) {
      setError(cleanError(err?.message || "Unable to remove processing uploads."));
    } finally {
      setRemovingUploads(false);
    }
  }

  async function refreshSettings() {
    setLoadingSettings(true);

    try {
      const data = (await withTimeout(
        apiGet(settingsUrl),
        "APC settings request timed out."
      )) as ProcessingSettings;

      setSettings(data);
    } catch (err: any) {
      setError(cleanError(err?.message || "Unable to load APC settings."));
    } finally {
      setLoadingSettings(false);
    }
  }

  async function refreshUploads() {
    setLoadingUploads(true);

    try {
      const data = (await withTimeout(
        apiGet(uploadsUrl),
        "Processing uploads request timed out."
      )) as { uploads: UploadItem[] };

      setUploads(data.uploads || []);
      setSelectedUploadNames((current) =>
        current.filter((name) =>
          (data.uploads || []).some(
            (item) => (item.blob_name || item.name || "Unknown file") === name
          )
        )
      );
    } catch (err: any) {
      setError(cleanError(err?.message || "Unable to load processing uploads."));
    } finally {
      setLoadingUploads(false);
    }
  }

  async function refreshJobHistory() {
    setLoadingJobHistory(true);

    try {
      const data = (await withTimeout(
        apiGet(jobHistoryUrl),
        "Processing history request timed out."
      )) as {
        jobs?: JobHistoryItem[];
      };

      setJobHistory(data.jobs || []);
    } catch (err: any) {
      setError(cleanError(err?.message || "Unable to load processing history."));
    } finally {
      setLoadingJobHistory(false);
    }
  }

  async function refreshAll() {
    setError("");

    await Promise.allSettled([
      refreshSettings(),
      refreshUploads(),
      refreshJobHistory(),
    ]);
  }

  async function pollTrackedJobStatus(jobId: string) {
    setPollingJob(true);

    try {
      const statusUrl = buildTrackedStatusUrl(jobId);

      for (let attempt = 0; attempt < 240; attempt += 1) {
        const status = (await apiGet(statusUrl)) as any;

        setTrackedJob(status);

        if (
          ["completed", "failed", "cancelled", "no_uploads"].includes(
            String(status?.status || "").toLowerCase()
          )
        ) {
          setJob(status);
          await refreshUploads();
          await refreshJobHistory();
          return;
        }

        await new Promise((resolve) => setTimeout(resolve, 3000));
      }

      setError("Tracked APC job is still running. Refresh status again shortly.");
    } catch (err: any) {
      setError(cleanError(err?.message || "Unable to poll tracked APC job."));
    } finally {
      setPollingJob(false);
    }
  }

  async function uploadToAzureProcessingCenter() {
    if (!clientId || !projectId || !selectedFile) {
      setError("Client, project, and file are required before uploading.");
      return;
    }

    const resolvedApiBase =
      apiBase ||
      process.env.NEXT_PUBLIC_API_BASE_URL ||
      "https://api.insyt360.com";

    setUploading(true);
    setError("");
    setUploadMessage(`Uploading ${selectedFile.name}...`);

    try {
      const formData = new FormData();
      formData.append("client", clientId);
      formData.append("project_id", projectId);
      formData.append("file", selectedFile);

      const token = localStorage.getItem("insyt_token");

      const response = await fetch(
        `${resolvedApiBase}/api/${workspace}/processing-center/uploads/upload`,
        {
          method: "POST",
          headers: token
            ? {
                Authorization: `Bearer ${token}`,
              }
            : undefined,
          credentials: "include",
          body: formData,
        }
      );

      const text = await response.text();

      if (!response.ok) {
        throw new Error(text || `Upload failed with status ${response.status}.`);
      }

      let result: any = {};
      try {
        result = text ? JSON.parse(text) : {};
      } catch {
        result = {};
      }

      setUploadMessage(
        result?.message ||
          `Uploaded ${selectedFile.name} to Azure Processing Center.`
      );

      // A new upload means the prior completed job status is stale.
      setJob(null);
      setTrackedJob(null);
      setJobReport(null);
      setArchiveMessage("");
      setRemoveMessage("");

      setSelectedFile(null);
      await refreshUploads();
      await refreshJobHistory();
    } catch (err: any) {
      setError(cleanError(err?.message || "Unable to upload to Azure Processing Center."));
      setUploadMessage("");
    } finally {
      setUploading(false);
    }
  }

  async function loadJobReport() {
    if (!reportUrl) {
      setError("No completed job is available for report lookup.");
      return;
    }

    setLoadingReport(true);
    setError("");

    try {
      const data = (await apiGet(reportUrl)) as any;
      setJobReport(data);
    } catch (err: any) {
      setError(cleanError(err?.message || "Unable to load job report."));
    } finally {
      setLoadingReport(false);
    }
  }

  async function archiveProcessedUploads() {
    if (!job?.job_id) {
      setError("No completed processing job is available to archive uploads.");
      return;
    }

    if (!isInsytAdmin()) {
      setError("Only INSYT Admin can archive Processing Center uploads.");
      return;
    }

    setArchivingUploads(true);
    setArchiveMessage("");
    setError("");

    try {
      const archiveUrl =
        `/api/${workspace}/processing-center/uploads/archive` +
        `?client=${encodeURIComponent(clientId)}` +
        `&project=${encodeURIComponent(projectId)}` +
        `&job_id=${encodeURIComponent(job.job_id)}`;

      const result = (await apiPost(archiveUrl, {})) as any;

      setArchiveMessage(
        `Archived ${result?.archived_count ?? 0} upload(s).`
      );

      await refreshUploads();
      await refreshJobHistory();
    } catch (err: any) {
      setError(err?.message || "Unable to archive Processing Center uploads.");
    } finally {
      setArchivingUploads(false);
    }
  }

  async function startProcessing() {
    if (!clientId || !projectId) {
      setError("Client and project are required before starting processing.");
      return;
    }

    if (!isInsytAdmin()) {
      setError("Only INSYT Admin users can start Azure processing.");
      return;
    }

    setStarting(true);
    setError("");
    setJobReport(null);
    setTrackedJob(null);

    try {
      const data = (await apiPost(trackedStartUrl, {
        client: clientId,
        project: projectId,
        matter_id: `${projectId}-AZURE-RUN`,
        doc_prefix: "INSYT",
        enable_ocr_dry_run: true,
        enable_live_ocr: false,
        azure_write: true,
        overwrite: true,
        clean_staging: false,
        auto_archive_uploads: true,
      })) as any;

      setTrackedJob(data);
      setJob(data);

      if (data?.job_id) {
        await pollTrackedJobStatus(data.job_id);
      } else {
        setError("Tracked APC job did not return a job_id.");
      }
    } catch (err: any) {
      setError(cleanError(err?.message || "Unable to start tracked APC job."));
    } finally {
      setStarting(false);
    }
  }


  useEffect(() => {
    refreshAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [settingsUrl, uploadsUrl, jobHistoryUrl]);

  return (
    <div className="rounded-2xl border border-slate-700 bg-slate-950/70 p-5 text-slate-100 shadow-xl space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold">Azure Processing Center</h2>
          <p className="text-sm text-slate-400">
            Intake from insytprodstorage; review-ready Native/Text outputs to
            insytreviewstorage.
          </p>
        </div>

        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={refreshAll}
            disabled={false}
            className="inline-flex h-10 min-w-[110px] items-center justify-center whitespace-nowrap rounded-full border border-blue-400/60 bg-blue-500/10 px-5 text-sm font-semibold text-blue-200 shadow-sm transition hover:-translate-y-0.5 hover:border-blue-300 hover:bg-blue-500/20 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
          >
            {loadingSettings || loadingUploads || loadingJobHistory
              ? "Refreshing..."
              : "Refresh"}
          </button>

          <button
            type="button"
            onClick={() => {
              setCostThresholdAcknowledged(false);
              setShowStartConfirm(true);
            }}
            disabled={starting || pollingJob || uploads.length === 0 || !isInsytAdmin()}
            className="inline-flex h-10 min-w-[190px] items-center justify-center whitespace-nowrap rounded-full border border-violet-400/60 bg-violet-500/20 px-5 text-sm font-semibold text-violet-100 shadow-sm transition hover:-translate-y-0.5 hover:border-violet-300 hover:bg-violet-500/30 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
          >
            {starting || pollingJob ? "Processing..." : "Start Azure Processing"}
          </button>
          {!isInsytAdmin() ? (
            <div className="rounded-xl border border-amber-400/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-100">
              Files may be uploaded to the Processing Center, but Azure Processing can
              only be started by an INSYT Admin.
            </div>
          ) : null}
        </div>
      </div>

      {error ? (
        <div className="rounded-xl border border-red-500/40 bg-red-950/40 p-3 text-sm text-red-200">
          {error}
        </div>
      ) : null}

      {starting || pollingJob || activeJobStatus ? (
        <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
          <div className="mb-2 flex items-center justify-between gap-3">
            <div>
              <div className="text-sm font-semibold text-slate-100">
                Azure Processing Status
              </div>
              <div className="mt-1 text-xs text-slate-400">
                {processingStatusLabel}
              </div>
            </div>

            <div className="text-xs font-semibold text-slate-300">
              {processingProgressPct}%
            </div>
          </div>

          <div className="h-3 overflow-hidden rounded-full bg-slate-800">
            <div
              className="h-full rounded-full bg-violet-500 transition-all duration-500"
              style={{ width: `${processingProgressPct}%` }}
            />
          </div>

          {starting ? (
            <div className="mt-2 text-xs text-slate-500">
              Processing may include ZIP expansion, hashing, duplicate checks, OCR
              dry-run pricing, Doc ID assignment, review promotion, report generation,
              and upload archiving.
            </div>
          ) : null}
        </div>
      ) : null}

      <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
        <div className="mb-3">
          <div className="font-medium">Upload to Azure Processing Center</div>
          <div className="mt-1 text-sm text-slate-400">
            Files are uploaded to source/processing_center/uploads. Processing can only be started by INSYT Admin.
          </div>
        </div>

        <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
          <input
            id="azure-processing-center-file-input"
            type="file"
            className="hidden"
            onChange={(event) =>
              setSelectedFile(event.target.files?.[0] || null)
            }
          />

          <label
            htmlFor="azure-processing-center-file-input"
            className="inline-flex h-10 min-w-[210px] cursor-pointer items-center justify-center whitespace-nowrap rounded-full border border-emerald-400/60 bg-emerald-500/15 px-5 text-sm font-semibold text-emerald-200 shadow-sm transition hover:-translate-y-0.5 hover:border-emerald-300 hover:bg-emerald-500/25 hover:text-white focus:outline-none focus:ring-2 focus:ring-emerald-400 focus:ring-offset-2 focus:ring-offset-slate-950"
          >
            Choose File
          </label>

          <button
            type="button"
            onClick={() => {
              if (!selectedFile || uploading) return;
              uploadToAzureProcessingCenter();
            }}
            disabled={!selectedFile || uploading}
            className="inline-flex h-10 min-w-[230px] items-center justify-center whitespace-nowrap rounded-full border border-sky-400/60 bg-sky-500/15 px-5 text-sm font-semibold text-sky-200 shadow-sm transition hover:-translate-y-0.5 hover:border-sky-300 hover:bg-sky-500/25 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
          >
            {uploading ? "Uploading..." : "Upload to Processing Center"}
          </button>
        </div>

        <div className="mt-2 min-h-5 truncate text-xs leading-5 text-slate-500">
          {selectedFile ? selectedFile.name : "No file selected"}
        </div>

        {uploadMessage ? (
          <div className="mt-2 rounded-lg border border-sky-500/30 bg-sky-950/30 px-3 py-2 text-xs text-sky-200">
            {uploadMessage}
          </div>
        ) : null}
      </div>

      <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="font-medium">Processing uploads</div>
            <div className="mt-1 text-sm text-slate-400">
              Pending files that have not yet been processed.
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <div className="text-sm text-slate-400">
              {uploads.length} file(s)
            </div>

            {isInsytAdmin() && uploads.length > 0 ? (
              <>
                <button
                  type="button"
                  onClick={() => removeProcessingUploads(false)}
                  disabled={removingUploads || selectedUploadNames.length === 0}
                  className="inline-flex h-9 items-center justify-center rounded-full border border-amber-400/60 bg-amber-500/10 px-4 text-xs font-semibold text-amber-100 shadow-sm transition hover:-translate-y-0.5 hover:border-amber-300 hover:bg-amber-500/20 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {removingUploads ? "Removing..." : "Remove Selected"}
                </button>

                <button
                  type="button"
                  onClick={() => removeProcessingUploads(true)}
                  disabled={removingUploads}
                  className="inline-flex h-9 items-center justify-center rounded-full border border-red-400/60 bg-red-500/10 px-4 text-xs font-semibold text-red-100 shadow-sm transition hover:-translate-y-0.5 hover:border-red-300 hover:bg-red-500/20 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
                >
                  Clear All Uploads
                </button>
              </>
            ) : null}
          </div>
        </div>

        {removeMessage ? (
          <div className="mb-3 rounded-xl border border-emerald-400/30 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-100">
            {removeMessage}
          </div>
        ) : null}

        {uploads.length === 0 ? (
          <p className="text-sm text-slate-500">
            No files found in source/processing_center/uploads.
          </p>
        ) : (
          <div className="max-h-72 space-y-2 overflow-y-auto pr-1">
            {uploads.map((item, index) => {
              const displayName = item.blob_name || item.name || "Unknown file";

              return (
                <div
                  key={`${displayName}-${index}`}
                  className="rounded-lg bg-slate-950 px-3 py-2 text-sm"
                >
                  <div className="flex items-start gap-3">
                    {isInsytAdmin() ? (
                      <input
                        type="checkbox"
                        checked={selectedUploadNames.includes(displayName)}
                        onChange={() => toggleSelectedUpload(displayName)}
                        className="mt-1 h-4 w-4 rounded border-slate-500 bg-slate-950"
                      />
                    ) : null}

                    <div className="break-all text-slate-200">{displayName}</div>
                  </div>
                  <div className="mt-1 flex flex-wrap gap-3 text-xs text-slate-500">
                    <span>{formatBytes(item.size)}</span>
                    {item.content_type ? <span>{item.content_type}</span> : null}
                    {item.last_modified ? (
                      <span>{String(item.last_modified)}</span>
                    ) : null}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
      
      <div className="grid gap-3 md:grid-cols-4">
        <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
          <div className="text-xs uppercase tracking-wide text-slate-500">
            Azure Writes
          </div>
          <div className="mt-1 text-lg font-semibold">
            {settings?.allow_azure_write ? "Enabled" : "Disabled"}
          </div>
        </div>

        <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
          <div className="text-xs uppercase tracking-wide text-slate-500">
            Live OCR
          </div>
          <div className="mt-1 text-lg font-semibold">
            {settings?.allow_live_ocr ? "Enabled" : "Disabled"}
          </div>
        </div>

        <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
          <div className="text-xs uppercase tracking-wide text-slate-500">
            Uploads
          </div>
          <div className="mt-1 text-lg font-semibold">{uploadCount}</div>
        </div>

        <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
          <div className="text-xs uppercase tracking-wide text-slate-500">
            Upload Size
          </div>
          <div className="mt-1 text-lg font-semibold">
            {formatBytes(totalUploadBytes)}
          </div>
        </div>
      </div>

      <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
        <div className="mb-3 font-medium">Storage routing</div>

        <div className="grid gap-3 md:grid-cols-2">
          <div className="rounded-lg bg-slate-950 px-3 py-2">
            <div className="text-xs text-slate-500">Processing account</div>
            <div className="break-all text-sm text-slate-200">
              {settings?.processing_account || "Loading..."}
            </div>
          </div>

          <div className="rounded-lg bg-slate-950 px-3 py-2">
            <div className="text-xs text-slate-500">Review output account</div>
            <div className="break-all text-sm text-slate-200">
              {settings?.review_account || "Loading..."}
            </div>
          </div>
        </div>
      </div>

      <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="font-medium">Project Processing Totals</div>
            <div className="mt-1 text-sm text-slate-400">
              Running totals from completed Azure Processing Center jobs for this project.
            </div>
          </div>

          <div className="rounded-full border border-slate-600 px-3 py-1 text-xs font-semibold text-slate-300">
            {projectHistoryTotals.jobs} job(s)
          </div>
        </div>

        <div className="grid gap-3 md:grid-cols-8">
          <div className="rounded-lg bg-slate-950 px-3 py-2">
            <div className="text-xs text-slate-500">Source uploads</div>
            <div className="text-base font-semibold text-slate-100">
              {projectHistoryTotals.sourceFiles}
            </div>
          </div>

          <div className="rounded-lg bg-slate-950 px-3 py-2">
            <div className="text-xs text-slate-500">Expanded files</div>
            <div className="text-base font-semibold text-slate-100">
              {projectHistoryTotals.expandedFiles}
            </div>
          </div>

          <div className="rounded-lg bg-slate-950 px-3 py-2">
            <div className="text-xs text-slate-500">New unique docs</div>
            <div className="text-base font-semibold text-emerald-100">
              {projectHistoryTotals.uniqueDocs}
            </div>
          </div>

          <div className="rounded-lg bg-slate-950 px-3 py-2">
            <div className="text-xs text-slate-500">Duplicate docs</div>
            <div className="text-base font-semibold text-amber-100">
              {projectHistoryTotals.duplicateDocs}
            </div>
          </div>

          <div className="rounded-lg bg-slate-950 px-3 py-2">
            <div className="text-xs text-slate-500">OCR pages</div>
            <div className="text-base font-semibold text-slate-100">
              {projectHistoryTotals.ocrPages}
            </div>
          </div>

          <div className="rounded-lg bg-slate-950 px-3 py-2">
            <div className="text-xs text-slate-500">OCR estimate</div>
            <div className="text-base font-semibold text-violet-100">
              ${projectHistoryTotals.ocrEstimate.toFixed(6)}
            </div>
          </div>

          <div className="rounded-lg bg-slate-950 px-3 py-2">
            <div className="text-xs text-slate-500">Failed jobs</div>
            <div className="text-base font-semibold text-red-100">
              {projectHistoryTotals.failedJobs}
            </div>
          </div>

          <div className="rounded-lg bg-slate-950 px-3 py-2">
            <div className="text-xs text-slate-500">Azure estimate</div>
            <div className="text-base font-semibold text-slate-100">
              ${projectHistoryTotals.azureEstimate.toFixed(6)}
            </div>
          </div>
        </div>
      </div>

      <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="font-medium">OCR Pricing Snapshot</div>
            <div className="mt-1 text-sm text-slate-400">
              OCR dry-run estimates from completed jobs. Live OCR remains disabled.
            </div>
          </div>

          <div className="rounded-full border border-slate-600 px-3 py-1 text-xs font-semibold text-slate-300">
            Dry-run pricing
          </div>
        </div>

        <div className="grid gap-3 md:grid-cols-5">
          <div className="rounded-lg bg-slate-950 px-3 py-2">
            <div className="text-xs text-slate-500">OCR candidates</div>
            <div className="text-base font-semibold text-slate-100">
              {projectHistoryTotals.ocrCandidates}
            </div>
          </div>

          <div className="rounded-lg bg-slate-950 px-3 py-2">
            <div className="text-xs text-slate-500">OCR pages</div>
            <div className="text-base font-semibold text-slate-100">
              {projectHistoryTotals.ocrEstimatedPages}
            </div>
          </div>

          <div className="rounded-lg bg-slate-950 px-3 py-2">
            <div className="text-xs text-slate-500">OCR estimate</div>
            <div className="text-base font-semibold text-violet-100">
              ${projectHistoryTotals.ocrEstimate.toFixed(6)}
            </div>
          </div>

          <div className="rounded-lg bg-slate-950 px-3 py-2">
            <div className="text-xs text-slate-500">Non-OCR estimate</div>
            <div className="text-base font-semibold text-slate-100">
              ${projectHistoryTotals.nonOcrEstimate.toFixed(6)}
            </div>
          </div>

          <div className="rounded-lg bg-slate-950 px-3 py-2">
            <div className="text-xs text-slate-500">Total Azure estimate</div>
            <div className="text-base font-semibold text-slate-100">
              ${projectHistoryTotals.azureEstimate.toFixed(6)}
            </div>
          </div>
        </div>
      </div>

      <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="font-medium">Processing Status / History</div>
            <div className="mt-1 text-sm text-slate-400">
              Previously completed Azure Processing Center jobs for this project.
            </div>
          </div>

          <button
            type="button"
            onClick={refreshJobHistory}
            disabled={loadingJobHistory}
            className="inline-flex h-9 min-w-[100px] items-center justify-center whitespace-nowrap rounded-full border border-blue-400/60 bg-blue-500/10 px-4 text-xs font-semibold text-blue-200 shadow-sm transition hover:-translate-y-0.5 hover:border-blue-300 hover:bg-blue-500/20 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
          >
            {loadingJobHistory ? "Loading..." : "Refresh"}
          </button>
        </div>

        {jobHistory.length === 0 ? (
          <p className="text-sm text-slate-500">
            No completed processing jobs found for this project yet.
          </p>
        ) : (
          <div className="max-h-96 space-y-3 overflow-y-auto pr-1">
            {jobHistory.map((historyJob) => (
              <div
                key={historyJob.job_id || historyJob.status_blob_path}
                className="rounded-xl border border-slate-800 bg-slate-950 px-4 py-3 text-sm"
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <div className="font-semibold text-slate-100">
                      {historyJob.job_id || "Unknown Job"}
                    </div>
                    <div className="mt-1 text-xs text-slate-500">
                      Completed:{" "}
                      {formatDateTime(
                        historyJob.completed_at ||
                          historyJob.generated_at ||
                          historyJob.last_modified
                      )}
                    </div>
                  </div>

                  <div className="rounded-full border border-emerald-400/40 bg-emerald-500/10 px-3 py-1 text-xs font-semibold text-emerald-200">
                    {historyJob.status || "unknown"}
                  </div>
                </div>

                <div className="mt-3 grid gap-2 md:grid-cols-8">
                  <div className="rounded-lg bg-slate-900 px-3 py-2">
                    <div className="text-xs text-slate-500">Source files</div>
                    <div className="font-semibold text-slate-100">
                      {historyJob.source_file_count ?? "—"}
                    </div>
                  </div>

                  <div className="rounded-lg bg-slate-900 px-3 py-2">
                    <div className="text-xs text-slate-500">Expanded</div>
                    <div className="font-semibold text-slate-100">
                      {historyJob.expanded_file_count ?? "—"}
                    </div>
                  </div>

                  <div className="rounded-lg bg-slate-900 px-3 py-2">
                    <div className="text-xs text-slate-500">Unique docs</div>
                    <div className="font-semibold text-emerald-100">
                      {historyJob.unique_doc_count ?? "—"}
                    </div>
                  </div>

                  <div className="rounded-lg bg-slate-900 px-3 py-2">
                    <div className="text-xs text-slate-500">Duplicates</div>
                    <div className="font-semibold text-amber-100">
                      {historyJob.duplicate_doc_count ?? "—"}
                    </div>
                  </div>

                  <div className="rounded-lg bg-slate-900 px-3 py-2">
                    <div className="text-xs text-slate-500">OCR pages</div>
                    <div className="font-semibold text-slate-100">
                      {historyJob.ocr_page_count ?? "—"}
                    </div>
                  </div>

                  <div className="rounded-lg bg-slate-900 px-3 py-2">
                    <div className="text-xs text-slate-500">OCR estimate</div>
                    <div className="font-semibold text-violet-100">
                      {typeof historyJob.ocr_estimated_cost_usd === "number"
                        ? `$${historyJob.ocr_estimated_cost_usd.toFixed(6)}`
                        : "—"}
                    </div>
                  </div>

                  <div className="rounded-lg bg-slate-900 px-3 py-2">
                    <div className="text-xs text-slate-500">Warnings</div>
                    <div className="font-semibold text-slate-100">
                      {historyJob.warning_count ?? "—"}
                    </div>
                  </div>

                  <div className="rounded-lg bg-slate-900 px-3 py-2">
                    <div className="text-xs text-slate-500">Azure estimate</div>
                    <div className="font-semibold text-slate-100">
                      {typeof historyJob.estimated_azure_cost_usd === "number"
                        ? `$${historyJob.estimated_azure_cost_usd.toFixed(6)}`
                        : "—"}
                    </div>
                  </div>
                </div>

                <div className="mt-2 break-all text-xs text-slate-600">
                  {historyJob.status_blob_path}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {job ? (
        <div className="rounded-xl border border-emerald-500/30 bg-emerald-950/20 p-4 text-sm">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="font-semibold text-emerald-200">
                Job {job.job_id}
              </div>
              <div className="mt-1 text-slate-300">Status: {job.status}</div>
            </div>

            <div className="flex flex-wrap gap-2">
              <div className="rounded-full border border-emerald-400/40 px-3 py-1 text-xs font-semibold text-emerald-200">
                {job.message || "Azure processing job completed."}
              </div>

              <button
                type="button"
                onClick={loadJobReport}
                disabled={loadingReport || !job?.job_id}
                className="inline-flex h-8 min-w-[110px] items-center justify-center whitespace-nowrap rounded-full border border-blue-400/60 bg-blue-500/10 px-4 text-xs font-semibold text-blue-200 shadow-sm transition hover:-translate-y-0.5 hover:border-blue-300 hover:bg-blue-500/20 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
              >
                {loadingReport ? "Loading..." : "View Report"}
              </button>
              {isInsytAdmin() && job?.status === "completed" ? (
                <button
                  type="button"
                  onClick={archiveProcessedUploads}
                  disabled={archivingUploads || uploads.length === 0}
                  className="inline-flex h-10 items-center justify-center rounded-full border border-amber-400/60 bg-amber-500/10 px-5 text-sm font-semibold text-amber-100 shadow-sm transition hover:-translate-y-0.5 hover:border-amber-300 hover:bg-amber-500/20 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {archivingUploads ? "Archiving..." : "Archive Processed Uploads"}
                </button>
              ) : null}
            </div>
          </div>

          {archiveMessage ? (
            <div className="mt-4 rounded-xl border border-emerald-400/30 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-100">
              {archiveMessage}
            </div>
          ) : null}

          <div className="mt-4 grid gap-3 md:grid-cols-4">
            <div className="rounded-lg bg-slate-950 px-3 py-2">
              <div className="text-xs text-slate-500">Downloaded</div>
              <div className="text-base font-semibold text-slate-100">
                {downloadedCount}
              </div>
            </div>

            <div className="rounded-lg bg-slate-950 px-3 py-2">
              <div className="text-xs text-slate-500">Native/Text uploads</div>
              <div className="text-base font-semibold text-slate-100">
                {nativeTextUploadCount}
              </div>
            </div>

            <div className="rounded-lg bg-slate-950 px-3 py-2">
              <div className="text-xs text-slate-500">Reports uploaded</div>
              <div className="text-base font-semibold text-slate-100">
                {reportUploadCount}
              </div>
            </div>

            <div className="rounded-lg bg-slate-950 px-3 py-2">
              <div className="text-xs text-slate-500">Warnings</div>
              <div className="text-base font-semibold text-slate-100">
                {warningCount}
              </div>
            </div>
          </div>

          <div className="mt-4 rounded-lg bg-slate-950 px-3 py-2">
            <div className="text-xs text-slate-500">Review output</div>
            <div className="break-all text-sm text-slate-300">
              {job.routing?.review_outputs?.storage_account || "review storage"} /{" "}
              {job.routing?.review_outputs?.container || "container"}
            </div>
          </div>

          {job.review_upload?.uploads?.length ? (
            <div className="mt-4">
              <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
                Uploaded Native/Text
              </div>
              <div className="max-h-48 space-y-2 overflow-y-auto pr-1">
                {job.review_upload.uploads.map((upload: any, index: number) => (
                  <div
                    key={`${upload.blob_path}-${index}`}
                    className="rounded-lg bg-slate-950 px-3 py-2 text-xs"
                  >
                    <div className="font-medium text-slate-200">
                      {upload.doc_id} · {upload.kind} · {upload.status}
                    </div>
                    <div className="mt-1 break-all text-slate-500">
                      {upload.blob_path}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ) : null}

          {jobReport ? (
            <div className="mt-4 rounded-xl border border-blue-500/30 bg-blue-950/20 p-4">
              <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
                <div>
                  <div className="font-semibold text-blue-200">
                    Processing Report
                  </div>
                  <div className="mt-1 text-xs text-slate-500">
                    Cost telemetry and document-output summary for {job.job_id}
                  </div>
                </div>

                <div className="rounded-full border border-blue-400/40 px-3 py-1 text-xs font-semibold text-blue-200">
                  Report Loaded
                </div>
              </div>

              <div className="grid gap-3 md:grid-cols-8">
                <div className="rounded-lg bg-slate-950 px-3 py-2">
                  <div className="text-xs text-slate-500">Source files</div>
                  <div className="text-base font-semibold text-slate-100">
                    {sourceFiles ?? "—"}
                  </div>
                </div>

                <div className="rounded-lg bg-slate-950 px-3 py-2">
                  <div className="text-xs text-slate-500">Unique docs</div>
                  <div className="text-base font-semibold text-slate-100">
                    {uniqueDocs ?? "—"}
                  </div>
                </div>

                <div className="rounded-lg bg-slate-950 px-3 py-2">
                  <div className="text-xs text-slate-500">Promoted docs</div>
                  <div className="text-base font-semibold text-slate-100">
                    {promotedDocs ?? "—"}
                  </div>
                </div>

                <div className="rounded-lg bg-slate-950 px-3 py-2">
                  <div className="text-xs text-slate-500">OCR pages</div>
                  <div className="text-base font-semibold text-slate-100">
                    {ocrPages ?? "—"}
                  </div>
                </div>

                <div className="rounded-lg bg-slate-950 px-3 py-2">
                  <div className="text-xs text-slate-500">OCR estimate</div>
                  <div className="text-base font-semibold text-slate-100">
                    {typeof ocrCost === "number"
                      ? `$${ocrCost.toFixed(6)}`
                      : "—"}
                  </div>
                </div>

                <div className="rounded-lg bg-slate-950 px-3 py-2">
                  <div className="text-xs text-slate-500">Azure estimate</div>
                  <div className="text-base font-semibold text-slate-100">
                    {typeof totalAzureCost === "number"
                      ? `$${totalAzureCost.toFixed(6)}`
                      : "—"}
                  </div>
                </div>
              </div>

              {job.report_upload?.uploaded_reports?.length ? (
                <div className="mt-4">
                  <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
                    Uploaded Reports
                  </div>

                  <div className="max-h-48 space-y-2 overflow-y-auto pr-1">
                    {job.report_upload.uploaded_reports.map(
                      (report: any, index: number) => (
                        <div
                          key={`${report.blob_path}-${index}`}
                          className="rounded-lg bg-slate-950 px-3 py-2 text-xs"
                        >
                          <div className="font-medium text-slate-200">
                            {report.status || "uploaded"} ·{" "}
                            {formatBytes(report.bytes)}
                          </div>
                          <div className="mt-1 break-all text-slate-500">
                            {report.blob_path}
                          </div>
                        </div>
                      )
                    )}
                  </div>
                </div>
              ) : null}
            </div>
          ) : null}
        </div>
      ) : null}
      {showStartConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 px-4">
          <div className="w-full max-w-lg rounded-2xl border border-slate-700 bg-slate-950 p-6 shadow-2xl">
            <div className="text-lg font-semibold text-slate-100">
              Start Azure Processing?
            </div>

            <div className="mt-3 space-y-3 text-sm leading-6 text-slate-300">
              <p>
                This will process all files currently in{" "}
                <span className="font-semibold text-slate-100">
                  source/processing_center/uploads
                </span>{" "}
                for this project.
              </p>

              <p>
                INSYT will assign Doc IDs, promote review-ready Native/Text outputs to
                review storage, and generate processing reports and cost telemetry.
              </p>

              <p className="rounded-xl border border-amber-400/30 bg-amber-500/10 px-3 py-2 text-amber-100">
                Live OCR is currently disabled. OCR dry-run cost telemetry may still
                be generated.
              </p>

              {exceedsCostThreshold ? (
                <div className="rounded-xl border border-red-400/40 bg-red-500/10 px-3 py-3 text-red-100">
                  <div className="font-semibold">Cost threshold warning</div>

                  <div className="mt-1 text-sm leading-6">
                    This project currently has {uploadCount} upload(s), totaling{" "}
                    {uploadSizeBytes.toLocaleString()} bytes. The pre-run safety estimate is{" "}
                    ${estimatedPreRunCostUsd.toFixed(6)}, which meets or exceeds the current
                    demo threshold of ${costThresholdUsd.toFixed(6)}.
                  </div>

                  <label className="mt-3 flex items-start gap-2 text-sm text-red-50">
                    <input
                      type="checkbox"
                      checked={costThresholdAcknowledged}
                      onChange={(event) =>
                        setCostThresholdAcknowledged(event.target.checked)
                      }
                      className="mt-1 h-4 w-4 rounded border-red-300 bg-slate-950"
                    />
                    <span>
                      I understand this processing run may generate Azure processing and
                      storage costs, and I approve starting the job.
                    </span>
                  </label>
                </div>
              ) : null}
            </div>

            <div className="mt-6 flex justify-end gap-3">
              <button
                type="button"
                onClick={() => setShowStartConfirm(false)}
                className="inline-flex h-10 items-center justify-center rounded-full border border-slate-600 px-5 text-sm font-semibold text-slate-200 transition hover:bg-slate-800"
              >
                Cancel
              </button>

              <button
                type="button"
                onClick={() => {
                  if (starting || pollingJob) return;
                  setShowStartConfirm(false);
                  startProcessing();
                }}
                disabled={
                  starting ||
                  pollingJob ||
                  (exceedsCostThreshold && !costThresholdAcknowledged)
                }
                className="inline-flex h-10 items-center justify-center rounded-full border border-violet-400/60 bg-violet-500/20 px-5 text-sm font-semibold text-violet-100 shadow-sm transition hover:-translate-y-0.5 hover:border-violet-300 hover:bg-violet-500/30 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
              >
                {starting ? "Starting..." : "Start Processing"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}