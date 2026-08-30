"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { ScanSearch, RefreshCw, Play } from "lucide-react";

import { apiGet, apiPost } from "../../../lib/api";

type DetectionReadyDoc = {
  doc_id: string;
  source_job_id: string;
  tracked_job_id?: string;
  original_filename?: string;
  extension?: string;
  source_bytes?: number;
  page_count?: number;
  native_staged_blob_path?: string;
  text_staged_blob_path?: string;
  text_staged_bytes?: number;
  promotion_status?: string;
  detection_status?: string;
};

type DetectionReadyResponse = {
  workspace: string;
  client: string;
  project: string;
  detection_ready_count: number;
  job_count: number;
  jobs: Array<{
    source_job_id: string;
    tracked_job_id?: string;
    completed_at?: string;
    ready_count: number;
  }>;
  docs: DetectionReadyDoc[];
};

type DetectionStatus = {
  status?: string;
  stage?: string;
  progress_pct?: number;
  message?: string;
  detection_job_id?: string;
  source_job_id?: string;
  documents_total?: number;
  documents_scanned?: number;
  documents_with_hits?: number;
  documents_no_hits?: number;
  documents_nfr?: number;
  documents_exception?: number;
  entity_hit_count?: number;
  entity_type_counts?: Array<{
    entity_type: string;
    hit_count: number;
    document_count: number;
  }>;
};

type DetectionSummary = {
  counts?: {
    documents_total?: number;
    documents_scanned?: number;
    documents_with_hits?: number;
    documents_no_hits?: number;
    documents_nfr?: number;
    documents_exception?: number;
    entity_hit_count?: number;
  };

  entity_type_counts?: Array<{
    entity_type: string;
    hit_count: number;
    document_count: number;
  }>;

  populations?: {
    hits?: any[];
    no_hits?: any[];
    nfr?: any[];
    exceptions?: any[];
  };

  documents?: any[];
  entities?: any[];
};

function DataElementDetectionPageContent() {
  const searchParams = useSearchParams();

  const clientId = searchParams.get("client") || "";
  const projectId = searchParams.get("project") || "";

  const [readyData, setReadyData] =
    useState<DetectionReadyResponse | null>(null);

  const [selectedDocIds, setSelectedDocIds] =
    useState<Set<string>>(new Set());

  const [loadingReady, setLoadingReady] = useState(false);
  const [startingDetection, setStartingDetection] = useState(false);

  const [detectionJobId, setDetectionJobId] = useState("");
  const [detectionStatus, setDetectionStatus] =
    useState<DetectionStatus | null>(null);

  const [detectionSummary, setDetectionSummary] =
    useState<DetectionSummary | null>(null);

  const [error, setError] = useState("");

  const readyDocs = readyData?.docs || [];

  const groupedReadyJobs = useMemo(() => {
    const groups = new Map<string, DetectionReadyDoc[]>();

    for (const doc of readyDocs) {
      const jobId = doc.source_job_id || "UNKNOWN";

      if (!groups.has(jobId)) {
        groups.set(jobId, []);
      }

      groups.get(jobId)?.push(doc);
    }

    return Array.from(groups.entries()).map(
      ([sourceJobId, docs]) => ({
        sourceJobId,
        docs,
      })
    );
  }, [readyDocs]);

  async function loadDetectionReady() {
    if (!clientId || !projectId) {
      return;
    }

    setLoadingReady(true);
    setError("");

    try {
      const params = new URLSearchParams({
        client: clientId,
        project: projectId,
      });

      const response = await apiGet(
        `/api/capture/processing-center/data-element-detection/ready?${params.toString()}`
      );

      setReadyData(response);

      const availableDocIds = new Set(
        (response?.docs || []).map(
          (doc: DetectionReadyDoc) => doc.doc_id
        )
      );

      setSelectedDocIds((current) => {
        const next = new Set<string>();

        for (const docId of current) {
          if (availableDocIds.has(docId)) {
            next.add(docId);
          }
        }

        return next;
      });
    } catch (err: any) {
      console.error(
        "Failed to load detection-ready documents:",
        err
      );

      setError(
        err?.message ||
          "Unable to load Detection Ready documents."
      );
    } finally {
      setLoadingReady(false);
    }
  }

  useEffect(() => {
    loadDetectionReady();
  }, [clientId, projectId]);

  function toggleDoc(docId: string) {
    setSelectedDocIds((current) => {
      const next = new Set(current);

      if (next.has(docId)) {
        next.delete(docId);
      } else {
        next.add(docId);
      }

      return next;
    });
  }

  function selectAllReady() {
    setSelectedDocIds(
      new Set(
        readyDocs.map((doc) => doc.doc_id)
      )
    );
  }

  function clearSelection() {
    setSelectedDocIds(new Set());
  }

  async function startDetectionForJob(
    sourceJobId: string,
    detectAllReady: boolean
  ) {
    if (!clientId || !projectId || !sourceJobId) {
      return;
    }

    const selectedForJob = readyDocs
      .filter(
        (doc) =>
          doc.source_job_id === sourceJobId &&
          selectedDocIds.has(doc.doc_id)
      )
      .map((doc) => doc.doc_id);

    if (!detectAllReady && selectedForJob.length === 0) {
      setError(
        "Select at least one Detection Ready document."
      );
      return;
    }

    setStartingDetection(true);
    setError("");
    setDetectionSummary(null);
    setDetectionStatus(null);

    try {
      const response = await apiPost(
        `/api/capture/processing-center/data-element-detection/start`,
        {
          client: clientId,
          project: projectId,
          source_job_id: sourceJobId,
          doc_ids: selectedForJob,
          detect_all_ready: detectAllReady,
          protocol_name: null,
          protocol_version: null,
          include_phi: true,
        }
      );

      const nextDetectionJobId =
        response?.detection_job_id || "";

      if (!nextDetectionJobId) {
        throw new Error(
          "Detection job was queued without a detection_job_id."
        );
      }

      setDetectionJobId(nextDetectionJobId);
      setDetectionStatus(response);
    } catch (err: any) {
      console.error(
        "Failed to start Data Element Detection:",
        err
      );

      setError(
        err?.message ||
          "Unable to start Data Element Detection."
      );
    } finally {
      setStartingDetection(false);
    }
  }

  useEffect(() => {
    if (!detectionJobId || !clientId || !projectId) {
      return;
    }

    let cancelled = false;

    async function pollDetectionStatus() {
      try {
        const params = new URLSearchParams({
          client: clientId,
          project: projectId,
        });

        const response = await apiGet(
          `/api/capture/processing-center/data-element-detection/${encodeURIComponent(
            detectionJobId
          )}/status?${params.toString()}`
        );

        if (cancelled) {
          return;
        }

        setDetectionStatus(response);

        const status = String(
          response?.status || ""
        ).toLowerCase();

        if (status === "completed") {
          await loadDetectionSummary();

          await loadDetectionReady();

          return;
        }

        if (status === "failed") {
          setError(
            response?.message ||
              "Data Element Detection failed."
          );

          return;
        }

        window.setTimeout(
          pollDetectionStatus,
          3000
        );
      } catch (err: any) {
        if (!cancelled) {
          console.error(
            "Unable to poll detection status:",
            err
          );

          window.setTimeout(
            pollDetectionStatus,
            5000
          );
        }
      }
    }

    async function loadDetectionSummary() {
      const params = new URLSearchParams({
        client: clientId,
        project: projectId,
      });

      const response = await apiGet(
        `/api/capture/processing-center/data-element-detection/${encodeURIComponent(
          detectionJobId
        )}/summary?${params.toString()}`
      );

      if (!cancelled) {
        setDetectionSummary(response);
      }
    }

    pollDetectionStatus();

    return () => {
      cancelled = true;
    };
  }, [
    detectionJobId,
    clientId,
    projectId,
  ]);

  const counts =
    detectionSummary?.counts || {};

  const documentsScanned =
    counts.documents_scanned ??
    detectionStatus?.documents_scanned ??
    0;

  const documentsWithHits =
    counts.documents_with_hits ??
    detectionStatus?.documents_with_hits ??
    0;

  const documentsNoHits =
    counts.documents_no_hits ??
    detectionStatus?.documents_no_hits ??
    0;

  const documentsNfr =
    counts.documents_nfr ??
    detectionStatus?.documents_nfr ??
    0;

  const documentsException =
    counts.documents_exception ??
    detectionStatus?.documents_exception ??
    0;

  const completedDetection =
    documentsScanned + documentsException;

  const entityTypeCounts =
    detectionSummary?.entity_type_counts ||
    detectionStatus?.entity_type_counts ||
    [];

  return (
    <main className="min-h-screen bg-slate-950 text-slate-100">
      <div className="mx-auto max-w-[1800px] px-6 py-6">
        <div className="mb-6 flex items-start justify-between gap-4">
          <div>
            <div className="mb-2 flex items-center gap-3">
              <ScanSearch className="h-7 w-7 text-sky-400" />

              <h1 className="text-2xl font-semibold text-white">
                Processing Center - Data Element Detection
              </h1>
            </div>

            <p className="max-w-4xl text-sm leading-6 text-slate-400">
              Scan ingestion-complete documents for PII,
              PHI, GDPR, and other protocol-defined data
              elements. Review detected populations,
              no-hit documents, NFR classifications,
              exceptions, and impact assessment totals
              before documents are promoted for review.
            </p>
          </div>

          <button
            type="button"
            onClick={loadDetectionReady}
            disabled={loadingReady}
            className="inline-flex items-center gap-2 rounded-xl border border-slate-700 bg-slate-900 px-4 py-2 text-sm text-slate-200 hover:bg-slate-800 disabled:opacity-50"
          >
            <RefreshCw
              className={`h-4 w-4 ${
                loadingReady ? "animate-spin" : ""
              }`}
            />

            Refresh
          </button>
        </div>

        {error ? (
          <div className="mb-5 rounded-xl border border-red-900/60 bg-red-950/40 px-4 py-3 text-sm text-red-300">
            {error}
          </div>
        ) : null}

        <div className="mb-6 grid gap-4 md:grid-cols-2 xl:grid-cols-6">
          <MetricCard
            label="Detection Ready"
            value={String(
              readyData?.detection_ready_count || 0
            )}
          />

          <MetricCard
            label="Documents Scanned"
            value={String(documentsScanned)}
          />

          <MetricCard
            label="Documents With Hits"
            value={String(documentsWithHits)}
          />

          <MetricCard
            label="No Hits"
            value={String(documentsNoHits)}
          />

          <MetricCard
            label="NFR"
            value={String(documentsNfr)}
          />

          <MetricCard
            label="Exceptions"
            value={String(documentsException)}
          />
        </div>

        <section className="mb-6 rounded-2xl border border-slate-800 bg-slate-900/60">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 px-5 py-4">
            <div>
              <h2 className="text-base font-semibold text-white">
                Detection Ready
              </h2>

              <p className="mt-1 text-sm text-slate-400">
                Documents become available here after
                Initial Ingestion, document ID assignment,
                text extraction, and any required OCR.
              </p>
            </div>

            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={selectAllReady}
                disabled={readyDocs.length === 0}
                className="rounded-lg border border-slate-700 px-3 py-2 text-xs text-slate-300 hover:bg-slate-800 disabled:opacity-40"
              >
                Select All
              </button>

              <button
                type="button"
                onClick={clearSelection}
                disabled={selectedDocIds.size === 0}
                className="rounded-lg border border-slate-700 px-3 py-2 text-xs text-slate-300 hover:bg-slate-800 disabled:opacity-40"
              >
                Clear
              </button>
            </div>
          </div>

          <div className="p-5">
            {loadingReady ? (
              <div className="rounded-xl border border-dashed border-slate-700 px-5 py-10 text-center text-sm text-slate-500">
                Loading Detection Ready documents...
              </div>
            ) : groupedReadyJobs.length === 0 ? (
              <div className="rounded-xl border border-dashed border-slate-700 px-5 py-10 text-center text-sm text-slate-500">
                No Detection Ready documents.
              </div>
            ) : (
              <div className="space-y-5">
                {groupedReadyJobs.map(
                  ({ sourceJobId, docs }) => (
                    <div
                      key={sourceJobId}
                      className="overflow-hidden rounded-xl border border-slate-800 bg-slate-950/40"
                    >
                      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 px-4 py-3">
                        <div>
                          <div className="text-xs uppercase tracking-[0.12em] text-slate-500">
                            Source APC Job
                          </div>

                          <div className="mt-1 font-mono text-xs text-slate-300">
                            {sourceJobId}
                          </div>
                        </div>

                        <div className="flex items-center gap-2">
                          <button
                            type="button"
                            disabled={
                              startingDetection ||
                              docs.length === 0
                            }
                            onClick={() =>
                              startDetectionForJob(
                                sourceJobId,
                                false
                              )
                            }
                            className="inline-flex items-center gap-2 rounded-lg border border-sky-700 bg-sky-950/40 px-3 py-2 text-xs text-sky-200 hover:bg-sky-900/60 disabled:opacity-40"
                          >
                            <Play className="h-3.5 w-3.5" />

                            Detect Selected
                          </button>

                          <button
                            type="button"
                            disabled={
                              startingDetection ||
                              docs.length === 0
                            }
                            onClick={() =>
                              startDetectionForJob(
                                sourceJobId,
                                true
                              )
                            }
                            className="inline-flex items-center gap-2 rounded-lg bg-teal-600 px-3 py-2 text-xs font-medium text-white hover:bg-teal-500 disabled:opacity-40"
                          >
                            <Play className="h-3.5 w-3.5" />

                            Detect All Ready
                          </button>
                        </div>
                      </div>

                      <div className="overflow-x-auto">
                        <table className="min-w-full text-sm">
                          <thead className="bg-slate-900/70 text-left text-xs uppercase tracking-wide text-slate-500">
                            <tr>
                              <th className="w-12 px-4 py-3">
                                Select
                              </th>

                              <th className="px-4 py-3">
                                Doc ID
                              </th>

                              <th className="px-4 py-3">
                                File
                              </th>

                              <th className="px-4 py-3">
                                Type
                              </th>

                              <th className="px-4 py-3 text-right">
                                Pages
                              </th>

                              <th className="px-4 py-3 text-right">
                                Text Bytes
                              </th>
                            </tr>
                          </thead>

                          <tbody className="divide-y divide-slate-800">
                            {docs.map((doc) => (
                              <tr
                                key={`${sourceJobId}-${doc.doc_id}`}
                                className="hover:bg-slate-900/50"
                              >
                                <td className="px-4 py-3">
                                  <input
                                    type="checkbox"
                                    checked={selectedDocIds.has(
                                      doc.doc_id
                                    )}
                                    onChange={() =>
                                      toggleDoc(doc.doc_id)
                                    }
                                    className="h-4 w-4 rounded border-slate-600 bg-slate-900"
                                  />
                                </td>

                                <td className="px-4 py-3 font-mono text-xs text-sky-300">
                                  {doc.doc_id}
                                </td>

                                <td className="max-w-[500px] truncate px-4 py-3 text-slate-200">
                                  {doc.original_filename ||
                                    "—"}
                                </td>

                                <td className="px-4 py-3 text-slate-400">
                                  {doc.extension || "—"}
                                </td>

                                <td className="px-4 py-3 text-right text-slate-300">
                                  {doc.page_count || 0}
                                </td>

                                <td className="px-4 py-3 text-right text-slate-300">
                                  {doc.text_staged_bytes || 0}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )
                )}
              </div>
            )}
          </div>
        </section>

        <section className="mb-6 rounded-2xl border border-slate-800 bg-slate-900/60">
          <div className="border-b border-slate-800 px-5 py-4">
            <h2 className="text-base font-semibold text-white">
              Detection Status
            </h2>
          </div>

          <div className="p-5">
            {!detectionJobId ? (
              <div className="rounded-xl border border-dashed border-slate-700 px-5 py-8 text-center text-sm text-slate-500">
                No Data Element Detection job started.
              </div>
            ) : (
              <div className="rounded-xl border border-slate-800 bg-slate-950/50 p-4">
                <div className="grid gap-4 md:grid-cols-4">
                  <StatusValue
                    label="Detection Job"
                    value={detectionJobId}
                  />

                  <StatusValue
                    label="Status"
                    value={
                      detectionStatus?.status || "queued"
                    }
                  />

                  <StatusValue
                    label="Stage"
                    value={
                      detectionStatus?.stage || "queued"
                    }
                  />

                  <StatusValue
                    label="Progress"
                    value={`${detectionStatus?.progress_pct || 0}%`}
                  />
                </div>

                <div className="mt-4 text-sm text-slate-400">
                  {detectionStatus?.message ||
                    "Waiting for worker..."}
                </div>
              </div>
            )}
          </div>
        </section>

        <section className="mb-6 rounded-2xl border border-slate-800 bg-slate-900/60">
          <div className="border-b border-slate-800 px-5 py-4">
            <h2 className="text-base font-semibold text-white">
              Detection Populations
            </h2>
          </div>

          <div className="grid gap-4 p-5 lg:grid-cols-4">
            <PopulationPane
              title="Completed Detection"
              description="Documents successfully scanned against the current detection configuration."
              value={completedDetection}
            />

            <PopulationPane
              title="Hits"
              description="Documents containing one or more detected data elements."
              value={documentsWithHits}
            />

            <PopulationPane
              title="No Hits"
              description="Documents scanned with no detected data elements."
              value={documentsNoHits}
            />

            <PopulationPane
              title="NFR / Exceptions"
              description="Documents classified NFR or requiring processing remediation."
              value={
                documentsNfr +
                documentsException
              }
            />
          </div>
        </section>

        <section className="rounded-2xl border border-slate-800 bg-slate-900/60">
          <div className="border-b border-slate-800 px-5 py-4">
            <h2 className="text-base font-semibold text-white">
              Impact Assessment
            </h2>

            <p className="mt-1 text-sm text-slate-400">
              Project-level counts by detected data element
              from the most recent detection run.
            </p>
          </div>

          <div className="p-5">
            {entityTypeCounts.length === 0 ? (
              <div className="rounded-xl border border-dashed border-slate-700 px-5 py-10 text-center text-sm text-slate-500">
                No detection results yet.
              </div>
            ) : (
              <div className="overflow-hidden rounded-xl border border-slate-800">
                <table className="min-w-full text-sm">
                  <thead className="bg-slate-950/80 text-left text-xs uppercase tracking-wide text-slate-500">
                    <tr>
                      <th className="px-4 py-3">
                        Data Element
                      </th>

                      <th className="px-4 py-3 text-right">
                        Documents
                      </th>

                      <th className="px-4 py-3 text-right">
                        Total Hits
                      </th>
                    </tr>
                  </thead>

                  <tbody className="divide-y divide-slate-800">
                    {entityTypeCounts.map(
                      (row) => (
                        <tr
                          key={row.entity_type}
                          className="bg-slate-950/30"
                        >
                          <td className="px-4 py-3 font-medium text-slate-200">
                            {row.entity_type}
                          </td>

                          <td className="px-4 py-3 text-right text-slate-300">
                            {row.document_count}
                          </td>

                          <td className="px-4 py-3 text-right text-slate-300">
                            {row.hit_count}
                          </td>
                        </tr>
                      )
                    )}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </section>

        <div className="mt-5 text-xs text-slate-600">
          Client: {clientId || "—"} &nbsp;•&nbsp;
          Project: {projectId || "—"}
        </div>
      </div>
    </main>
  );
}

function MetricCard({
  label,
  value,
}: {
  label: string;
  value: string;
}) {
  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-4">
      <div className="text-xs uppercase tracking-[0.14em] text-slate-500">
        {label}
      </div>

      <div className="mt-2 text-2xl font-semibold text-white">
        {value}
      </div>
    </div>
  );
}

function PopulationPane({
  title,
  description,
  value,
}: {
  title: string;
  description: string;
  value: number;
}) {
  return (
    <div className="min-h-[180px] rounded-xl border border-slate-800 bg-slate-950/50 p-4">
      <h3 className="text-sm font-semibold text-slate-100">
        {title}
      </h3>

      <p className="mt-2 text-xs leading-5 text-slate-500">
        {description}
      </p>

      <div className="mt-6 text-3xl font-semibold text-slate-300">
        {value}
      </div>
    </div>
  );
}

function StatusValue({
  label,
  value,
}: {
  label: string;
  value: string;
}) {
  return (
    <div>
      <div className="text-xs uppercase tracking-[0.12em] text-slate-500">
        {label}
      </div>

      <div className="mt-1 break-all text-sm text-slate-200">
        {value}
      </div>
    </div>
  );
}

export default function DataElementDetectionPage() {
  return (
    <Suspense
      fallback={
        <main className="min-h-screen bg-slate-950 text-slate-100">
          <div className="mx-auto max-w-[1800px] px-6 py-6">
            <div className="rounded-2xl border border-slate-800 bg-slate-900/60 px-5 py-10 text-center text-sm text-slate-500">
              Loading Data Element Detection...
            </div>
          </div>
        </main>
      }
    >
      <DataElementDetectionPageContent />
    </Suspense>
  );
}