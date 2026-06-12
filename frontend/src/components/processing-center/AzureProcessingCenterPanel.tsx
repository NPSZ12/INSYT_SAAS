"use client";

import { useEffect, useMemo, useState } from "react";

type UploadItem = {
  name?: string;
  blob_name?: string;
  size?: number;
};

type Props = {
  workspace: "capture" | "discovery" | "summaries";
  clientId: string;
  projectId: string;
  apiBase?: string;
};

async function apiGet<T>(url: string): Promise<T> {
  const response = await fetch(url, { credentials: "include" });
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

async function apiPost<T>(url: string, body: unknown): Promise<T> {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

export default function AzureProcessingCenterPanel({ workspace, clientId, projectId, apiBase = "" }: Props) {
  const [uploads, setUploads] = useState<UploadItem[]>([]);
  const [loadingUploads, setLoadingUploads] = useState(false);
  const [starting, setStarting] = useState(false);
  const [job, setJob] = useState<any>(null);
  const [error, setError] = useState<string>("");

  const uploadsUrl = useMemo(
    () => `${apiBase}/api/${workspace}/processing-center/uploads?client=${encodeURIComponent(clientId)}&project=${encodeURIComponent(projectId)}`,
    [apiBase, workspace, clientId, projectId]
  );

  async function refreshUploads() {
    setLoadingUploads(true);
    setError("");
    try {
      const data = await apiGet<{ uploads: UploadItem[] }>(uploadsUrl);
      setUploads(data.uploads || []);
    } catch (err: any) {
      setError(err?.message || "Unable to load processing uploads.");
    } finally {
      setLoadingUploads(false);
    }
  }

  async function startProcessing() {
    setStarting(true);
    setError("");
    try {
      const data = await apiPost<any>(`${apiBase}/api/${workspace}/processing-center/azure-run/start`, {
        client: clientId,
        project: projectId,
        matter_id: `${projectId}-AZURE-RUN`,
        doc_prefix: "INSYT",
        enable_ocr_dry_run: true,
        enable_live_ocr: false,
        azure_write: true,
        overwrite: true,
      });
      setJob(data);
      await refreshUploads();
    } catch (err: any) {
      setError(err?.message || "Processing job failed.");
    } finally {
      setStarting(false);
    }
  }

  useEffect(() => {
    refreshUploads();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [uploadsUrl]);

  return (
    <div className="rounded-2xl border border-slate-700 bg-slate-950/70 p-5 text-slate-100 shadow-xl space-y-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold">Azure Processing Center</h2>
          <p className="text-sm text-slate-400">
            Intake from insytprodstorage; review-ready Native/Text outputs to insytreviewstorage.
          </p>
        </div>
        <button
          type="button"
          onClick={refreshUploads}
          disabled={loadingUploads}
          className="rounded-full border border-blue-400/40 px-4 py-2 text-sm font-medium text-blue-200 hover:bg-blue-500/10 disabled:opacity-50"
        >
          {loadingUploads ? "Refreshing..." : "Refresh Uploads"}
        </button>
      </div>

      {error ? <div className="rounded-xl border border-red-500/40 bg-red-950/40 p-3 text-sm text-red-200">{error}</div> : null}

      <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
        <div className="mb-3 flex items-center justify-between">
          <div className="font-medium">Processing uploads</div>
          <div className="text-sm text-slate-400">{uploads.length} file(s)</div>
        </div>
        {uploads.length === 0 ? (
          <p className="text-sm text-slate-500">No files found in source/processing_center/uploads.</p>
        ) : (
          <div className="space-y-2">
            {uploads.map((item, index) => (
              <div key={`${item.blob_name || item.name}-${index}`} className="rounded-lg bg-slate-950 px-3 py-2 text-sm">
                <div className="break-all text-slate-200">{item.blob_name || item.name}</div>
                <div className="text-xs text-slate-500">{item.size ?? 0} bytes</div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="flex gap-3">
        <button
          type="button"
          onClick={startProcessing}
          disabled={starting || uploads.length === 0}
          className="rounded-full bg-blue-500 px-5 py-2 text-sm font-semibold text-white hover:bg-blue-400 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {starting ? "Processing..." : "Start Azure Processing"}
        </button>
      </div>

      {job ? (
        <div className="rounded-xl border border-emerald-500/30 bg-emerald-950/20 p-4 text-sm">
          <div className="font-semibold text-emerald-200">Job {job.job_id}</div>
          <div className="mt-1 text-slate-300">Status: {job.status}</div>
          <div className="mt-1 text-slate-300">Native/Text uploaded: {job.review_upload?.uploads?.length ?? 0}</div>
          <div className="mt-1 text-slate-300">Reports uploaded: {job.report_upload?.uploaded_reports?.length ?? 0}</div>
        </div>
      ) : null}
    </div>
  );
}
