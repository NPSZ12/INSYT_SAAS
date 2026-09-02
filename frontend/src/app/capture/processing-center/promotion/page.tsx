"use client";

import {
  Fragment,
  Suspense,
  useEffect,
  useMemo,
  useState,
} from "react";

import { useSearchParams } from "next/navigation";

import {
  Archive,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  CircleAlert,
  Database,
  FileCheck2,
  FileSpreadsheet,
  FileText,
  FolderArchive,
  RefreshCw,
  Route,
  Search,
  Send,
  ShieldCheck,
  XCircle,
} from "lucide-react";

import AppShell from "../../../../components/AppShell";
import { apiGet, apiPost } from "../../../../lib/api";


type PromotionDoc = {
  doc_id: string;
  file_id?: string;

  source_job_id?: string;
  detection_job_id?: string;

  classification?: string;
  destination?: string;
  promotion_status?: string;
  ready_for_promotion?: boolean;

  original_filename?: string;
  extension?: string;

  source_type?: string;
  is_workbook_sheet?: boolean;

  original_workbook_file_id?: string;
  original_workbook_name?: string;

  sheet_name?: string;
  sheet_index?: number | null;
  sheet_visibility?: string;

  native_staged_blob_path?: string;
  text_staged_blob_path?: string;

  final_native_blob_path?: string;
  final_text_blob_path?: string;

  entity_types?: string[];
  profiled_entity_count?: number;

  detection_mode?: string;
  type_profile_complete?: boolean | null;
  entity_counts_complete?: boolean | null;
};


type PromotionResponse = {
  workspace?: string;
  client?: string;
  project?: string;

  detection_job_id?: string | null;
  source_job_id?: string | null;

  spreadsheet_hits?: PromotionDoc[];
  review_hits?: PromotionDoc[];
  no_hits?: PromotionDoc[];
  nfr?: PromotionDoc[];
  exceptions?: PromotionDoc[];

  counts?: {
    spreadsheet_hits?: number;
    review_hits?: number;
    no_hits?: number;
    nfr?: number;
    exceptions?: number;
    total?: number;
  };

  detection_result_paths?: {
    summary?: string;
    documents?: string;
    entities?: string;
  };
};


type PromotionFolder =
  | "spreadsheet_hits"
  | "review_hits"
  | "no_hits"
  | "nfr"
  | "exceptions";


type FolderDefinition = {
  key: PromotionFolder;
  title: string;
  shortTitle: string;
  description: string;
};


const FOLDERS: FolderDefinition[] = [
  {
    key: "spreadsheet_hits",
    title: "Spreadsheet / CSV Hits",
    shortTitle: "Spreadsheet Hits",
    description:
      "Worksheet-derived CSVs and other CSV data containing responsive elements. These records are routed to the Cyber² data workflow rather than ordinary document review.",
  },
  {
    key: "review_hits",
    title: "Document Review Hits",
    shortTitle: "Review Hits",
    description:
      "Responsive non-spreadsheet documents ready to be promoted into the normal INSYT review population.",
  },
  {
    key: "no_hits",
    title: "No Hits",
    shortTitle: "No Hits",
    description:
      "Documents and worksheet children that completed Detection but did not meet the current responsiveness criteria. They remain retained for defensibility but are excluded from the responsive review population.",
  },
  {
    key: "nfr",
    title: "NFR",
    shortTitle: "NFR",
    description:
      "Documents classified as Not For Review under the current processing or protocol rules.",
  },
  {
    key: "exceptions",
    title: "Exceptions",
    shortTitle: "Exceptions",
    description:
      "Documents requiring remediation before they can be routed or promoted.",
  },
];


function ProcessingCenterPromotionPageContent() {
  const searchParams = useSearchParams();

  const clientId =
    searchParams.get("client") || "";

  const projectId =
    searchParams.get("project") || "";

  const workspace =
    searchParams.get("workspace") ||
    "capture";

  const [promotionData, setPromotionData] =
    useState<PromotionResponse | null>(null);

  const [loading, setLoading] =
    useState(false);

  const [error, setError] =
    useState("");

  const [promotingReview, setPromotingReview] =
    useState(false);

  const [searchText, setSearchText] =
    useState("");

  const [
    selectedSpreadsheetIds,
    setSelectedSpreadsheetIds,
  ] = useState<Set<string>>(
    new Set()
  );

  const [
    selectedReviewIds,
    setSelectedReviewIds,
  ] = useState<Set<string>>(
    new Set()
  );

  const [
    expandedRows,
    setExpandedRows,
  ] = useState<Set<string>>(
    new Set()
  );

  const [
    openFolders,
    setOpenFolders,
  ] = useState<
    Record<PromotionFolder, boolean>
  >({
    spreadsheet_hits: true,
    review_hits: true,
    no_hits: true,
    nfr: false,
    exceptions: false,
  });


  const spreadsheetHits =
    promotionData?.spreadsheet_hits || [];

  const reviewHits =
    promotionData?.review_hits || [];

  const noHits =
    promotionData?.no_hits || [];

  const nfr =
    promotionData?.nfr || [];

  const exceptions =
    promotionData?.exceptions || [];


  const counts =
    promotionData?.counts || {};


  async function loadPromotionPopulation() {
    if (!clientId || !projectId) {
      return;
    }

    setLoading(true);
    setError("");

    try {
      const params =
        new URLSearchParams({
          client: clientId,
          project: projectId,
        });

      const response =
        await apiGet(
          `/api/${encodeURIComponent(
            workspace
          )}/processing-center/promotion?${params.toString()}`
        );

      setPromotionData(response);

      const validSpreadsheetIds =
        new Set(
          (
            response?.spreadsheet_hits ||
            []
          ).map(
            (doc: PromotionDoc) =>
              doc.doc_id
          )
        );

      const validReviewIds =
        new Set(
          (
            response?.review_hits ||
            []
          ).map(
            (doc: PromotionDoc) =>
              doc.doc_id
          )
        );

      setSelectedSpreadsheetIds(
        (current) => {
          const next =
            new Set<string>();

          for (const docId of current) {
            if (
              validSpreadsheetIds.has(
                docId
              )
            ) {
              next.add(docId);
            }
          }

          return next;
        }
      );

      setSelectedReviewIds(
        (current) => {
          const next =
            new Set<string>();

          for (const docId of current) {
            if (
              validReviewIds.has(
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
        "Failed to load Promotion Center:",
        err
      );

      setError(
        err?.message ||
          "Unable to load Promotion Center population."
      );

    } finally {
      setLoading(false);
    }
  }


  useEffect(() => {
    loadPromotionPopulation();
  }, [
    clientId,
    projectId,
    workspace,
  ]);


  function toggleFolder(
    folder: PromotionFolder
  ) {
    setOpenFolders(
      (current) => ({
        ...current,
        [folder]:
          !current[folder],
      })
    );
  }


  function toggleExpandedRow(
    docId: string
  ) {
    setExpandedRows(
      (current) => {
        const next =
          new Set(current);

        if (next.has(docId)) {
          next.delete(docId);
        } else {
          next.add(docId);
        }

        return next;
      }
    );
  }


  function toggleSpreadsheetDoc(
    docId: string
  ) {
    setSelectedSpreadsheetIds(
      (current) => {
        const next =
          new Set(current);

        if (next.has(docId)) {
          next.delete(docId);
        } else {
          next.add(docId);
        }

        return next;
      }
    );
  }


  function toggleReviewDoc(
    docId: string
  ) {
    setSelectedReviewIds(
      (current) => {
        const next =
          new Set(current);

        if (next.has(docId)) {
          next.delete(docId);
        } else {
          next.add(docId);
        }

        return next;
      }
    );
  }


  function normalizeSearchValue(
    value: unknown
  ) {
    return String(
      value ?? ""
    )
      .trim()
      .toLowerCase();
  }


  function matchesSearch(
    doc: PromotionDoc
  ) {
    const search =
      normalizeSearchValue(
        searchText
      );

    if (!search) {
      return true;
    }

    const haystack = [
      doc.doc_id,
      doc.file_id,
      doc.original_filename,
      doc.original_workbook_name,
      doc.sheet_name,
      doc.extension,
      doc.classification,
      doc.destination,
      doc.promotion_status,
      doc.source_type,
      doc.detection_mode,
      ...(doc.entity_types || []),
    ]
      .map(normalizeSearchValue)
      .join(" ");

    return haystack.includes(
      search
    );
  }


  const filteredSpreadsheetHits =
    useMemo(
      () =>
        spreadsheetHits.filter(
          matchesSearch
        ),
      [
        spreadsheetHits,
        searchText,
      ]
    );


  const filteredReviewHits =
    useMemo(
      () =>
        reviewHits.filter(
          matchesSearch
        ),
      [
        reviewHits,
        searchText,
      ]
    );


  const filteredNoHits =
    useMemo(
      () =>
        noHits.filter(
          matchesSearch
        ),
      [
        noHits,
        searchText,
      ]
    );


  const filteredNfr =
    useMemo(
      () =>
        nfr.filter(
          matchesSearch
        ),
      [
        nfr,
        searchText,
      ]
    );


  const filteredExceptions =
    useMemo(
      () =>
        exceptions.filter(
          matchesSearch
        ),
      [
        exceptions,
        searchText,
      ]
    );


  function selectAllSpreadsheetHits() {
    setSelectedSpreadsheetIds(
      new Set(
        filteredSpreadsheetHits.map(
          (doc) => doc.doc_id
        )
      )
    );
  }


  function clearSpreadsheetSelection() {
    setSelectedSpreadsheetIds(
      new Set()
    );
  }


  function selectAllReviewHits() {
    setSelectedReviewIds(
      new Set(
        filteredReviewHits.map(
          (doc) => doc.doc_id
        )
      )
    );
  }


  function clearReviewSelection() {
    setSelectedReviewIds(
      new Set()
    );
  }


  function placeholderCyber2Action() {
    if (
      selectedSpreadsheetIds.size ===
      0
    ) {
      setError(
        "Select at least one Spreadsheet / CSV Hit."
      );

      return;
    }

    setError(
      "Cyber² promotion action is not wired yet. Population selection is working and ready for the write endpoint."
    );
  }


async function promoteSelectedToReview() {
  if (
    selectedReviewIds.size === 0
  ) {
    setError(
      "Select at least one Document Review Hit."
    );

    return;
  }

  if (!clientId || !projectId) {
    setError(
      "Client and project are required for Review promotion."
    );

    return;
  }

  const docIds = Array.from(
    selectedReviewIds
  );

  setPromotingReview(true);
  setError("");

  try {
    const response = await apiPost(
      `/api/${encodeURIComponent(
        workspace
      )}/processing-center/promotion/promote-review`,
      {
        client: clientId,
        project: projectId,
        doc_ids: docIds,
        overwrite: false,
      }
    );

    const promotedCount =
      Number(
        response?.promoted_count || 0
      );

    const skippedCount =
      Number(
        response?.skipped_count || 0
      );

    const errorCount =
      Number(
        response?.source_job_error_count || 0
      );

    if (
      skippedCount > 0 ||
      errorCount > 0
    ) {
      console.warn(
        "Review promotion completed with skipped/errors:",
        response
      );
    }

    setSelectedReviewIds(
      new Set()
    );

    await loadPromotionPopulation();

    if (
      promotedCount === 0
    ) {
      setError(
        response?.message ||
          "No documents were promoted to Review."
      );
    }

  } catch (err: any) {
    console.error(
      "Failed to promote selected documents to Review:",
      err
    );

    setError(
      err?.message ||
        "Unable to promote selected documents to Review."
    );

  } finally {
    setPromotingReview(false);
  }
}


  const totalProcessed =
    counts.total ??
    (
      spreadsheetHits.length +
      reviewHits.length +
      noHits.length +
      nfr.length +
      exceptions.length
    );


  const spreadsheetHitCount =
    counts.spreadsheet_hits ??
    spreadsheetHits.length;


  const reviewHitCount =
    counts.review_hits ??
    reviewHits.length;


  const noHitCount =
    counts.no_hits ??
    noHits.length;


  const nfrCount =
    counts.nfr ??
    nfr.length;


  const exceptionCount =
    counts.exceptions ??
    exceptions.length;


  const hasDetectionPopulation =
    Boolean(
      promotionData
        ?.detection_job_id
    );


  return (
    <div className="min-h-full bg-slate-950 text-slate-100">
      <div className="mx-auto max-w-[1900px] px-6 py-6">

        {/* Page Header */}

        <div className="mb-6 flex flex-wrap items-start justify-between gap-4">

          <div>
            <div className="mb-2 flex items-center gap-3">
              <Route className="h-7 w-7 text-sky-400" />

              <h1 className="text-2xl font-semibold text-white">
                Processing Center - Promotion
              </h1>
            </div>

            <p className="max-w-5xl text-sm leading-6 text-slate-400">
              Final routing point for documents that completed
              Initial Ingestion and Data Element Detection.
              Responsive spreadsheet and worksheet-derived CSV
              data is separated for Cyber² processing, ordinary
              responsive documents are prepared for Review, and
              No Hit documents remain retained outside the
              responsive review population.
            </p>

            <div className="mt-3 flex flex-wrap gap-2 text-xs text-slate-500">

              <span>
                Source APC Job:{" "}
                <span className="font-mono text-slate-300">
                  {promotionData
                    ?.source_job_id ||
                    "—"}
                </span>
              </span>

              <span>•</span>

              <span>
                Detection Job:{" "}
                <span className="font-mono text-slate-300">
                  {promotionData
                    ?.detection_job_id ||
                    "—"}
                </span>
              </span>
            </div>
          </div>


          <button
            type="button"
            onClick={
              loadPromotionPopulation
            }
            disabled={loading}
            className="inline-flex items-center gap-2 rounded-xl border border-slate-700 bg-slate-900 px-4 py-2 text-sm text-slate-200 transition-colors hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <RefreshCw
              className={`h-4 w-4 ${
                loading
                  ? "animate-spin"
                  : ""
              }`}
            />

            Refresh
          </button>

        </div>


        {/* Error / Status Banner */}

        {error ? (
          <div className="mb-5 flex items-start justify-between gap-4 rounded-xl border border-amber-800/60 bg-amber-950/30 px-4 py-3 text-sm text-amber-200">

            <div className="flex items-start gap-2">
              <CircleAlert className="mt-0.5 h-4 w-4 shrink-0" />

              <span>
                {error}
              </span>
            </div>

            <button
              type="button"
              onClick={() =>
                setError("")
              }
              className="text-amber-300 hover:text-white"
              title="Dismiss"
            >
              <XCircle className="h-4 w-4" />
            </button>

          </div>
        ) : null}


        {/* Metrics */}

        <div className="mb-6 grid gap-4 md:grid-cols-2 xl:grid-cols-6">

          <MetricCard
            label="Total Processed"
            value={String(
              totalProcessed
            )}
            detail="Latest Detection population"
          />

          <MetricCard
            label="Spreadsheet Hits"
            value={String(
              spreadsheetHitCount
            )}
            detail="Cyber² destination"
          />

          <MetricCard
            label="Review Hits"
            value={String(
              reviewHitCount
            )}
            detail="Review destination"
          />

          <MetricCard
            label="No Hits"
            value={String(
              noHitCount
            )}
            detail="Retained / excluded"
          />

          <MetricCard
            label="NFR"
            value={String(
              nfrCount
            )}
            detail="Not For Review"
          />

          <MetricCard
            label="Exceptions"
            value={String(
              exceptionCount
            )}
            detail="Requires remediation"
          />

        </div>


        {/* Routing Explanation */}

        <section className="mb-6 rounded-2xl border border-slate-800 bg-slate-900/60">

          <div className="border-b border-slate-800 px-5 py-4">
            <div className="flex items-center gap-2">
              <Route className="h-5 w-5 text-sky-400" />

              <h2 className="text-base font-semibold text-white">
                Promotion Routing
              </h2>
            </div>

            <p className="mt-1 max-w-5xl text-sm leading-6 text-slate-400">
              Promotion routing is determined by document type
              and Detection classification. The original workbook
              remains preserved as the source container; only
              responsive worksheet-derived CSV children are routed
              into Cyber².
            </p>
          </div>


          <div className="grid gap-4 p-5 md:grid-cols-3">

            <RoutingCard
              icon={
                <FileSpreadsheet className="h-5 w-5 text-violet-300" />
              }
              title="Spreadsheet / CSV HIT"
              destination="Cyber²"
              description="Responsive worksheet-derived CSV data is routed to the data-processing workflow."
            />

            <RoutingCard
              icon={
                <FileCheck2 className="h-5 w-5 text-sky-300" />
              }
              title="Document HIT"
              destination="Review"
              description="Responsive ordinary documents are promoted into the normal review population."
            />

            <RoutingCard
              icon={
                <FolderArchive className="h-5 w-5 text-slate-300" />
              }
              title="NO HIT"
              destination="Retained"
              description="No Hit documents remain preserved and defensible without entering the responsive review population."
            />

          </div>

        </section>


        {/* Search */}

        <div className="mb-6">

          <div className="relative max-w-2xl">

            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" />

            <input
              type="text"
              value={searchText}
              onChange={(event) =>
                setSearchText(
                  event.target.value
                )
              }
              placeholder="Search Doc ID, workbook, worksheet, file, entity type, destination..."
              className="w-full rounded-xl border border-slate-700 bg-slate-900 py-2.5 pl-10 pr-4 text-sm text-slate-200 outline-none transition-colors placeholder:text-slate-600 focus:border-sky-600"
            />

          </div>

        </div>


        {/* Loading */}

        {loading ? (

          <div className="rounded-2xl border border-slate-800 bg-slate-900/60 px-5 py-16 text-center">

            <RefreshCw className="mx-auto mb-3 h-6 w-6 animate-spin text-sky-400" />

            <div className="text-sm text-slate-400">
              Loading Promotion population...
            </div>

          </div>

        ) : !hasDetectionPopulation ? (

          <div className="rounded-2xl border border-dashed border-slate-700 bg-slate-900/40 px-6 py-16 text-center">

            <ShieldCheck className="mx-auto mb-4 h-8 w-8 text-slate-600" />

            <div className="text-base font-medium text-slate-300">
              No completed Detection population is available for Promotion.
            </div>

            <div className="mx-auto mt-2 max-w-2xl text-sm leading-6 text-slate-500">
              Complete Data Element Detection for the project.
              The latest completed Detection result will then
              populate this page automatically.
            </div>

          </div>

        ) : (

          <div className="space-y-6">

            {/* Spreadsheet Hits */}

            <PromotionSection
              folderKey="spreadsheet_hits"
              title="Spreadsheet / CSV Hits"
              description="Responsive spreadsheet data routed to Cyber². Worksheet-derived CSV children remain linked to their preserved source workbook."
              count={
                spreadsheetHitCount
              }
              icon={
                <FileSpreadsheet className="h-5 w-5 text-violet-300" />
              }
              open={
                openFolders
                  .spreadsheet_hits
              }
              onToggle={() =>
                toggleFolder(
                  "spreadsheet_hits"
                )
              }
              headerActions={
                <div className="flex flex-wrap items-center gap-2">

                  <button
                    type="button"
                    onClick={
                      selectAllSpreadsheetHits
                    }
                    disabled={
                      filteredSpreadsheetHits.length ===
                      0
                    }
                    className="rounded-lg border border-violet-700 bg-violet-950/30 px-3 py-2 text-xs font-medium text-violet-200 hover:bg-violet-900/50 disabled:opacity-40"
                  >
                    Select All
                  </button>

                  <button
                    type="button"
                    onClick={
                      clearSpreadsheetSelection
                    }
                    disabled={
                      selectedSpreadsheetIds.size ===
                      0
                    }
                    className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-xs font-medium text-slate-300 hover:bg-slate-800 disabled:opacity-40"
                  >
                    Clear
                  </button>

                  <button
                    type="button"
                    onClick={
                      placeholderCyber2Action
                    }
                    disabled={
                      selectedSpreadsheetIds.size ===
                      0
                    }
                    className="inline-flex items-center gap-2 rounded-lg border border-violet-500 bg-violet-700 px-3 py-2 text-xs font-semibold text-white transition-colors hover:bg-violet-600 disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    <Send className="h-3.5 w-3.5" />

                    Send Selected to Cyber²
                  </button>

                </div>
              }
            >

              <PromotionTable
                docs={
                  filteredSpreadsheetHits
                }
                selectable
                selectedIds={
                  selectedSpreadsheetIds
                }
                onToggleSelect={
                  toggleSpreadsheetDoc
                }
                expandedRows={
                  expandedRows
                }
                onToggleExpanded={
                  toggleExpandedRow
                }
                emptyMessage="No responsive Spreadsheet / CSV Hits."
              />

            </PromotionSection>


            {/* Review Hits */}

            <PromotionSection
              folderKey="review_hits"
              title="Document Review Hits"
              description="Responsive non-spreadsheet documents prepared for promotion to INSYT Review."
              count={
                reviewHitCount
              }
              icon={
                <FileCheck2 className="h-5 w-5 text-sky-300" />
              }
              open={
                openFolders
                  .review_hits
              }
              onToggle={() =>
                toggleFolder(
                  "review_hits"
                )
              }
              headerActions={
                <div className="flex flex-wrap items-center gap-2">

                  <button
                    type="button"
                    onClick={
                      selectAllReviewHits
                    }
                    disabled={
                      filteredReviewHits.length ===
                      0
                    }
                    className="rounded-lg border border-sky-700 bg-sky-950/30 px-3 py-2 text-xs font-medium text-sky-200 hover:bg-sky-900/50 disabled:opacity-40"
                  >
                    Select All
                  </button>

                  <button
                    type="button"
                    onClick={
                      clearReviewSelection
                    }
                    disabled={
                      selectedReviewIds.size ===
                      0
                    }
                    className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-xs font-medium text-slate-300 hover:bg-slate-800 disabled:opacity-40"
                  >
                    Clear
                  </button>

                  <button
                    type="button"
                    onClick={
                      promoteSelectedToReview
                    }
                    disabled={
                      promotingReview ||
                      selectedReviewIds.size ===
                        0
                    }
                    className="inline-flex items-center gap-2 rounded-lg border border-sky-500 bg-sky-700 px-3 py-2 text-xs font-semibold text-white transition-colors hover:bg-sky-600 disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    <FileCheck2 className="h-3.5 w-3.5" />

                    {promotingReview
                      ? "Promoting..."
                      : "Promote Selected to Review"}
                  </button>

                </div>
              }
            >

              <PromotionTable
                docs={
                  filteredReviewHits
                }
                selectable
                selectedIds={
                  selectedReviewIds
                }
                onToggleSelect={
                  toggleReviewDoc
                }
                expandedRows={
                  expandedRows
                }
                onToggleExpanded={
                  toggleExpandedRow
                }
                emptyMessage="No ordinary responsive documents are awaiting Review promotion."
              />

            </PromotionSection>


            {/* No Hits */}

            <PromotionSection
              folderKey="no_hits"
              title="No Hits"
              description="Detection completed without a responsive result. These documents remain retained for defensibility and are excluded from the responsive review population."
              count={
                noHitCount
              }
              icon={
                <FolderArchive className="h-5 w-5 text-slate-300" />
              }
              open={
                openFolders.no_hits
              }
              onToggle={() =>
                toggleFolder(
                  "no_hits"
                )
              }
            >

              <PromotionTable
                docs={
                  filteredNoHits
                }
                selectable={false}
                selectedIds={
                  new Set()
                }
                expandedRows={
                  expandedRows
                }
                onToggleExpanded={
                  toggleExpandedRow
                }
                emptyMessage="No No-Hit documents."
              />

            </PromotionSection>


            {/* NFR */}

            <PromotionSection
              folderKey="nfr"
              title="NFR"
              description="Documents classified Not For Review under the current workflow or protocol."
              count={
                nfrCount
              }
              icon={
                <Archive className="h-5 w-5 text-amber-300" />
              }
              open={
                openFolders.nfr
              }
              onToggle={() =>
                toggleFolder(
                  "nfr"
                )
              }
            >

              <PromotionTable
                docs={
                  filteredNfr
                }
                selectable={false}
                selectedIds={
                  new Set()
                }
                expandedRows={
                  expandedRows
                }
                onToggleExpanded={
                  toggleExpandedRow
                }
                emptyMessage="No NFR documents."
              />

            </PromotionSection>


            {/* Exceptions */}

            <PromotionSection
              folderKey="exceptions"
              title="Exceptions"
              description="Documents that could not be classified or require remediation before Promotion."
              count={
                exceptionCount
              }
              icon={
                <CircleAlert className="h-5 w-5 text-red-300" />
              }
              open={
                openFolders
                  .exceptions
              }
              onToggle={() =>
                toggleFolder(
                  "exceptions"
                )
              }
            >

              <PromotionTable
                docs={
                  filteredExceptions
                }
                selectable={false}
                selectedIds={
                  new Set()
                }
                expandedRows={
                  expandedRows
                }
                onToggleExpanded={
                  toggleExpandedRow
                }
                emptyMessage="No Promotion exceptions."
              />

            </PromotionSection>

          </div>
        )}


        {/* Audit / Footer Information */}

        <section className="mt-6 rounded-2xl border border-slate-800 bg-slate-900/40">

          <div className="border-b border-slate-800 px-5 py-4">

            <h2 className="text-sm font-semibold text-white">
              Promotion Audit Context
            </h2>

            <p className="mt-1 text-xs leading-5 text-slate-500">
              Promotion operates from the latest completed
              Detection result. Source lineage remains preserved
              through Doc ID, File ID, source APC job, Detection
              job, workbook parent, worksheet index, and staged
              blob paths.
            </p>

          </div>


          <div className="grid gap-4 p-5 md:grid-cols-2 xl:grid-cols-4">

            <AuditValue
              label="Workspace"
              value={
                workspace
              }
            />

            <AuditValue
              label="Client"
              value={
                clientId || "—"
              }
            />

            <AuditValue
              label="Project"
              value={
                projectId || "—"
              }
            />

            <AuditValue
              label="Source APC Job"
              value={
                promotionData
                  ?.source_job_id ||
                "—"
              }
            />

            <AuditValue
              label="Detection Job"
              value={
                promotionData
                  ?.detection_job_id ||
                "—"
              }
            />

            <AuditValue
              label="Detection Summary"
              value={
                promotionData
                  ?.detection_result_paths
                  ?.summary ||
                "—"
              }
            />

            <AuditValue
              label="Detection Documents"
              value={
                promotionData
                  ?.detection_result_paths
                  ?.documents ||
                "—"
              }
            />

            <AuditValue
              label="Detection Entities"
              value={
                promotionData
                  ?.detection_result_paths
                  ?.entities ||
                "—"
              }
            />

          </div>

        </section>


        <div className="mt-5 text-xs text-slate-600">
          Client:{" "}
          {clientId || "—"}
          {" "}•{" "}
          Project:{" "}
          {projectId || "—"}
        </div>

      </div>
    </div>
  );
}


function PromotionSection({
  folderKey,
  title,
  description,
  count,
  icon,
  open,
  onToggle,
  headerActions,
  children,
}: {
  folderKey: PromotionFolder;
  title: string;
  description: string;
  count: number;
  icon: React.ReactNode;
  open: boolean;
  onToggle: () => void;
  headerActions?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section
      data-folder={folderKey}
      className="overflow-hidden rounded-2xl border border-slate-800 bg-slate-900/60"
    >

      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-800 px-5 py-4">

        <button
          type="button"
          onClick={onToggle}
          className="flex min-w-0 flex-1 items-start gap-3 text-left"
        >

          <div className="mt-0.5">
            {open ? (
              <ChevronDown className="h-4 w-4 text-slate-500" />
            ) : (
              <ChevronRight className="h-4 w-4 text-slate-500" />
            )}
          </div>


          <div className="mt-0.5">
            {icon}
          </div>


          <div className="min-w-0">

            <div className="flex flex-wrap items-center gap-2">

              <h2 className="text-base font-semibold text-white">
                {title}
              </h2>

              <span className="rounded-full border border-slate-700 bg-slate-950 px-2 py-0.5 text-xs font-semibold text-slate-300">
                {count.toLocaleString()}
              </span>

            </div>

            <p className="mt-1 max-w-5xl text-sm leading-5 text-slate-400">
              {description}
            </p>

          </div>

        </button>


        {headerActions ? (
          <div>
            {headerActions}
          </div>
        ) : null}

      </div>


      {open ? (
        <div>
          {children}
        </div>
      ) : null}

    </section>
  );
}


function PromotionTable({
  docs,
  selectable,
  selectedIds,
  onToggleSelect,
  expandedRows,
  onToggleExpanded,
  emptyMessage,
}: {
  docs: PromotionDoc[];
  selectable: boolean;
  selectedIds: Set<string>;
  onToggleSelect?: (
    docId: string
  ) => void;
  expandedRows: Set<string>;
  onToggleExpanded: (
    docId: string
  ) => void;
  emptyMessage: string;
}) {
  if (docs.length === 0) {
    return (
      <div className="px-5 py-10">

        <div className="rounded-xl border border-dashed border-slate-700 px-5 py-10 text-center text-sm text-slate-500">
          {emptyMessage}
        </div>

      </div>
    );
  }


  return (
    <div className="max-h-[620px] overflow-auto">

      <table className="min-w-[1500px] w-full text-sm">

        <thead className="sticky top-0 z-20 bg-slate-950 text-left text-[11px] uppercase tracking-wide text-slate-500">

          <tr>

            <th className="w-12 px-4 py-3">
              Details
            </th>

            {selectable ? (
              <th className="w-12 px-4 py-3">
                Select
              </th>
            ) : null}

            <th className="px-4 py-3">
              Doc ID
            </th>

            <th className="px-4 py-3">
              Source File / Workbook
            </th>

            <th className="px-4 py-3">
              Worksheet
            </th>

            <th className="px-4 py-3">
              Type
            </th>

            <th className="px-4 py-3">
              Classification
            </th>

            <th className="px-4 py-3">
              Detected Types
            </th>

            <th className="px-4 py-3">
              Destination
            </th>

            <th className="px-4 py-3">
              Status
            </th>

          </tr>

        </thead>


        <tbody className="divide-y divide-slate-800">

          {docs.map((doc) => {
            const expanded =
              expandedRows.has(
                doc.doc_id
              );

            const sourceName =
              doc.original_workbook_name ||
              doc.original_filename ||
              "—";

            const worksheetLabel =
              doc.is_workbook_sheet
                ? [
                    doc.sheet_index
                      ? `Sheet ${doc.sheet_index}`
                      : "",
                    doc.sheet_name || "",
                  ]
                    .filter(Boolean)
                    .join(" - ")
                : "—";

            return (
              <Fragment key={doc.doc_id}>
                <tr
                  className="bg-slate-950/20 hover:bg-slate-900/70"
                >

                  <td className="px-4 py-3">

                    <button
                      type="button"
                      onClick={() =>
                        onToggleExpanded(
                          doc.doc_id
                        )
                      }
                      className="rounded-md p-1 text-slate-500 hover:bg-slate-800 hover:text-white"
                      title={
                        expanded
                          ? "Hide details"
                          : "Show details"
                      }
                    >
                      {expanded ? (
                        <ChevronDown className="h-4 w-4" />
                      ) : (
                        <ChevronRight className="h-4 w-4" />
                      )}
                    </button>

                  </td>


                  {selectable ? (
                    <td className="px-4 py-3">

                      <input
                        type="checkbox"
                        checked={
                          selectedIds.has(
                            doc.doc_id
                          )
                        }
                        onChange={() =>
                          onToggleSelect?.(
                            doc.doc_id
                          )
                        }
                        className="h-4 w-4 rounded border-slate-600 bg-slate-900"
                      />

                    </td>
                  ) : null}


                  <td className="whitespace-nowrap px-4 py-3 font-mono text-xs text-sky-300">
                    {doc.doc_id}
                  </td>


                  <td
                    className="max-w-[360px] px-4 py-3 text-slate-200"
                    title={sourceName}
                  >

                    <div className="truncate">
                      {sourceName}
                    </div>

                    {doc.is_workbook_sheet &&
                    doc.original_filename &&
                    doc.original_filename !==
                      doc.original_workbook_name ? (
                      <div
                        className="mt-1 truncate text-[11px] text-slate-600"
                        title={
                          doc.original_filename
                        }
                      >
                        Child:{" "}
                        {doc.original_filename}
                      </div>
                    ) : null}

                  </td>


                  <td className="whitespace-nowrap px-4 py-3 text-slate-300">

                    {worksheetLabel}

                    {doc.is_workbook_sheet &&
                    doc.sheet_visibility ? (
                      <div className="mt-1">
                        <VisibilityBadge
                          visibility={
                            doc.sheet_visibility
                          }
                        />
                      </div>
                    ) : null}

                  </td>


                  <td className="px-4 py-3">

                    <TypeBadge
                      doc={doc}
                    />

                  </td>


                  <td className="px-4 py-3">

                    <ClassificationBadge
                      classification={
                        doc.classification ||
                        ""
                      }
                    />

                  </td>


                  <td className="max-w-[420px] px-4 py-3">

                    <EntityTypeList
                      entityTypes={
                        doc.entity_types ||
                        []
                      }
                    />

                  </td>


                  <td className="px-4 py-3">

                    <DestinationBadge
                      destination={
                        doc.destination ||
                        ""
                      }
                    />

                  </td>


                  <td className="px-4 py-3">

                    <PromotionStatusBadge
                      status={
                        doc.promotion_status ||
                        ""
                      }
                      ready={
                        Boolean(
                          doc.ready_for_promotion
                        )
                      }
                    />

                  </td>

                </tr>


                {expanded ? (
                  <tr
                    key={`${doc.doc_id}-details`}
                    className="bg-slate-950/60"
                  >

                    <td
                      colSpan={
                        selectable
                          ? 10
                          : 9
                      }
                      className="px-6 py-5"
                    >

                      <DocumentDetails
                        doc={doc}
                      />

                    </td>

                  </tr>
                ) : null}
              </Fragment>
            );
          })}

        </tbody>

      </table>

    </div>
  );
}


function DocumentDetails({
  doc,
}: {
  doc: PromotionDoc;
}) {
  return (
    <div className="grid gap-5 xl:grid-cols-3">

      <DetailGroup
        title="Document Identity"
        rows={[
          [
            "Doc ID",
            doc.doc_id,
          ],
          [
            "File ID",
            doc.file_id || "—",
          ],
          [
            "Source Type",
            doc.source_type || "—",
          ],
          [
            "Extension",
            doc.extension || "—",
          ],
          [
            "Classification",
            doc.classification || "—",
          ],
          [
            "Destination",
            doc.destination || "—",
          ],
        ]}
      />


      <DetailGroup
        title="Workbook / Worksheet Lineage"
        rows={[
          [
            "Original Workbook",
            doc.original_workbook_name ||
              "—",
          ],
          [
            "Workbook File ID",
            doc.original_workbook_file_id ||
              "—",
          ],
          [
            "Sheet Name",
            doc.sheet_name || "—",
          ],
          [
            "Sheet Index",
            doc.sheet_index != null
              ? String(
                  doc.sheet_index
                )
              : "—",
          ],
          [
            "Sheet Visibility",
            doc.sheet_visibility ||
              "—",
          ],
          [
            "Worksheet Child",
            doc.is_workbook_sheet
              ? "Yes"
              : "No",
          ],
        ]}
      />


      <DetailGroup
        title="Detection / Profile"
        rows={[
          [
            "Detection Mode",
            doc.detection_mode ||
              "—",
          ],
          [
            "Profiled Types",
            String(
              doc.profiled_entity_count ||
                0
            ),
          ],
          [
            "Type Profile Complete",
            booleanDisplay(
              doc.type_profile_complete
            ),
          ],
          [
            "Entity Counts Complete",
            booleanDisplay(
              doc.entity_counts_complete
            ),
          ],
          [
            "Source APC Job",
            doc.source_job_id ||
              "—",
          ],
          [
            "Detection Job",
            doc.detection_job_id ||
              "—",
          ],
        ]}
      />


      <div className="xl:col-span-3">

        <div className="rounded-xl border border-slate-800 bg-slate-900/40">

          <div className="border-b border-slate-800 px-4 py-3 text-xs font-semibold uppercase tracking-[0.12em] text-slate-400">
            Storage / Lineage Paths
          </div>

          <div className="grid gap-4 p-4 lg:grid-cols-2">

            <PathValue
              label="Staged Native"
              value={
                doc.native_staged_blob_path ||
                "—"
              }
            />

            <PathValue
              label="Staged Text"
              value={
                doc.text_staged_blob_path ||
                "—"
              }
            />

            <PathValue
              label="Final Native Destination"
              value={
                doc.final_native_blob_path ||
                "—"
              }
            />

            <PathValue
              label="Final Text Destination"
              value={
                doc.final_text_blob_path ||
                "—"
              }
            />

          </div>

        </div>

      </div>

    </div>
  );
}


function MetricCard({
  label,
  value,
  detail,
}: {
  label: string;
  value: string;
  detail?: string;
}) {
  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-4">

      <div className="text-xs uppercase tracking-[0.14em] text-slate-500">
        {label}
      </div>

      <div className="mt-2 text-2xl font-semibold text-white">
        {value}
      </div>

      {detail ? (
        <div className="mt-1 text-[11px] text-slate-600">
          {detail}
        </div>
      ) : null}

    </div>
  );
}


function RoutingCard({
  icon,
  title,
  destination,
  description,
}: {
  icon: React.ReactNode;
  title: string;
  destination: string;
  description: string;
}) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-950/50 p-4">

      <div className="flex items-center gap-2">

        {icon}

        <h3 className="text-sm font-semibold text-slate-100">
          {title}
        </h3>

      </div>

      <div className="mt-3">

        <span className="rounded-full border border-slate-700 bg-slate-900 px-2.5 py-1 text-xs font-semibold text-slate-300">
          → {destination}
        </span>

      </div>

      <p className="mt-3 text-xs leading-5 text-slate-500">
        {description}
      </p>

    </div>
  );
}


function TypeBadge({
  doc,
}: {
  doc: PromotionDoc;
}) {
  if (doc.is_workbook_sheet) {
    return (
      <span className="inline-flex items-center gap-1 rounded-full border border-violet-800 bg-violet-950/40 px-2.5 py-1 text-xs font-medium text-violet-200">

        <FileSpreadsheet className="h-3.5 w-3.5" />

        Worksheet CSV

      </span>
    );
  }

  if (
    String(
      doc.extension || ""
    ).toLowerCase() ===
    "csv"
  ) {
    return (
      <span className="inline-flex items-center gap-1 rounded-full border border-violet-800 bg-violet-950/40 px-2.5 py-1 text-xs font-medium text-violet-200">

        <Database className="h-3.5 w-3.5" />

        CSV

      </span>
    );
  }

  return (
    <span className="inline-flex items-center gap-1 rounded-full border border-slate-700 bg-slate-900 px-2.5 py-1 text-xs font-medium text-slate-300">

      <FileText className="h-3.5 w-3.5" />

      {String(
        doc.extension ||
          "document"
      ).toUpperCase()}

    </span>
  );
}


function ClassificationBadge({
  classification,
}: {
  classification: string;
}) {
  const normalized =
    String(
      classification || ""
    ).toUpperCase();

  if (normalized === "HIT") {
    return (
      <span className="inline-flex items-center gap-1 rounded-full border border-emerald-800 bg-emerald-950/40 px-2.5 py-1 text-xs font-semibold text-emerald-300">

        <CheckCircle2 className="h-3.5 w-3.5" />

        HIT

      </span>
    );
  }

  if (
    normalized === "NO_HIT"
  ) {
    return (
      <span className="inline-flex items-center gap-1 rounded-full border border-slate-700 bg-slate-900 px-2.5 py-1 text-xs font-semibold text-slate-300">

        NO HIT

      </span>
    );
  }

  if (
    normalized === "NFR"
  ) {
    return (
      <span className="rounded-full border border-amber-800 bg-amber-950/40 px-2.5 py-1 text-xs font-semibold text-amber-300">
        NFR
      </span>
    );
  }

  return (
    <span className="rounded-full border border-red-900 bg-red-950/40 px-2.5 py-1 text-xs font-semibold text-red-300">
      {normalized || "UNKNOWN"}
    </span>
  );
}


function DestinationBadge({
  destination,
}: {
  destination: string;
}) {
  const normalized =
    String(
      destination || ""
    ).toLowerCase();

  if (normalized === "cyber2") {
    return (
      <span className="rounded-full border border-violet-700 bg-violet-950/40 px-2.5 py-1 text-xs font-semibold text-violet-200">
        Cyber²
      </span>
    );
  }

  if (normalized === "review") {
    return (
      <span className="rounded-full border border-sky-700 bg-sky-950/40 px-2.5 py-1 text-xs font-semibold text-sky-200">
        Review
      </span>
    );
  }

  if (
    normalized === "no_hits"
  ) {
    return (
      <span className="rounded-full border border-slate-700 bg-slate-900 px-2.5 py-1 text-xs font-semibold text-slate-300">
        Retained
      </span>
    );
  }

  if (normalized === "nfr") {
    return (
      <span className="rounded-full border border-amber-800 bg-amber-950/40 px-2.5 py-1 text-xs font-semibold text-amber-300">
        NFR
      </span>
    );
  }

  return (
    <span className="rounded-full border border-red-900 bg-red-950/40 px-2.5 py-1 text-xs font-semibold text-red-300">
      Exception
    </span>
  );
}


function PromotionStatusBadge({
  status,
  ready,
}: {
  status: string;
  ready: boolean;
}) {
  const normalized =
    String(
      status || ""
    ).trim().toLowerCase();

  if (
    normalized === "promoted"
  ) {
    return (
      <span className="inline-flex items-center gap-1 text-xs font-medium text-emerald-300">

        <CheckCircle2 className="h-3.5 w-3.5" />

        Promoted

      </span>
    );
  }

  if (ready) {
    return (
      <span className="text-xs font-medium text-sky-300">
        Ready
      </span>
    );
  }

  return (
    <span className="text-xs text-slate-500">
      Retained
    </span>
  );
}


function VisibilityBadge({
  visibility,
}: {
  visibility: string;
}) {
  const normalized =
    String(
      visibility || ""
    ).toLowerCase();

  if (
    normalized === "hidden" ||
    normalized === "veryhidden" ||
    normalized === "very_hidden"
  ) {
    return (
      <span className="rounded-full border border-amber-800/70 bg-amber-950/30 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-amber-300">
        {normalized ===
        "veryhidden"
          ? "Very Hidden"
          : normalized ===
              "very_hidden"
            ? "Very Hidden"
            : "Hidden"}
      </span>
    );
  }

  return (
    <span className="rounded-full border border-slate-700 bg-slate-900 px-2 py-0.5 text-[10px] uppercase tracking-wide text-slate-500">
      {visibility || "Visible"}
    </span>
  );
}


function EntityTypeList({
  entityTypes,
}: {
  entityTypes: string[];
}) {
  if (
    !entityTypes ||
    entityTypes.length === 0
  ) {
    return (
      <span className="text-xs text-slate-600">
        —
      </span>
    );
  }

  return (
    <div className="flex flex-wrap gap-1.5">

      {entityTypes.map(
        (entityType) => (
          <span
            key={entityType}
            className="rounded-md border border-slate-700 bg-slate-900 px-2 py-1 text-[11px] text-slate-300"
          >
            {entityType}
          </span>
        )
      )}

    </div>
  );
}


function DetailGroup({
  title,
  rows,
}: {
  title: string;
  rows: Array<
    [string, string]
  >;
}) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/40">

      <div className="border-b border-slate-800 px-4 py-3 text-xs font-semibold uppercase tracking-[0.12em] text-slate-400">
        {title}
      </div>

      <div className="divide-y divide-slate-800/70">

        {rows.map(
          ([label, value]) => (
            <div
              key={label}
              className="grid grid-cols-[150px_1fr] gap-3 px-4 py-2.5"
            >

              <div className="text-xs text-slate-500">
                {label}
              </div>

              <div className="break-all text-xs text-slate-300">
                {value}
              </div>

            </div>
          )
        )}

      </div>

    </div>
  );
}


function PathValue({
  label,
  value,
}: {
  label: string;
  value: string;
}) {
  return (
    <div>

      <div className="text-[11px] uppercase tracking-[0.12em] text-slate-600">
        {label}
      </div>

      <div className="mt-1 break-all font-mono text-xs leading-5 text-slate-400">
        {value}
      </div>

    </div>
  );
}


function AuditValue({
  label,
  value,
}: {
  label: string;
  value: string;
}) {
  return (
    <div>

      <div className="text-[11px] uppercase tracking-[0.12em] text-slate-600">
        {label}
      </div>

      <div className="mt-1 break-all text-xs leading-5 text-slate-300">
        {value}
      </div>

    </div>
  );
}


function booleanDisplay(
  value:
    | boolean
    | null
    | undefined
) {
  if (value === true) {
    return "Yes";
  }

  if (value === false) {
    return "No";
  }

  return "—";
}


export default function ProcessingCenterPromotionPage() {
  return (
    <AppShell>

      <Suspense
        fallback={
          <div className="min-h-full bg-slate-950 text-slate-100">

            <div className="mx-auto max-w-[1900px] px-6 py-6">

              <div className="rounded-2xl border border-slate-800 bg-slate-900/60 px-5 py-12 text-center text-sm text-slate-500">
                Loading Processing Center - Promotion...
              </div>

            </div>

          </div>
        }
      >

        <ProcessingCenterPromotionPageContent />

      </Suspense>

    </AppShell>
  );
}