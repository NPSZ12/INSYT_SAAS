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

type AvailableSummaryItem = {
  id?: string;
  doc_id?: string;
  summary_key?: string;
  title?: string;
  pdf_name?: string;
  native_blob?: string;
  text_blob?: string;
  outline_blob?: string;
  status?: string;
  source?: string;
  start_page?: number | null;
  end_page?: number | null;
  page?: number | null;
};

type SummaryExtractionFile = {
  doc_id: string;
  pdf_name: string;
  native_blob: string;
  text_blob?: string | null;
  outline_blob?: string | null;
  status: string;
};

type SummaryExtractionListResult = {
  status: string;
  client: string;
  project_id: string;
  storage_account?: string;
  container?: string;
  pending_count?: number;
  result_count?: number;
  files: SummaryExtractionFile[];
  manifest_count?: number;
  manifests?: unknown[];
};

type SummaryExtractionRunResult = {
  status: string;
  message: string;
  client: string;
  project_id: string;
  run_id: string;
  storage_account?: string;
  container?: string;
  manifest_blob: string;
  processed_count: number;
  skipped_count: number;
  error_count: number;
  processed: unknown[];
  skipped: unknown[];
  errors: unknown[];
};

type SummaryExtractionPromoteResult = {
  status: string;
  message: string;
  client: string;
  project_id: string;
  promotion_id: string;
  storage_account?: string;
  container?: string;
  manifest_blob: string;
  promoted_count: number;
  skipped_count: number;
  error_count: number;
  promoted: unknown[];
  skipped: unknown[];
  errors: unknown[];
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

  const [availableSummaries, setAvailableSummaries] = useState<
    AvailableSummaryItem[]
  >([]);
  const [loadingAvailableSummaries, setLoadingAvailableSummaries] =
    useState(false);

  const [pendingExtractionFiles, setPendingExtractionFiles] = useState<
    SummaryExtractionFile[]
  >([]);
  const [loadingPendingExtraction, setLoadingPendingExtraction] =
    useState(false);

  const [extractionResults, setExtractionResults] = useState<
    SummaryExtractionFile[]
  >([]);
  const [loadingExtractionResults, setLoadingExtractionResults] =
    useState(false);

  const [runningExtraction, setRunningExtraction] = useState(false);
  const [lastExtractionRun, setLastExtractionRun] =
    useState<SummaryExtractionRunResult | null>(null);

  const [promotingExtractionResults, setPromotingExtractionResults] =
    useState(false);
  const [lastExtractionPromotion, setLastExtractionPromotion] =
    useState<SummaryExtractionPromoteResult | null>(null);

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

  const availableSummariesUrl = useMemo(
    () =>
      `/api/summaries/processing-center/available-summaries?client=${encodeURIComponent(
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

  async function refreshAvailableSummaries() {
    setLoadingAvailableSummaries(true);
    setSummaryError("");
    setSummaryMessage("");

    try {
      const data = (await withTimeout(
        apiGet(availableSummariesUrl),
        "Available Summaries lookup timed out."
      )) as {
        items?: AvailableSummaryItem[];
        available_count?: number;
        outline_count?: number;
      };

      setAvailableSummaries(data.items || []);
      setSummaryMessage(
        `Loaded ${data.available_count ?? (data.items || []).length} available summary item(s) from ${data.outline_count ?? 0} outline file(s).`
      );
    } catch (err: any) {
      setSummaryError(
        cleanError(err?.message || "Unable to load available summaries.")
      );
    } finally {
      setLoadingAvailableSummaries(false);
    }
  }

  const refreshExtractionPending = async () => {
    setLoadingPendingExtraction(true);
    setSummaryError("");

    try {
      const params = new URLSearchParams({
        client: clientId,
        project: projectId,
      });

      const result = (await apiGet(
        `/api/summaries/processing-center/extraction-pending?${params.toString()}`
      )) as SummaryExtractionListResult;

      setPendingExtractionFiles(result.files || []);
    } catch (error) {
      setSummaryError(
        error instanceof Error
          ? error.message
          : "Unable to load Summary Extraction pending files."
      );
    } finally {
      setLoadingPendingExtraction(false);
    }
  };

  const refreshExtractionResults = async () => {
    setLoadingExtractionResults(true);
    setSummaryError("");

    try {
      const params = new URLSearchParams({
        client: clientId,
        project: projectId,
      });

      const result = (await apiGet(
        `/api/summaries/processing-center/extraction-pending?${params.toString()}`
      )) as SummaryExtractionListResult;

      setExtractionResults(result.files || []);
    } catch (error) {
      setSummaryError(
        error instanceof Error
          ? error.message
          : "Unable to load Summary Extraction result files."
      );
    } finally {
      setLoadingExtractionResults(false);
    }
  };

  const runSummaryExtraction = async () => {
    setRunningExtraction(true);
    setSummaryMessage("");
    setSummaryError("");

    try {
      const result = await postJsonToApi<SummaryExtractionRunResult>(
        "/api/summaries/processing-center/run-summary-extraction",
        {
          client: clientId,
          project_id: projectId,
          run_all: true,
          doc_ids: [],
          overwrite: true,
        },
        "Run Summary Extraction request timed out.",
        120000
      );

      setLastExtractionRun(result);
      setSummaryMessage(result.message || "Summary Extraction completed.");

      await refreshExtractionPending();
      await refreshExtractionResults();
    } catch (error) {
      setSummaryError(
        error instanceof Error
          ? error.message
          : "Unable to run Summary Extraction."
      );
    } finally {
      setRunningExtraction(false);
    }
  };

  const promoteExtractionResults = async () => {
    setPromotingExtractionResults(true);
    setSummaryMessage("");
    setSummaryError("");

    try {
      const result = await postJsonToApi<SummaryExtractionPromoteResult>(
        "/api/summaries/processing-center/promote-extraction-results",
        {
          client: clientId,
          project_id: projectId,
          promote_all: true,
          doc_ids: [],
          overwrite: true,
        },
        "Promote Summary Extraction results request timed out.",
        120000
      );

      setLastExtractionPromotion(result);
      setSummaryMessage(
        result.message || "Summary Extraction results promoted."
      );

      await refreshExtractionResults();
      await refreshSummariesReadyFiles();
      await refreshAvailableSummaries();
    } catch (error) {
      setSummaryError(
        error instanceof Error
          ? cleanError(error.message)
          : "Unable to promote Summary Extraction results."
      );
    } finally {
      setPromotingExtractionResults(false);
    }
  };

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
      await refreshAvailableSummaries();
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
      <div className="rounded-2xl border border-cyan-500/30 bg-cyan-950/20 p-5 text-slate-100 shadow-xl">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="text-xs font-semibold uppercase tracking-[0.18em] text-cyan-300">
              INSYT Summaries
            </div>

            <h2 className="mt-2 text-xl font-semibold">
              Summaries Processing Center
            </h2>

            <p className="mt-1 text-sm text-slate-400">
              Prepare promoted PDFs/Text for PDF Outline review, Available Summaries,
              and summary-level batching. Use Azure processing below only when new
              source PDFs still need to be uploaded, processed, or promoted.
            </p>
          </div>

          <div className="rounded-full border border-cyan-400/40 bg-cyan-500/10 px-4 py-2 text-xs font-semibold text-cyan-100">
            Summary workflow
          </div>
        </div>
      </div>

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
            <button
              type="button"
              onClick={refreshAvailableSummaries}
              disabled={
                loadingReadyFiles ||
                buildingOutlines ||
                loadingAvailableSummaries
              }
              className="inline-flex h-10 min-w-[190px] items-center justify-center whitespace-nowrap rounded-full border border-emerald-400/60 bg-emerald-500/15 px-5 text-sm font-semibold text-emerald-100 shadow-sm transition hover:-translate-y-0.5 hover:border-emerald-300 hover:bg-emerald-500/25 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
            >
              {loadingAvailableSummaries
                ? "Loading..."
                : "Refresh Available Summaries"}
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
        <div className="mt-5 rounded-xl border border-slate-800 bg-slate-900/60 p-4">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="font-medium">Available Summary Items</div>
              <div className="mt-1 text-sm text-slate-400">
                Outline-level summary items available for Summary Set batching.
              </div>
            </div>

            <div className="rounded-full border border-slate-600 px-3 py-1 text-xs font-semibold text-slate-300">
              {availableSummaries.length} item(s)
            </div>
          </div>

          {availableSummaries.length === 0 ? (
            <p className="text-sm text-slate-500">
              No available summary items loaded yet. Build PDF Outlines, then click
              Refresh Available Summaries.
            </p>
          ) : (
            <div className="max-h-96 space-y-2 overflow-y-auto pr-1">
              {availableSummaries.map((item, index) => {
                const displayTitle =
                  item.title ||
                  item.summary_key ||
                  `Summary Item ${index + 1}`;

                return (
                  <div
                    key={`${item.id || item.doc_id || "summary"}-${item.summary_key || index}`}
                    className="rounded-xl border border-slate-800 bg-slate-950 px-4 py-3 text-sm"
                  >
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <div className="font-semibold text-slate-100">
                          {displayTitle}
                        </div>

                        <div className="mt-1 text-xs text-slate-500">
                          Doc ID: {item.doc_id || "—"} · Summary Key:{" "}
                          {item.summary_key || "—"} · Status:{" "}
                          {item.status || "available"}
                        </div>

                        {item.pdf_name ? (
                          <div className="mt-1 text-xs text-slate-500">
                            PDF: {item.pdf_name}
                          </div>
                        ) : null}
                      </div>

                      <div className="rounded-full border border-emerald-400/40 bg-emerald-500/10 px-3 py-1 text-xs font-semibold text-emerald-100">
                        Batchable
                      </div>
                    </div>

                    <div className="mt-3 grid gap-2 md:grid-cols-3">
                      <div className="rounded-lg bg-slate-900 px-3 py-2">
                        <div className="text-xs text-slate-500">Page Range</div>
                        <div className="mt-1 text-xs text-slate-300">
                          {item.start_page || item.page || "—"} -{" "}
                          {item.end_page || item.page || "—"}
                        </div>
                      </div>

                      <div className="rounded-lg bg-slate-900 px-3 py-2">
                        <div className="text-xs text-slate-500">Source</div>
                        <div className="mt-1 break-all text-xs text-slate-300">
                          {item.source || "outline"}
                        </div>
                      </div>

                      <div className="rounded-lg bg-slate-900 px-3 py-2">
                        <div className="text-xs text-slate-500">Outline</div>
                        <div className="mt-1 break-all text-xs text-slate-300">
                          {item.outline_blob || "—"}
                        </div>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>

      <div className="rounded-2xl border border-slate-700 bg-slate-900/70 p-5 shadow-xl">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-cyan-300">
              Summary Extraction
            </p>
            <h2 className="mt-1 text-lg font-semibold text-white">
              Pending Extraction / Results
            </h2>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-300">
              Files uploaded from Azure Source Processing land in pending first.
              Run Summary Extraction to create result Native/Text/Outline files
              before final promotion into Summaries review.
            </p>
          </div>

          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={refreshExtractionPending}
              disabled={loadingPendingExtraction}
              className="rounded-xl border border-slate-600 px-4 py-2 text-sm font-semibold text-slate-100 hover:border-cyan-300 hover:text-cyan-100 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {loadingPendingExtraction ? "Loading..." : "Refresh Pending"}
            </button>

            <button
              type="button"
              onClick={runSummaryExtraction}
              disabled={runningExtraction || pendingExtractionFiles.length === 0}
              className="rounded-xl bg-cyan-400 px-4 py-2 text-sm font-semibold text-slate-950 hover:bg-cyan-300 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {runningExtraction ? "Running..." : "Run Summary Extraction"}
            </button>

            <button
              type="button"
              onClick={promoteExtractionResults}
              disabled={
                promotingExtractionResults ||
                runningExtraction ||
                extractionResults.length === 0
              }
              className="rounded-xl bg-emerald-400 px-4 py-2 text-sm font-semibold text-slate-950 hover:bg-emerald-300 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {promotingExtractionResults
                ? "Promoting..."
                : "Promote Extraction Results"}
            </button>

            <button
              type="button"
              onClick={refreshExtractionResults}
              disabled={loadingExtractionResults}
              className="rounded-xl border border-slate-600 px-4 py-2 text-sm font-semibold text-slate-100 hover:border-cyan-300 hover:text-cyan-100 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {loadingExtractionResults ? "Loading..." : "Refresh Results"}
            </button>
          </div>
        </div>

        {lastExtractionRun ? (
          <div className="mt-4 rounded-xl border border-emerald-400/30 bg-emerald-500/10 p-4 text-sm text-emerald-100">
            <div className="font-semibold">{lastExtractionRun.message}</div>
            <div className="mt-1 text-xs text-emerald-200">
              Processed: {lastExtractionRun.processed_count} | Skipped:{" "}
              {lastExtractionRun.skipped_count} | Errors:{" "}
              {lastExtractionRun.error_count}
            </div>
            <div className="mt-1 break-all text-xs text-emerald-200">
              Manifest: {lastExtractionRun.manifest_blob}
            </div>
          </div>
        ) : null}

        {lastExtractionPromotion ? (
          <div className="mt-4 rounded-xl border border-cyan-400/30 bg-cyan-500/10 p-4 text-sm text-cyan-100">
            <div className="font-semibold">
              {lastExtractionPromotion.message}
            </div>
            <div className="mt-1 text-xs text-cyan-200">
              Promoted: {lastExtractionPromotion.promoted_count} | Skipped:{" "}
              {lastExtractionPromotion.skipped_count} | Errors:{" "}
              {lastExtractionPromotion.error_count}
            </div>
            <div className="mt-1 break-all text-xs text-cyan-200">
              Manifest: {lastExtractionPromotion.manifest_blob}
            </div>
          </div>
        ) : null}

        <div className="mt-5 grid gap-4 lg:grid-cols-2">
          <div className="rounded-xl border border-slate-700 bg-slate-950/60 p-4">
            <div className="flex items-center justify-between gap-3">
              <h3 className="text-sm font-semibold text-white">
                Pending Files
              </h3>
              <span className="rounded-full bg-slate-800 px-3 py-1 text-xs text-slate-300">
                {pendingExtractionFiles.length}
              </span>
            </div>

            <div className="mt-3 space-y-2">
              {pendingExtractionFiles.length === 0 ? (
                <p className="text-sm text-slate-400">
                  No pending Summary Extraction files loaded.
                </p>
              ) : (
                pendingExtractionFiles.map((file) => (
                  <div
                    key={file.doc_id}
                    className="rounded-lg border border-slate-800 bg-slate-900 p-3"
                  >
                    <div className="text-sm font-semibold text-slate-100">
                      {file.doc_id}
                    </div>
                    <div className="mt-1 break-all text-xs text-slate-400">
                      {file.pdf_name}
                    </div>
                    <div className="mt-1 text-xs text-slate-500">
                      Status: {file.status}
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>

          <div className="rounded-xl border border-slate-700 bg-slate-950/60 p-4">
            <div className="flex items-center justify-between gap-3">
              <h3 className="text-sm font-semibold text-white">
                Extraction Results
              </h3>
              <span className="rounded-full bg-slate-800 px-3 py-1 text-xs text-slate-300">
                {extractionResults.length}
              </span>
            </div>

            <div className="mt-3 space-y-2">
              {extractionResults.length === 0 ? (
                <p className="text-sm text-slate-400">
                  No Summary Extraction results loaded.
                </p>
              ) : (
                extractionResults.map((file) => (
                  <div
                    key={file.doc_id}
                    className="rounded-lg border border-slate-800 bg-slate-900 p-3"
                  >
                    <div className="text-sm font-semibold text-slate-100">
                      {file.doc_id}
                    </div>
                    <div className="mt-1 break-all text-xs text-slate-400">
                      {file.pdf_name}
                    </div>
                    <div className="mt-1 text-xs text-slate-500">
                      Status: {file.status}
                    </div>
                    {file.outline_blob ? (
                      <div className="mt-1 break-all text-xs text-cyan-300">
                        Outline: {file.outline_blob}
                      </div>
                    ) : null}
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      </div>

      <AzureProcessingCenterPanel
        workspace="summaries"
        clientId={clientId}
        projectId={projectId}
        apiBase={apiBase}
        title="Azure Source Processing"
        subtitle="Optional upstream processing for Summaries source PDFs. Use this only when PDFs still need to be uploaded, processed, promoted, or archived before outline preparation."
      />
    </div>
  );
}