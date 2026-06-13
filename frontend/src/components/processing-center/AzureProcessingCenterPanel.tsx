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

function cleanError(message: string) {
  try {
    const parsed = JSON.parse(message);
    return parsed?.detail || message;
  } catch {
    return message;
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

  const startUrl = useMemo(
    () => `/api/${workspace}/processing-center/azure-run/start`,
    [workspace]
  );

  const reportUrl = useMemo(() => {
    if (!job?.job_id) return "";

    return `/api/${workspace}/processing-center/jobs/${encodeURIComponent(
      job.job_id
    )}/report`;
  }, [workspace, job?.job_id]);

  const uploadCount = uploads.length;
  const totalUploadBytes = uploads.reduce(
    (sum, item) => sum + Number(item.size || 0),
    0
  );

  const nativeTextUploadCount = job?.review_upload?.uploads?.length ?? 0;
  const reportUploadCount = job?.report_upload?.uploaded_reports?.length ?? 0;
  const downloadedCount = job?.downloads?.length ?? 0;
  const warningCount = job?.warnings?.length ?? 0;

  const reportSummary =
    jobReport?.summary ||
    jobReport?.report ||
    jobReport?.job_report ||
    jobReport ||
    null;

  const sourceFiles =
    reportSummary?.source_file_count ??
    reportSummary?.source_files ??
    reportSummary?.source_data?.source_files ??
    reportSummary?.sourceData?.sourceFiles ??
    null;

  const uniqueDocs =
    reportSummary?.unique_doc_count ??
    reportSummary?.unique_docs ??
    reportSummary?.source_data?.unique_docs ??
    reportSummary?.sourceData?.uniqueDocs ??
    null;

  const ocrPages =
    reportSummary?.ocr_page_count ??
    reportSummary?.ocr_estimated_pages ??
    reportSummary?.ocr?.estimated_pages ??
    reportSummary?.ocr?.pages ??
    null;

  const ocrCost =
    reportSummary?.ocr_estimated_cost ??
    reportSummary?.ocr_cost_estimated_usd ??
    reportSummary?.ocr?.estimated_cost_usd ??
    null;

  const totalAzureCost =
    reportSummary?.estimated_azure_cost_usd ??
    reportSummary?.total_estimated_azure_cost ??
    reportSummary?.azure_cost?.total_estimated_cost ??
    null;

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

  async function refreshSettings() {
    setLoadingSettings(true);
    setError("");

    try {
      const data = (await apiGet(settingsUrl)) as ProcessingSettings;
      setSettings(data);
    } catch (err: any) {
      setError(cleanError(err?.message || "Unable to load APC settings."));
    } finally {
      setLoadingSettings(false);
    }
  }

  async function refreshUploads() {
    setLoadingUploads(true);
    setError("");

    try {
      const data = (await apiGet(uploadsUrl)) as { uploads: UploadItem[] };
      setUploads(data.uploads || []);
    } catch (err: any) {
      setError(cleanError(err?.message || "Unable to load processing uploads."));
    } finally {
      setLoadingUploads(false);
    }
  }

  async function refreshAll() {
    await Promise.all([refreshSettings(), refreshUploads()]);
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

      setSelectedFile(null);
      await refreshUploads();
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

    try {
      const data = (await apiPost(startUrl, {
        client: clientId,
        project: projectId,
        matter_id: `${projectId}-AZURE-RUN`,
        doc_prefix: "INSYT",
        enable_ocr_dry_run: true,
        enable_live_ocr: false,
        azure_write: true,
        overwrite: true,
      })) as any;

      setJob(data);
      await refreshUploads();
    } catch (err: any) {
      setError(cleanError(err?.message || "Processing job failed."));
    } finally {
      setStarting(false);
    }
  }


  useEffect(() => {
    refreshAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [settingsUrl, uploadsUrl]);

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
            disabled={loadingSettings || loadingUploads}
            className="inline-flex h-10 min-w-[110px] items-center justify-center whitespace-nowrap rounded-full border border-blue-400/60 bg-blue-500/10 px-5 text-sm font-semibold text-blue-200 shadow-sm transition hover:-translate-y-0.5 hover:border-blue-300 hover:bg-blue-500/20 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
          >
            {loadingSettings || loadingUploads ? "Refreshing..." : "Refresh"}
          </button>

          <button
            type="button"
            onClick={startProcessing}
            disabled={starting || uploads.length === 0 || !isInsytAdmin()}
            className="inline-flex h-10 min-w-[190px] items-center justify-center whitespace-nowrap rounded-full border border-violet-400/60 bg-violet-500/20 px-5 text-sm font-semibold text-violet-100 shadow-sm transition hover:-translate-y-0.5 hover:border-violet-300 hover:bg-violet-500/30 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
          >
            {starting ? "Processing..." : "Start Azure Processing"}
          </button>
          {!isInsytAdmin() ? (
            <div className="text-xs text-slate-500">
              Upload is available to clients. Processing commitment is currently reserved for INSYT Admin.
            </div>
          ) : null}
        </div>
      </div>

      {error ? (
        <div className="rounded-xl border border-red-500/40 bg-red-950/40 p-3 text-sm text-red-200">
          {error}
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
        <div className="mb-3 flex items-center justify-between">
          <div className="font-medium">Processing uploads</div>
          <div className="text-sm text-slate-400">
            {uploads.length} file(s)
          </div>
        </div>

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
                  <div className="break-all text-slate-200">{displayName}</div>
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
            </div>
          </div>

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

              <div className="grid gap-3 md:grid-cols-5">
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
    </div>
  );
}