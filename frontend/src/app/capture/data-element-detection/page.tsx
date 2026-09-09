"use client";

import {
  Suspense,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { useSearchParams } from "next/navigation";
import { ScanSearch, RefreshCw, Play, Download } from "lucide-react";

import AppShell from "../../../components/AppShell";
import {
  apiGet,
  apiPost,
  buildApiUrl,
} from "../../../lib/api";


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

  impact_assessment?: {
    documents_with_hits_only?: number;
    rough_names_with_attached_elements?: number;
    total_elements_identified?: number;
    rough_name_method?: string;
    element_breakdown?: Array<{
      entity_type: string;
      document_count: number;
      hit_count: number;
    }>;
  };
};

function DataElementDetectionPageContent() {
  const searchParams = useSearchParams();

  const clientId = searchParams.get("client") || "";
  const projectId = searchParams.get("project") || "";

  const [readyData, setReadyData] =
    useState<DetectionReadyResponse | null>(null);

  const [selectedDocIds, setSelectedDocIds] =
    useState<Set<string>>(new Set());

  const [
    initialLoadingReady,
    setInitialLoadingReady,
  ] = useState(true);

  const [
    refreshingReady,
    setRefreshingReady,
  ] = useState(false);
  const [startingDetection, setStartingDetection] = useState(false);

  const [detectionJobId, setDetectionJobId] = useState("");
  const [detectionStatus, setDetectionStatus] =
    useState<DetectionStatus | null>(null);

  const [detectionSummary, setDetectionSummary] =
    useState<DetectionSummary | null>(null);

  const [
    projectImpact,
    setProjectImpact,
  ] = useState<any | null>(null);

  const [
    loadingProjectImpact,
    setLoadingProjectImpact,
  ] = useState(false);

  const [
    completedProjectFilters,
    setCompletedProjectFilters,
  ] = useState({
    doc_id: "",
    original_file: "",
    workbook: "",
    sheet: "",
    classification: "",
    entities: "",
    elements: "",
    detection_job: "",
    detection_date: "",
    source_job: "",
  });

  type CompletedProjectSortKey =
    | "doc_id"
    | "original_file"
    | "workbook"
    | "sheet"
    | "classification"
    | "entities"
    | "elements"
    | "detection_job"
    | "detection_date"
    | "source_job";

  const [
    completedProjectSort,
    setCompletedProjectSort,
  ] = useState<{
    key: CompletedProjectSortKey;
    direction: "asc" | "desc";
  }>({
    key: "doc_id",
    direction: "asc",
  });

  function toggleCompletedProjectSort(
    key: CompletedProjectSortKey
  ) {
    setCompletedProjectSort(
      (current) => ({
        key,
        direction:
          current.key === key &&
          current.direction === "asc"
            ? "desc"
            : "asc",
      })
    );
  }

  const [error, setError] = useState("");

  const readyDocs = readyData?.docs || [];

  const groupedReadyJobs = useMemo(() => {
    const groups = new Map<string, DetectionReadyDoc[]>();

    for (const doc of readyDocs) {
      const jobId =
        doc.source_job_id ||
        "UNKNOWN";

      if (!groups.has(jobId)) {
        groups.set(jobId, []);
      }

      groups.get(jobId)?.push(doc);
    }

    const jobDateById =
      new Map<string, string>();

    for (const job of readyData?.jobs || []) {
      const jobId =
        String(
          job.source_job_id ||
          ""
        ).trim();

      if (jobId) {
        jobDateById.set(
          jobId,
          String(
            job.completed_at ||
            ""
          ).trim()
        );
      }
    }

    return Array.from(
      groups.entries()
    ).map(
      ([sourceJobId, docs]) => ({
        sourceJobId,
        docs,
        jobDate:
          jobDateById.get(
            sourceJobId
          ) || "",
      })
    );
  }, [
    readyDocs,
    readyData?.jobs,
  ]);

  const filteredCompletedProjectDocs = useMemo(() => {
    const docs: any[] =
      Array.isArray(projectImpact?.documents)
        ? projectImpact.documents
        : [];

    const contains = (
      value: unknown,
      filter: string
    ) => {
      if (!filter.trim()) {
        return true;
      }

      return String(value ?? "")
        .toLowerCase()
        .includes(filter.trim().toLowerCase());
    };

    const filtered = docs.filter((doc) => {
      const hits = Array.isArray(doc?.hits)
        ? doc.hits
        : [];

      const elementTypes = Array.from(
        new Set(
          hits
            .map(
              (hit: any) =>
                hit?.entity_type ||
                hit?.category ||
                hit?.type ||
                ""
            )
            .filter(Boolean)
        )
      ).join(", ");

      const originalFile =
        doc.original_filename ||
        doc.original_workbook_name ||
        "";

      const detectionJob =
        doc.latest_detection_job_id ||
        doc.detection_job_id ||
        "";

      const detectionDate =
        doc.detected_at ||
        doc.document_index_last_modified ||
        "";

      return (
        contains(
          doc.doc_id,
          completedProjectFilters.doc_id
        ) &&
        contains(
          originalFile,
          completedProjectFilters.original_file
        ) &&
        contains(
          doc.original_workbook_name,
          completedProjectFilters.workbook
        ) &&
        contains(
          doc.sheet_name,
          completedProjectFilters.sheet
        ) &&
        contains(
          doc.classification,
          completedProjectFilters.classification
        ) &&
        contains(
          hits.length,
          completedProjectFilters.entities
        ) &&
        contains(
          elementTypes,
          completedProjectFilters.elements
        ) &&
        contains(
          detectionJob,
          completedProjectFilters.detection_job
        ) &&
        contains(
          detectionDate,
          completedProjectFilters.detection_date
        ) &&
        contains(
          doc.source_job_id,
          completedProjectFilters.source_job
        )
      );
    });

  const getSortValue = (
    doc: any
  ) => {
    const hits =
      Array.isArray(doc.hits)
        ? doc.hits
        : [];

    const elementTypes =
      Array.from(
        new Set(
          hits
            .map(
              (hit: any) =>
                String(
                  hit.entity_type ||
                  hit.category ||
                  hit.type ||
                  ""
                ).trim()
            )
            .filter(Boolean)
        )
      ).join(", ");

    const originalFile =
      doc.original_filename ||
      doc.original_workbook_name ||
      "";

    const detectionJob =
      doc.latest_detection_job_id ||
      doc.detection_job_id ||
      "";

    const detectionDate =
      doc.detected_at ||
      doc.document_index_last_modified ||
      "";

    switch (
      completedProjectSort.key
    ) {
      case "doc_id":
        return String(
          doc.doc_id || ""
        );

      case "original_file":
        return String(
          originalFile
        );

      case "workbook":
        return String(
          doc.original_workbook_name ||
          ""
        );

      case "sheet":
        return String(
          doc.sheet_name ||
          ""
        );

      case "classification":
        return String(
          doc.classification ||
          ""
        );

      case "entities":
        return hits.length;

      case "elements":
        return elementTypes;

      case "detection_job":
        return String(
          detectionJob
        );

      case "detection_date":
        return String(
          detectionDate
        );

      case "source_job":
        return String(
          doc.source_job_id ||
          ""
        );

      default:
        return "";
    }
  };

  return [
    ...filtered,
  ].sort(
    (a, b) => {
      const aValue =
        getSortValue(a);
      const bValue =
        getSortValue(b);

      let comparison = 0;

      if (
        typeof aValue === "number" &&
        typeof bValue === "number"
      ) {
        comparison =
          aValue - bValue;
      } else {
        comparison =
          String(aValue)
            .localeCompare(
              String(bValue),
              undefined,
              {
                numeric: true,
                sensitivity: "base",
              }
            );
      }

      return completedProjectSort
        .direction === "asc"
        ? comparison
        : -comparison;
    }
  );
  }, [
  projectImpact,
  completedProjectFilters,
  completedProjectSort,
  ]);

  async function loadDetectionReady(
    isRefresh = false
  ) {
    if (!clientId || !projectId) {
      setInitialLoadingReady(false);
      return;
    }

    if (isRefresh) {
      setRefreshingReady(true);
    } else {
      setInitialLoadingReady(true);
    }

    setError("");

    try {
      const params =
        new URLSearchParams({
          client: clientId,
          project: projectId,
        });

      const response =
        await apiGet(
          `/api/capture/processing-center/data-element-detection/ready?${params.toString()}`
        );

      setReadyData(response);

      const availableDocIds =
        new Set(
          (
            response?.docs ||
            []
          ).map(
            (
              doc: DetectionReadyDoc
            ) => doc.doc_id
          )
        );

      setSelectedDocIds(
        (current) => {
          const next =
            new Set<string>();

          for (const docId of current) {
            if (
              availableDocIds.has(
                docId
              )
            ) {
              next.add(docId);
            }
          }

          return next;
        }
      );

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
      setInitialLoadingReady(false);
      setRefreshingReady(false);
    }
  }

  async function loadProjectImpactAssessment() {
    if (!clientId || !projectId) {
      return;
    }

    setLoadingProjectImpact(true);

    try {
      const params =
        new URLSearchParams({
          client: clientId,
          project: projectId,
        });

      const response =
        await apiGet(
          `/api/capture/processing-center/` +
            `data-element-detection/` +
            `project-impact-assessment?` +
            params.toString()
        );

      setProjectImpact(
        response
      );

    } catch (err: any) {
      console.error(
        "Unable to load project Impact Assessment:",
        err
      );

    } finally {
      setLoadingProjectImpact(false);
    }
  }

  useEffect(() => {
    loadDetectionReady();
    loadProjectImpactAssessment();
  }, [
    clientId,
    projectId,
  ]);

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

  function selectAllForJob(
    docs: DetectionReadyDoc[]
  ) {
    setSelectedDocIds((current) => {
      const next = new Set(current);

      for (const doc of docs) {
        next.add(doc.doc_id);
      }

      return next;
    });
  }

  function clearSelectionForJob(
    docs: DetectionReadyDoc[]
  ) {
    const jobDocIds = new Set(
      docs.map((doc) => doc.doc_id)
    );

    setSelectedDocIds((current) => {
      const next = new Set<string>();

      for (const docId of current) {
        if (!jobDocIds.has(docId)) {
          next.add(docId);
        }
      }

      return next;
    });
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

          await loadDetectionReady(true);

          await loadProjectImpactAssessment();

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
          2000
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
  
  const impactAssessment =
    detectionSummary?.impact_assessment || {};

  const impactDocumentsWithHits =
    impactAssessment.documents_with_hits_only ??
    documentsWithHits;

  const roughNamesWithElements =
    impactAssessment.rough_names_with_attached_elements ??
    0;

  const totalElementsIdentified =
    impactAssessment.total_elements_identified ??
    counts.entity_hit_count ??
    detectionStatus?.entity_hit_count ??
    0;

  function exportImpactAssessmentReport() {
    if (!detectionJobId || !clientId || !projectId) {
      return;
    }

    const params = new URLSearchParams({
      client: clientId,
      project: projectId,
    });

    const url =
      `/api/capture/processing-center/data-element-detection/` +
      `${encodeURIComponent(detectionJobId)}/impact-assessment.xlsx?` +
      params.toString();

    window.open(
      buildApiUrl(url),
      "_blank"
    );
  }

  function exportProjectImpactAssessmentReport() {
    if (!clientId || !projectId) {
      return;
    }

    const params =
      new URLSearchParams({
        client: clientId,
        project: projectId,
      });

    const url =
      `/api/capture/processing-center/` +
      `data-element-detection/` +
      `project-impact-assessment.xlsx?` +
      params.toString();

    window.open(
      buildApiUrl(url),
      "_blank"
    );
  }

  return (
    <div className="min-h-full bg-slate-950 text-slate-100">
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
            onClick={() =>
              loadDetectionReady(true)
            }
            disabled={refreshingReady}
            className="inline-flex items-center gap-2 rounded-xl border border-slate-700 bg-slate-900 px-4 py-2 text-sm text-slate-200 hover:bg-slate-800 disabled:opacity-50"
          >
            <RefreshCw
              className={`h-4 w-4 ${
                refreshingReady
                  ? "animate-spin"
                  : ""
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

        <CollapsiblePane
          title="Detection Ready"
          description="Documents become available here after Initial Ingestion, document ID assignment, text extraction, and any required OCR."
          className="mb-6"
          actions={
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
          }
        >
          <div className="max-h-[520px] overflow-y-auto p-5">
            {initialLoadingReady ? (
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
                  ({
                    sourceJobId,
                    docs,
                    jobDate,
                  }) => (
                    <div
                      key={sourceJobId}
                      className="overflow-hidden rounded-xl border border-slate-800 bg-slate-950/40"
                    >
                      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 px-4 py-3">
                        <div>
                          <div className="text-xs uppercase tracking-[0.12em] text-slate-500">
                            Source APC Job
                          </div>

                          <div className="mt-1 flex flex-wrap items-center gap-2">
                            <span className="font-mono text-xs text-slate-300">
                              {sourceJobId}
                            </span>

                            <span className="text-xs text-slate-500">
                              • {docs.length.toLocaleString()}{" "}
                              {docs.length === 1 ? "doc" : "docs"}
                            </span>

                            {jobDate ? (
                              <span className="text-xs text-slate-500">
                                •{" "}
                                {new Date(
                                  jobDate
                                ).toLocaleString()}
                              </span>
                            ) : null}

                          </div>
                        </div>

                        <div className="flex flex-wrap items-center gap-2">
                          <button
                            type="button"
                            onClick={() => selectAllForJob(docs)}
                            disabled={docs.length === 0}
                            className="rounded-lg border border-indigo-600 bg-indigo-950/50 px-3 py-2 text-xs font-medium text-indigo-200 transition-colors hover:border-violet-500 hover:bg-violet-700 hover:text-white disabled:cursor-not-allowed disabled:opacity-40"
                          >
                            Select All
                          </button>

                          <button
                            type="button"
                            onClick={() => clearSelectionForJob(docs)}
                            disabled={
                              !docs.some((doc) =>
                                selectedDocIds.has(doc.doc_id)
                              )
                            }
                            className="rounded-lg border border-slate-600 bg-slate-900 px-3 py-2 text-xs font-medium text-slate-300 transition-colors duration-150 hover:border-slate-400 hover:bg-slate-700 hover:text-white disabled:cursor-not-allowed disabled:opacity-40"
                          >
                            Clear Selection
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
                                false
                              )
                            }
                            className="inline-flex items-center gap-2 rounded-lg border border-sky-600 bg-sky-700 px-3 py-2 text-xs font-medium text-white transition-colors duration-150 hover:border-sky-400 hover:bg-sky-600 disabled:cursor-not-allowed disabled:opacity-40"
                          >
                            <Play className="h-3.5 w-3.5" />

                            Detect Selected
                          </button>

                          <button
                            type="button"
                            disabled={
                              startingDetection ||
                              docs.length === 0 ||
                              !docs.some((doc) =>
                                selectedDocIds.has(doc.doc_id)
                              )
                            }
                            onClick={() =>
                              startDetectionForJob(
                                sourceJobId,
                                true
                              )
                            }
                            className="inline-flex items-center gap-2 rounded-lg border border-teal-500 bg-teal-600 px-3 py-2 text-xs font-medium text-white transition-colors duration-150 hover:border-teal-300 hover:bg-teal-500 disabled:cursor-not-allowed disabled:opacity-40"
                          >
                            <Play className="h-3.5 w-3.5" />

                            Detect All Ready
                          </button>
                        </div>
                      </div>

                      <div className="max-h-[360px] overflow-auto">
                        <table className="min-w-full text-sm">
                          <thead className="sticky top-0 z-10 bg-slate-900 text-left text-xs uppercase tracking-wide text-slate-500">
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
        </CollapsiblePane>

        <CollapsiblePane
          title="Detection Status"
          className="mb-6"
        >

          <div className="max-h-[260px] overflow-y-auto p-5">
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
        </CollapsiblePane>

        <CollapsiblePane
          title="Detection Populations"
          className="mb-6"
        >

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
        </CollapsiblePane>

        <CollapsiblePane
          title="Impact Assessment - Set"
          description="Latest completed Detection set only. Counts and detected data elements for the documents processed in the current Detection run."
          className="mb-6"
          actions={
            <button
              type="button"
              onClick={exportImpactAssessmentReport}
              disabled={!detectionJobId || !detectionSummary}
              className="inline-flex items-center gap-2 rounded-lg border border-sky-700 bg-sky-950/40 px-3 py-2 text-xs font-semibold text-sky-200 hover:bg-sky-900/60 disabled:opacity-40"
            >
              <Download className="h-4 w-4" />
              Export Impact Assessment XL - Set
            </button>
          }
        >

          <div className="p-5">
              <div className="mb-5 grid gap-4 md:grid-cols-3">
                <MetricCard
                  label="Documents With Hits Only"
                  value={String(impactDocumentsWithHits)}
                />

                <MetricCard
                  label="Rough Names With Attached Elements"
                  value={String(roughNamesWithElements)}
                />

                <MetricCard
                  label="Total Elements Identified"
                  value={String(totalElementsIdentified)}
                />
              </div>


            {entityTypeCounts.length === 0 ? (
              <div className="rounded-xl border border-dashed border-slate-700 px-5 py-10 text-center text-sm text-slate-500">
                No detection results yet.
              </div>
            ) : (
              <div className="max-h-[420px] overflow-auto rounded-xl border border-slate-800">
                <table className="min-w-full text-sm">
                  <thead className="sticky top-0 z-10 bg-slate-950 text-left text-xs uppercase tracking-wide text-slate-500">
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
        </CollapsiblePane>

        <CollapsiblePane
          title="Impact Assessment - Project"
          description="Cumulative project assessment of every document that has completed Data Element Detection through the current time. Each Doc ID is counted once using its latest completed Detection result."
          className="mb-6"
          actions={
            <button
              type="button"
              onClick={exportProjectImpactAssessmentReport}
              disabled={
                !projectImpact ||
                Number(
                  projectImpact?.counts
                    ?.documents_completed || 0
                ) === 0
              }
              className="inline-flex items-center gap-2 rounded-lg border border-violet-700 bg-violet-950/40 px-3 py-2 text-xs font-semibold text-violet-200 hover:bg-violet-900/60 disabled:opacity-40"
            >
              <Download className="h-4 w-4" />
              Export Impact Assessment XL - Project
            </button>
          }
        >

          <div className="p-5">
            {loadingProjectImpact ? (
              <div className="rounded-xl border border-dashed border-slate-700 px-5 py-10 text-center text-sm text-slate-500">
                Loading project Impact Assessment...
              </div>
            ) : (
              <>
                <div className="mb-5 grid gap-4 md:grid-cols-3 xl:grid-cols-6">
                  <MetricCard
                    label="Completed Detection"
                    value={String(
                      projectImpact?.counts
                        ?.documents_completed || 0
                    )}
                  />

                  <MetricCard
                    label="Hits"
                    value={String(
                      projectImpact?.counts
                        ?.documents_with_hits || 0
                    )}
                  />

                  <MetricCard
                    label="No Hits"
                    value={String(
                      projectImpact?.counts
                        ?.documents_no_hits || 0
                    )}
                  />

                  <MetricCard
                    label="NFR"
                    value={String(
                      projectImpact?.counts
                        ?.documents_nfr || 0
                    )}
                  />

                  <MetricCard
                    label="Exceptions"
                    value={String(
                      projectImpact?.counts
                        ?.documents_exception || 0
                    )}
                  />

                  <MetricCard
                    label="Elements Identified"
                    value={String(
                      projectImpact?.counts
                        ?.entity_hit_count || 0
                    )}
                  />
                </div>

                {(projectImpact?.entity_type_counts || [])
                  .length === 0 ? (
                  <div className="rounded-xl border border-dashed border-slate-700 px-5 py-10 text-center text-sm text-slate-500">
                    No completed project Detection results yet.
                  </div>
                ) : (
                  <div className="max-h-[420px] overflow-auto rounded-xl border border-slate-800">
                    <table className="min-w-full text-sm">
                      <thead className="sticky top-0 z-10 bg-slate-950 text-left text-xs uppercase tracking-wide text-slate-500">
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
                        {(
                          projectImpact
                            ?.entity_type_counts ||
                          []
                        ).map(
                          (row: any) => (
                            <tr
                              key={
                                row.entity_type
                              }
                            >
                              <td className="px-4 py-3 text-slate-200">
                                {row.entity_type}
                              </td>

                              <td className="px-4 py-3 text-right text-slate-300">
                                {row.document_count || 0}
                              </td>

                              <td className="px-4 py-3 text-right text-slate-300">
                                {row.hit_count || 0}
                              </td>
                            </tr>
                          )
                        )}
                      </tbody>
                    </table>
                  </div>
                )}
              </>
            )}
          </div>
        </CollapsiblePane>

        <CollapsiblePane
          title="Completed Detection - Project"
          description="Every document in this project with a completed Data Element Detection result, using the latest completed Detection state per Doc ID."
          className="mb-6"
        >

          <div className="p-5">
            {loadingProjectImpact ? (
              <div className="rounded-xl border border-dashed border-slate-700 px-5 py-10 text-center text-sm text-slate-500">
                Loading completed Detection documents...
              </div>
            ) : (projectImpact?.documents || []).length === 0 ? (
              <div className="rounded-xl border border-dashed border-slate-700 px-5 py-10 text-center text-sm text-slate-500">
                No completed Detection documents yet.
              </div>
            ) : (
              <div className="max-h-[420px] overflow-auto rounded-xl border border-slate-800">
                <table className="min-w-full text-sm">
                  <thead className="sticky top-0 z-10 bg-slate-950 text-left text-xs uppercase tracking-wide text-slate-500">
                    <tr>
                      <th className="px-4 py-3">
                        <button
                          type="button"
                          onClick={() =>
                            toggleCompletedProjectSort(
                              "doc_id"
                            )
                          }
                          className="whitespace-nowrap hover:text-slate-200"
                        >
                          Doc ID{" "}
                          {completedProjectSort.key ===
                          "doc_id"
                            ? completedProjectSort.direction ===
                              "asc"
                              ? "↑"
                              : "↓"
                            : "↕"}
                        </button>
                      </th>

                      <th className="px-4 py-3">
                        <button
                          type="button"
                          onClick={() =>
                            toggleCompletedProjectSort(
                              "original_file"
                            )
                          }
                          className="whitespace-nowrap hover:text-slate-200"
                        >
                          Original File{" "}
                          {completedProjectSort.key ===
                          "original_file"
                            ? completedProjectSort.direction ===
                              "asc"
                              ? "↑"
                              : "↓"
                            : "↕"}
                        </button>
                      </th>

                      <th className="px-4 py-3">
                        <button
                          type="button"
                          onClick={() =>
                            toggleCompletedProjectSort(
                              "workbook"
                            )
                          }
                          className="whitespace-nowrap hover:text-slate-200"
                        >
                          Workbook{" "}
                          {completedProjectSort.key ===
                          "workbook"
                            ? completedProjectSort.direction ===
                              "asc"
                              ? "↑"
                              : "↓"
                            : "↕"}
                        </button>
                      </th>

                      <th className="px-4 py-3">
                        <button
                          type="button"
                          onClick={() =>
                            toggleCompletedProjectSort(
                              "sheet"
                            )
                          }
                          className="whitespace-nowrap hover:text-slate-200"
                        >
                          Sheet{" "}
                          {completedProjectSort.key ===
                          "sheet"
                            ? completedProjectSort.direction ===
                              "asc"
                              ? "↑"
                              : "↓"
                            : "↕"}
                        </button>
                      </th>

                      <th className="px-4 py-3">
                        <button
                          type="button"
                          onClick={() =>
                            toggleCompletedProjectSort(
                              "classification"
                            )
                          }
                          className="whitespace-nowrap hover:text-slate-200"
                        >
                          Classification{" "}
                          {completedProjectSort.key ===
                          "classification"
                            ? completedProjectSort.direction ===
                              "asc"
                              ? "↑"
                              : "↓"
                            : "↕"}
                        </button>
                      </th>

                      <th className="px-4 py-3 text-right">
                        <button
                          type="button"
                          onClick={() =>
                            toggleCompletedProjectSort(
                              "entities"
                            )
                          }
                          className="whitespace-nowrap hover:text-slate-200"
                        >
                          Entities{" "}
                          {completedProjectSort.key ===
                          "entities"
                            ? completedProjectSort.direction ===
                              "asc"
                              ? "↑"
                              : "↓"
                            : "↕"}
                        </button>
                      </th>

                      <th className="px-4 py-3">
                        <button
                          type="button"
                          onClick={() =>
                            toggleCompletedProjectSort(
                              "elements"
                            )
                          }
                          className="whitespace-nowrap hover:text-slate-200"
                        >
                          Detected Data Elements{" "}
                          {completedProjectSort.key ===
                          "elements"
                            ? completedProjectSort.direction ===
                              "asc"
                              ? "↑"
                              : "↓"
                            : "↕"}
                        </button>
                      </th>

                      <th className="px-4 py-3">
                        <button
                          type="button"
                          onClick={() =>
                            toggleCompletedProjectSort(
                              "detection_job"
                            )
                          }
                          className="whitespace-nowrap hover:text-slate-200"
                        >
                          Detection Job{" "}
                          {completedProjectSort.key ===
                          "detection_job"
                            ? completedProjectSort.direction ===
                              "asc"
                              ? "↑"
                              : "↓"
                            : "↕"}
                        </button>
                      </th>

                      <th className="px-4 py-3">
                        <button
                          type="button"
                          onClick={() =>
                            toggleCompletedProjectSort(
                              "detection_date"
                            )
                          }
                          className="whitespace-nowrap hover:text-slate-200"
                        >
                          Detection Date{" "}
                          {completedProjectSort.key ===
                          "detection_date"
                            ? completedProjectSort.direction ===
                              "asc"
                              ? "↑"
                              : "↓"
                            : "↕"}
                        </button>
                      </th>

                      <th className="px-4 py-3">
                        <button
                          type="button"
                          onClick={() =>
                            toggleCompletedProjectSort(
                              "source_job"
                            )
                          }
                          className="whitespace-nowrap hover:text-slate-200"
                        >
                          Source Job{" "}
                          {completedProjectSort.key ===
                          "source_job"
                            ? completedProjectSort.direction ===
                              "asc"
                              ? "↑"
                              : "↓"
                            : "↕"}
                        </button>
                      </th>
                      </tr>

                      <tr className="border-t border-slate-800 bg-slate-950">
                        {[
                          ["doc_id", "Search Doc ID"],
                          ["original_file", "Search file"],
                          ["workbook", "Search workbook"],
                          ["sheet", "Search sheet"],
                          ["classification", "Filter class"],
                          ["entities", "Filter count"],
                          ["elements", "Search elements"],
                          ["detection_job", "Search Detection job"],
                          ["detection_date", "Search date"],
                          ["source_job", "Search source job"],
                        ].map(([field, placeholder]) => (
                          <th
                            key={field}
                            className="px-2 pb-3"
                          >
                            <input
                              type="text"
                              value={
                                completedProjectFilters[
                                  field as keyof typeof completedProjectFilters
                                ]
                              }
                              onChange={(event) =>
                                setCompletedProjectFilters(
                                  (current) => ({
                                    ...current,
                                    [field]: event.target.value,
                                  })
                                )
                              }
                              placeholder={placeholder}
                              className="w-full min-w-[110px] rounded-md border border-slate-700 bg-slate-900 px-2 py-1.5 text-xs font-normal normal-case tracking-normal text-slate-200 outline-none placeholder:text-slate-600 focus:border-sky-600"
                            />
                          </th>
                        ))}
                      </tr>
                      </thead>

                  <tbody className="divide-y divide-slate-800">
                    {filteredCompletedProjectDocs.map(
                      (doc: any) => {
                        const hits = Array.isArray(doc?.hits)
                          ? doc.hits
                          : [];

                        return (
                          <tr key={doc.doc_id}>
                            <td className="px-4 py-3 font-mono text-xs text-sky-300">
                              {doc.doc_id || "—"}
                            </td>

                            <td className="max-w-[360px] truncate px-4 py-3 text-slate-200">
                              {doc.original_filename ||
                                doc.original_workbook_name ||
                                "—"}
                            </td>

                            <td className="max-w-[280px] truncate px-4 py-3 text-slate-400">
                              {doc.original_workbook_name || "—"}
                            </td>

                            <td className="px-4 py-3 text-slate-400">
                              {doc.sheet_name || "—"}
                            </td>

                            <td className="px-4 py-3 text-slate-300">
                              {doc.classification || "—"}
                            </td>

                            <td className="px-4 py-3 text-right text-slate-300">
                              {hits.length}
                            </td>

                            <td className="max-w-[360px] px-4 py-3 text-slate-300">
                              {Array.from(
                                new Set(
                                  hits
                                    .map(
                                      (hit: any) =>
                                        hit?.entity_type ||
                                        hit?.category ||
                                        hit?.type ||
                                        ""
                                    )
                                    .filter(Boolean)
                                )
                              ).join(", ") || "—"}
                            </td>

                            <td className="px-4 py-3 font-mono text-xs text-slate-400">
                              {doc.latest_detection_job_id ||
                                doc.detection_job_id ||
                                "—"}
                            </td>

                            <td className="px-4 py-3 text-slate-400">
                              {doc.detected_at ||
                                doc.document_index_last_modified ||
                                "—"}
                            </td>

                            <td className="px-4 py-3 font-mono text-xs text-slate-400">
                              {doc.source_job_id || "—"}
                            </td>
                          </tr>
                        );
                      }
                    )}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </CollapsiblePane>

        <div className="mt-5 text-xs text-slate-600">
          Client: {clientId || "—"} &nbsp;•&nbsp;
          Project: {projectId || "—"}
        </div>
      </div>
    </div>
  );
}

function CollapsiblePane({
  title,
  description,
  actions,
  children,
  className = "",
}: {
  title: string;
  description?: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  const [open, setOpen] = useState(false);

  return (
    <section
      className={`rounded-2xl border border-slate-800 bg-slate-900/60 ${className}`}
    >
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 px-5 py-4">
        <button
          type="button"
          onClick={() =>
            setOpen((current) => !current)
          }
          className="flex min-w-0 flex-1 items-center gap-3 text-left"
        >
          <span className="w-4 shrink-0 text-xs text-slate-400">
            {open ? "▼" : "▶"}
          </span>

          <div className="min-w-0">
            <h2 className="text-base font-semibold text-white">
              {title}
            </h2>

            {description ? (
              <p className="mt-1 text-sm text-slate-400">
                {description}
              </p>
            ) : null}
          </div>
        </button>

        {actions ? (
          <div className="shrink-0">
            {actions}
          </div>
        ) : null}
      </div>

      {open ? children : null}
    </section>
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
    <AppShell>
      <Suspense
        fallback={
          <div className="min-h-full bg-slate-950 text-slate-100">
            <div className="mx-auto max-w-[1800px] px-6 py-6">
              <div className="rounded-2xl border border-slate-800 bg-slate-900/60 px-5 py-10 text-center text-sm text-slate-500">
                Loading Data Element Detection...
              </div>
            </div>
          </div>
        }
      >
        <DataElementDetectionPageContent />
      </Suspense>
    </AppShell>
  );
}