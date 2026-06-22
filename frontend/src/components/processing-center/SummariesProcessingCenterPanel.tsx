"use client";

import { useMemo, useState } from "react";

import { apiGet } from "../../lib/api";
import AzureProcessingCenterPanel from "./AzureProcessingCenterPanel";

type Props = {
  clientId: string;
  projectId: string;
  apiBase?: string;
};

type SummaryReadyFile = {
  doc_id?: string;
  pdf_name?: string;
  name?: string;
  native_blob?: string;
  text_blob?: string;
  outline_blob?: string;
  summary_count?: number;
  status?: string;
  last_modified?: string;
};

type OutlineBuildResult = {
  status?: string;
  message?: string;
  client?: string;
  project_id?: string;
  processed_count?: number;
  skipped_count?: number;
  outlines?: SummaryReadyFile[];
};

function cleanError(message: string) {
  try {
    const parsed = JSON.parse(message);
    return parsed?.detail || message;
  } catch {
    return message;
  }
}

function formatDateTime(value?: string) {
  if (!value) return "—";

  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
}

async function withTimeout<T>(
  promise: Promise<T>,
  message: string,
  timeoutMs = 30000
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
    if (timeoutId) clearTimeout(timeoutId);
  }
}

export default function SummariesProcessingCenterPanel({
  clientId,
  projectId,
  apiBase = "",
}: Props) {
  const [readyFiles, setReadyFiles] = useState<SummaryReadyFile[]>([]);
  const [loadingReadyFiles, setLoadingReadyFiles] = useState(false);
  const [buildingOutlines, setBuildingOutlines] = useState(false);
  const [summaryMessage, setSummaryMessage] = useState("");
  const [summaryError, setSummaryError] = useState("");
  const [lastBuildResult, setLastBuildResult] =
    useState<OutlineBuildResult | null>(null);

  function resolveApiBase() {
    return (
      apiBase ||
      process.env.NEXT_PUBLIC_API_BASE_URL ||
      "https://api.insyt360.com"
    ).replace(/\/+$/, "");
  }

  function getAuthHeaders(json = true): HeadersInit {
    const token = localStorage.getItem("insyt_token");

    return {
      accept: "application/json",
      ...(json ? { "Content-Type": "application/json" } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    };
  }

  async function postJsonToApi<T = any>(
    path: string,
    body: Record<string, any>,
    timeoutMessage: string,
    timeoutMs = 60000
  ): Promise<T> {
    const resolvedApiBase = resolveApiBase();

    const response = await withTimeout(
      fetch(`${resolvedApiBase}${path}`, {
        method: "POST",
        headers: getAuthHeaders(true),
        credentials: "include",
        body: JSON.stringify(body),
      }),
      timeoutMessage,
      timeoutMs
    );

    const text = await response.text();

    if (!response.ok) {
      throw new Error(text || `POST ${path} failed with status ${response.status}.`);
    }

    try {
      return (text ? JSON.parse(text) : {}) as T;
    } catch {
      return {} as T;
    }
  }

  const summariesReadyUrl = useMemo(
    () =>
      `/api/summaries/processing-center/summaries-ready?client=${encodeURIComponent(
        clientId
      )}&project=${encodeURIComponent(projectId)}`,
    [clientId, projectId]
  );

  async function refreshSummariesReadyFiles() {
    setLoadingReadyFiles(true);
    setSummaryError("");
    setSummaryMessage("");

    try {
      const data = (await withTimeout(
        apiGet(summariesReadyUrl),
        "Summaries-ready file lookup timed out."
      )) as {
        files?: SummaryReadyFile[];
      };

      setReadyFiles(data.files || []);
      setSummaryMessage(
        `Loaded ${(data.files || []).length} summaries-ready file(s).`
      );
    } catch (err: any) {
      setSummaryError(
        cleanError(err?.message || "Unable to load summaries-ready files.")
      );
    } finally {
      setLoadingReadyFiles(false);
    }
  }

  async function buildPdfOutlines() {
    if (!clientId || !projectId) {
      setSummaryError("Client and project are required before building outlines.");
      return;
    }

    setBuildingOutlines(true);
    setSummaryError("");
    setSummaryMessage("");
    setLastBuildResult(null);

    try {
      const result = await postJsonToApi<OutlineBuildResult>(
        "/api/summaries/processing-center/build-outlines",
        {
          client: clientId,
          project_id: projectId,
          overwrite: true,
        },
        "Build Summaries outlines request timed out.",
        120000
      );

      setLastBuildResult(result);

      setSummaryMessage(
        result?.message ||
          `Built outlines for ${result?.processed_count ?? 0} file(s).`
      );

      await refreshSummariesReadyFiles();
    } catch (err: any) {
      setSummaryError(
        cleanError(err?.message || "Unable to build Summaries outlines.")
      );
    } finally {
      setBuildingOutlines(false);
    }
  }

  return (
    <div className="space-y-5">
      <AzureProcessingCenterPanel
        workspace="summaries"
        clientId={clientId}
        projectId={projectId}
        apiBase={apiBase}
        title="INSYT Summaries Processing Center"
        subtitle="Upload source PDFs, run Summaries processing, prepare review-ready text, and build PDF outline and summary-level batching outputs."
      />

      <div className="rounded-2xl border border-cyan-500/30 bg-slate-950/80 p-5 text-slate-100 shadow-xl">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h2 className="text-lg font-semibold">
              Summaries Preparation Center
            </h2>
            <p className="mt-1 text-sm text-slate-400">
              After Azure processing/promote completes, use this section to find
              review-ready PDFs/Text and build PDF Outline + Available Summary items
              for INSYT Summaries batching.
            </p>
          </div>

          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={refreshSummariesReadyFiles}
              disabled={loadingReadyFiles || buildingOutlines}
              className="inline-flex h-10 min-w-[150px] items-center justify-center whitespace-nowrap rounded-full border border-blue-400/60 bg-blue-500/10 px-5 text-sm font-semibold text-blue-200 shadow-sm transition hover:-translate-y-0.5 hover:border-blue-300 hover:bg-blue-500/20 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
            >
              {loadingReadyFiles ? "Loading..." : "Refresh Ready Files"}
            </button>

            <button
              type="button"
              onClick={buildPdfOutlines}
              disabled={buildingOutlines || loadingReadyFiles}
              className="inline-flex h-10 min-w-[170px] items-center justify-center whitespace-nowrap rounded-full border border-cyan-400/60 bg-cyan-500/15 px-5 text-sm font-semibold text-cyan-100 shadow-sm transition hover:-translate-y-0.5 hover:border-cyan-300 hover:bg-cyan-500/25 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
            >
              {buildingOutlines ? "Building..." : "Build PDF Outlines"}
            </button>
          </div>
        </div>

        {summaryError ? (
          <div className="mt-4 rounded-xl border border-red-500/40 bg-red-950/40 p-3 text-sm text-red-200">
            {summaryError}
          </div>
        ) : null}

        {summaryMessage ? (
          <div className="mt-4 rounded-xl border border-emerald-500/30 bg-emerald-950/30 p-3 text-sm text-emerald-200">
            {summaryMessage}
          </div>
        ) : null}

        {lastBuildResult ? (
          <div className="mt-4 grid gap-3 md:grid-cols-3">
            <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-4">
              <div className="text-xs uppercase tracking-wide text-slate-500">
                Processed
              </div>
              <div className="mt-1 text-lg font-semibold text-slate-100">
                {lastBuildResult.processed_count ?? 0}
              </div>
            </div>

            <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-4">
              <div className="text-xs uppercase tracking-wide text-slate-500">
                Skipped
              </div>
              <div className="mt-1 text-lg font-semibold text-slate-100">
                {lastBuildResult.skipped_count ?? 0}
              </div>
            </div>

            <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-4">
              <div className="text-xs uppercase tracking-wide text-slate-500">
                Status
              </div>
              <div className="mt-1 text-lg font-semibold text-slate-100">
                {lastBuildResult.status || "—"}
              </div>
            </div>
          </div>
        ) : null}

        <div className="mt-5 rounded-xl border border-slate-800 bg-slate-900/60 p-4">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="font-medium">Summaries-ready files</div>
              <div className="mt-1 text-sm text-slate-400">
                Promoted PDFs/Text available for outline generation and summary-level batching.
              </div>
            </div>

            <div className="rounded-full border border-slate-600 px-3 py-1 text-xs font-semibold text-slate-300">
              {readyFiles.length} file(s)
            </div>
          </div>

          {readyFiles.length === 0 ? (
            <p className="text-sm text-slate-500">
              No summaries-ready files loaded yet. Click Refresh Ready Files after
              processing/promotion completes.
            </p>
          ) : (
            <div className="max-h-80 space-y-2 overflow-y-auto pr-1">
              {readyFiles.map((file, index) => {
                const displayName =
                  file.pdf_name || file.name || file.doc_id || "Unknown PDF";

                return (
                  <div
                    key={`${file.doc_id || displayName}-${index}`}
                    className="rounded-xl border border-slate-800 bg-slate-950 px-4 py-3 text-sm"
                  >
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <div className="font-semibold text-slate-100">
                          {displayName}
                        </div>

                        <div className="mt-1 text-xs text-slate-500">
                          Doc ID: {file.doc_id || "—"} · Status:{" "}
                          {file.status || "ready"}
                        </div>
                      </div>

                      <div className="rounded-full border border-cyan-400/40 bg-cyan-500/10 px-3 py-1 text-xs font-semibold text-cyan-100">
                        {file.summary_count ?? 0} summary item(s)
                      </div>
                    </div>

                    <div className="mt-3 grid gap-2 md:grid-cols-3">
                      <div className="rounded-lg bg-slate-900 px-3 py-2">
                        <div className="text-xs text-slate-500">Native PDF</div>
                        <div className="mt-1 break-all text-xs text-slate-300">
                          {file.native_blob || "—"}
                        </div>
                      </div>

                      <div className="rounded-lg bg-slate-900 px-3 py-2">
                        <div className="text-xs text-slate-500">Text</div>
                        <div className="mt-1 break-all text-xs text-slate-300">
                          {file.text_blob || "—"}
                        </div>
                      </div>

                      <div className="rounded-lg bg-slate-900 px-3 py-2">
                        <div className="text-xs text-slate-500">Outline</div>
                        <div className="mt-1 break-all text-xs text-slate-300">
                          {file.outline_blob || "Not built yet"}
                        </div>
                      </div>
                    </div>

                    {file.last_modified ? (
                      <div className="mt-2 text-xs text-slate-600">
                        Updated: {formatDateTime(file.last_modified)}
                      </div>
                    ) : null}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}