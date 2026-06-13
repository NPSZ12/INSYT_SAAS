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
  const [loadingSettings, setLoadingSettings] = useState(false);
  const [loadingUploads, setLoadingUploads] = useState(false);
  const [starting, setStarting] = useState(false);
  const [job, setJob] = useState<any>(null);
  const [error, setError] = useState<string>("");

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

  const uploadCount = uploads.length;
  const totalUploadBytes = uploads.reduce(
    (sum, item) => sum + Number(item.size || 0),
    0
  );

  const nativeTextUploadCount = job?.review_upload?.uploads?.length ?? 0;
  const reportUploadCount = job?.report_upload?.uploaded_reports?.length ?? 0;
  const downloadedCount = job?.downloads?.length ?? 0;
  const warningCount = job?.warnings?.length ?? 0;

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

  async function startProcessing() {
    if (!clientId || !projectId) {
      setError("Client and project are required before starting processing.");
      return;
    }

    setStarting(true);
    setError("");

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
            className="rounded-full border border-blue-400/40 px-4 py-2 text-sm font-medium text-blue-200 hover:bg-blue-500/10 disabled:opacity-50"
          >
            {loadingSettings || loadingUploads ? "Refreshing..." : "Refresh"}
          </button>

          <button
            type="button"
            onClick={startProcessing}
            disabled={starting || uploads.length === 0}
            className="rounded-full bg-blue-500 px-5 py-2 text-sm font-semibold text-white hover:bg-blue-400 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {starting ? "Processing..." : "Start Azure Processing"}
          </button>
        </div>
      </div>

      {error ? (
        <div className="rounded-xl border border-red-500/40 bg-red-950/40 p-3 text-sm text-red-200">
          {error}
        </div>
      ) : null}

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

            <div className="rounded-full border border-emerald-400/40 px-3 py-1 text-xs font-semibold text-emerald-200">
              {job.message || "Azure processing job completed."}
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
        </div>
      ) : null}
    </div>
  );
}