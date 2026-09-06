"use client";

import {
  Suspense,
  useEffect,
  useMemo,
  useState,
} from "react";

import {
  useRouter,
  useSearchParams,
} from "next/navigation";

import AppShell from "../../../../components/AppShell";
import PageContainer from "../../../../components/PageContainer";
import PageHeader from "../../../../components/PageHeader";
import CyberUtilityWorkflowNav from "../../../../components/CyberUtilityWorkflowNav";

import {
  apiGet,
  apiPost,
} from "../../../../lib/api";


type HeaderColumn = {
  
  ai_review_required?: boolean;
  ai_invoked?: boolean;
  ai_status?: string;
  ai_recommendation?: string;
  ai_confidence?: number | null;

  column_index: number;
  column_number?: number;

  source_header?: string;

  recommended_protocol_header?: string;

  mapping_confidence?: number;

  matched?: boolean;

  match_method?: string;

  semantic_type?: string;

  semantic_confidence?: number;

  sample_count?: number;

  sample_values?: string[];

  default_disposition?: string;
};


type IdentificationDocument = {
  doc_id: string;

  source_csv_path?: string;

  classification?: string;

  entity_types?: string[];

  original_filename?: string;

  original_workbook_name?: string;

  sheet_name?: string;

  sheet_index?: number | null;

  sheet_visibility?: string;

  identification_status?: string;

  identification_error?: string;

  delimiter?: string;

  sample_row_count?: number;

  header_status?: string;

  header_confidence?: number;

  matched_column_count?: number;

  unmatched_column_count?: number;

  column_count?: number;

  columns?: HeaderColumn[];
};


type IdentificationResult = {
  status?: string;

  analysis_engine?: string;

  analysis_mode?: string;

  ai_status?: string;

  identified_at?: string;

  protocol_header_source?: string;

  protocol_headers?: string[];

  document_count?: number;

  completed_document_count?: number;

  error_document_count?: number;

  header_presence_counts?: {
    headers_in_row_1?: number;
    no_headers_in_row_1?: number;
    needs_review?: number;
  };

  documents?: IdentificationDocument[];
};


type HeaderSetManifest = {
  header_set_id?: string;

  status?: string;

  created_at?: string;

  created_by?: string;

  document_count?: number;

  documents?: any[];

  header_identification_path?: string;

  approved_mapping_path?: string;
};


type HeaderSetResponse = {
  workspace?: string;

  client?: string;

  project?: string;

  header_set_id?: string;

  manifest?: HeaderSetManifest;

  identification?: IdentificationResult | null;

  identification_exists?: boolean;

  identification_path?: string;
};


type MappingResponse = {
  workspace?: string;

  client?: string;

  project?: string;

  header_set_id?: string;

  protocol_headers?: string[];

  protocol_header_source?: string;

  identification?: IdentificationResult;

  approved_mapping?: any;

  approved_mapping_exists?: boolean;

  approved_mapping_path?: string;
};


type ColumnDecision = {
  disposition:
    | "approve"
    | "map"
    | "keep"
    | "rename"
    | "delete";

  final_header: string;
};


type DecisionState = Record<
  string,
  ColumnDecision
>;


function decisionKey(
  docId: string,
  columnIndex: number
) {
  return `${docId}::${columnIndex}`;
}


function formatPercent(
  value?: number | null
) {
  if (
    value === null ||
    value === undefined
  ) {
    return "—";
  }

  return `${Math.round(
    Number(value) * 100
  )}%`;
}


function formatStatus(
  value?: string
) {
  const clean =
    String(
      value || ""
    )
      .replaceAll(
        "_",
        " "
      )
      .trim();

  if (!clean) {
    return "Pending";
  }

  return clean.replace(
    /\b\w/g,
    (character) =>
      character.toUpperCase()
  );
}


function SchemaMappingSetContent() {
  const router =
    useRouter();

  const searchParams =
    useSearchParams();

  const workspace =
    searchParams.get(
      "workspace"
    ) || "capture";

  const client =
    searchParams.get(
      "client"
    ) || "";

  const project =
    searchParams.get(
      "project"
    ) || "";

  const headerSetId =
    searchParams.get(
      "header_set"
    ) || "";


  const [
    headerSetData,
    setHeaderSetData,
  ] =
    useState<HeaderSetResponse | null>(
      null
    );


  const [
    mappingData,
    setMappingData,
  ] =
    useState<MappingResponse | null>(
      null
    );


  const [
    decisions,
    setDecisions,
  ] =
    useState<DecisionState>({});


  const [
    selectedUnmatched,
    setSelectedUnmatched,
  ] =
    useState<Record<string, boolean>>(
      {}
    );


  const [
    loading,
    setLoading,
  ] =
    useState(false);


  const [
    identifying,
    setIdentifying,
  ] =
    useState(false);


  const [
    approving,
    setApproving,
  ] =
    useState(false);


  const [
    error,
    setError,
  ] =
    useState("");


  const [
    message,
    setMessage,
  ] =
    useState("");


  const [
    activeDocId,
    setActiveDocId,
  ] =
    useState<string | null>(
      null
    );


  function buildProjectParams() {
    const params =
      new URLSearchParams();

    params.set(
      "workspace",
      workspace
    );

    if (client) {
      params.set(
        "client",
        client
      );
    }

    if (project) {
      params.set(
        "project",
        project
      );
    }

    return params;
  }


  function returnToHeaderSets() {
    const params =
      buildProjectParams();

    router.push(
      `/cyber-utility/schema-mapping?${params.toString()}`
    );
  }


  function returnToCyber2() {
    const params =
      buildProjectParams();

    router.push(
      `/cyber-utility?${params.toString()}`
    );
  }


  async function loadHeaderSet() {
    if (
      !client ||
      !project ||
      !headerSetId
    ) {
      return;
    }

    setLoading(true);
    setError("");

    try {
      const params =
        new URLSearchParams({
          client,
          project,
        });

      const response =
        await apiGet(
          `/api/${encodeURIComponent(
            workspace
          )}/cyber2/header-sets/${encodeURIComponent(
            headerSetId
          )}?${params.toString()}`
        );

      setHeaderSetData(
        response
      );

      if (
        response?.identification_exists
      ) {
        await loadMapping();
      }

    } catch (err: any) {
      console.error(
        "Unable to load Header Set:",
        err
      );

      setError(
        err?.message ||
          "Unable to load Header Set."
      );

    } finally {
      setLoading(false);
    }
  }


  async function loadMapping() {
    if (
      !client ||
      !project ||
      !headerSetId
    ) {
      return;
    }

    const params =
      new URLSearchParams({
        client,
        project,
      });

    const response =
      await apiGet(
        `/api/${encodeURIComponent(
          workspace
        )}/cyber2/header-sets/${encodeURIComponent(
          headerSetId
        )}/mapping?${params.toString()}`
      );

    setMappingData(
      response
    );

    initializeDecisions(
      response
    );
  }


  function initializeDecisions(
    response: MappingResponse
  ) {
    const identification =
      response?.identification;

    const documents =
      identification?.documents ||
      [];

    const next: DecisionState =
      {};

    for (
      const document
      of documents
    ) {
      const docId =
        String(
          document.doc_id ||
          ""
        ).trim();

      if (!docId) {
        continue;
      }

      for (
        const column
        of document.columns ||
        []
      ) {
        const key =
          decisionKey(
            docId,
            column.column_index
          );

        const recommended =
          String(
            column
              .recommended_protocol_header ||
            ""
          ).trim();

        if (
          column.matched &&
          recommended
        ) {
          next[key] = {
            disposition:
              "approve",

            final_header:
              recommended,
          };

        } else {
          next[key] = {
            disposition:
              "keep",

            final_header:
              String(
                column.source_header ||
                `Column ${
                  column.column_index +
                  1
                }`
              ),
          };
        }
      }
    }

    setDecisions(
      next
    );
  }


  async function runIdentification() {
    if (
      !client ||
      !project ||
      !headerSetId
    ) {
      return;
    }

    setIdentifying(true);
    setError("");
    setMessage("");

    try {
      const params =
        new URLSearchParams({
          client,
          project,
        });

      const result =
        await apiPost(
          `/api/${encodeURIComponent(
            workspace
          )}/cyber2/header-sets/${encodeURIComponent(
            headerSetId
          )}/identify?${params.toString()}`,
          {}
        );

      setMessage(
        result?.message ||
        "Header Identification completed."
      );

      await loadHeaderSet();

    } catch (err: any) {
      console.error(
        "Header Identification failed:",
        err
      );

      setError(
        err?.message ||
          "Header Identification failed."
      );

    } finally {
      setIdentifying(false);
    }
  }


  useEffect(() => {
    loadHeaderSet();
  }, [
    workspace,
    client,
    project,
    headerSetId,
  ]);


  const identification =
    mappingData?.identification ||
    headerSetData?.identification ||
    null;


  const documents =
    identification?.documents ||
    [];


  const protocolHeaders =
    mappingData?.protocol_headers ||
    identification?.protocol_headers ||
    [];


  const completedDocuments =
    useMemo(
      () =>
        documents.filter(
          (document) =>
            document
              .identification_status
            === "COMPLETED"
        ),
      [
        documents,
      ]
    );


  const activeDocument =
    useMemo(
      () =>
        completedDocuments.find(
          (document) =>
            document.doc_id ===
            activeDocId
        ) ||
        null,
      [
        completedDocuments,
        activeDocId,
      ]
    );


  const unmatchedKeys =
    useMemo(
      () => {
        const keys: string[] =
          [];

        for (
          const document
          of completedDocuments
        ) {
          for (
            const column
            of document.columns ||
            []
          ) {
            if (
              column.matched
            ) {
              continue;
            }

            keys.push(
              decisionKey(
                document.doc_id,
                column.column_index
              )
            );
          }
        }

        return keys;
      },
      [
        completedDocuments,
      ]
    );


  const selectedUnmatchedCount =
    unmatchedKeys.filter(
      (key) =>
        Boolean(
          selectedUnmatched[key]
        )
    ).length;


  function updateDecision(
    docId: string,
    columnIndex: number,
    patch: Partial<ColumnDecision>
  ) {
    const key =
      decisionKey(
        docId,
        columnIndex
      );

    setDecisions(
      (current) => ({
        ...current,

        [key]: {
          disposition:
            current[key]
              ?.disposition ||
            "keep",

          final_header:
            current[key]
              ?.final_header ||
            "",

          ...patch,
        },
      })
    );
  }


  function changeDisposition(
    docId: string,
    column: HeaderColumn,
    disposition:
      ColumnDecision["disposition"]
  ) {
    let finalHeader =
      decisions[
        decisionKey(
          docId,
          column.column_index
        )
      ]?.final_header ||
      "";

    if (
      disposition ===
      "approve"
    ) {
      finalHeader =
        String(
          column
            .recommended_protocol_header ||
          ""
        );
    }

    if (
      disposition ===
      "keep"
    ) {
      finalHeader =
        String(
          column.source_header ||
          `Column ${
            column.column_index +
            1
          }`
        );
    }

    if (
      disposition ===
      "delete"
    ) {
      finalHeader = "";
    }

    if (
      disposition ===
      "map"
    ) {
      const currentIsProtocol =
        protocolHeaders.includes(
          finalHeader
        );

      if (
        !currentIsProtocol
      ) {
        finalHeader =
          protocolHeaders[0] ||
          "";
      }
    }

    if (
      disposition ===
      "rename" &&
      !finalHeader
    ) {
      finalHeader =
        String(
          column.source_header ||
          ""
        );
    }

    updateDecision(
      docId,
      column.column_index,
      {
        disposition,
        final_header:
          finalHeader,
      }
    );
  }


  function toggleUnmatched(
    docId: string,
    columnIndex: number
  ) {
    const key =
      decisionKey(
        docId,
        columnIndex
      );

    setSelectedUnmatched(
      (current) => ({
        ...current,

        [key]:
          !current[key],
      })
    );
  }


  function selectAllUnmatched() {
    const next: Record<
      string,
      boolean
    > = {};

    for (
      const key
      of unmatchedKeys
    ) {
      next[key] = true;
    }

    setSelectedUnmatched(
      next
    );
  }


  function clearUnmatchedSelection() {
    setSelectedUnmatched(
      {}
    );
  }


  function deleteSelectedUnmatched() {
    if (
      selectedUnmatchedCount ===
      0
    ) {
      return;
    }

    setDecisions(
      (current) => {
        const next = {
          ...current,
        };

        for (
          const key
          of unmatchedKeys
        ) {
          if (
            !selectedUnmatched[
              key
            ]
          ) {
            continue;
          }

          next[key] = {
            disposition:
              "delete",

            final_header:
              "",
          };
        }

        return next;
      }
    );

    setSelectedUnmatched(
      {}
    );
  }


  async function approveMapping() {
    if (
      completedDocuments.length ===
      0
    ) {
      setError(
        "No identified documents are available for approval."
      );

      return;
    }

    const documentPayloads =
      completedDocuments.map(
        (document) => ({
          doc_id:
            document.doc_id,

          columns:
            (
              document.columns ||
              []
            ).map(
              (column) => {
                const key =
                  decisionKey(
                    document.doc_id,
                    column.column_index
                  );

                const decision =
                  decisions[key] || {
                    disposition:
                      "keep" as const,

                    final_header:
                      column.source_header ||
                      `Column ${
                        column.column_index +
                        1
                      }`,
                  };

                return {
                  column_index:
                    column.column_index,

                  disposition:
                    decision
                      .disposition,

                  final_header:
                    decision
                      .final_header,
                };
              }
            ),
        })
      );

    setApproving(true);
    setError("");
    setMessage("");

    try {
      const result =
        await apiPost(
          `/api/${encodeURIComponent(
            workspace
          )}/cyber2/header-sets/${encodeURIComponent(
            headerSetId
          )}/mapping/approve`,
          {
            client,
            project,

            documents:
              documentPayloads,

            approved_by: "",
          }
        );

      setMessage(
        result?.message ||
        "Header mapping approved."
      );

      await loadHeaderSet();

    } catch (err: any) {
      console.error(
        "Header Mapping approval failed:",
        err
      );

      setError(
        err?.message ||
          "Header Mapping approval failed."
      );

    } finally {
      setApproving(false);
    }
  }


  if (
    !client ||
    !project ||
    !headerSetId
  ) {
    return (
      <AppShell>
        <PageContainer>
        <CyberUtilityWorkflowNav />

          <PageHeader
            title="Header & Schema Mapping"
            subtitle="A client, project, and Header Set are required."
          />

        </PageContainer>
      </AppShell>
    );
  }


  return (
    <AppShell>

      <PageContainer>

        <div className="mb-4 flex flex-wrap gap-2">

          <button
            type="button"
            onClick={
              returnToHeaderSets
            }
            className="rounded-lg border border-slate-700 bg-slate-900 px-4 py-2 text-sm font-medium text-slate-200 transition hover:bg-slate-800"
          >
            ← Return to Header & Schema Mapping
          </button>


          <button
            type="button"
            onClick={
              returnToCyber2
            }
            className="rounded-lg border border-slate-700 bg-slate-900 px-4 py-2 text-sm font-medium text-slate-200 transition hover:bg-slate-800"
          >
            ← Return to Cyber² Landing
          </button>

        </div>


        <PageHeader
          title="Header Set Review"
          subtitle={
            `Header Set ${headerSetId}`
          }
        />


        {error ? (
          <div className="mt-5 rounded-xl border border-red-900/70 bg-red-950/30 px-4 py-3 text-sm text-red-300">
            {error}
          </div>
        ) : null}


        {message ? (
          <div className="mt-5 rounded-xl border border-emerald-900/70 bg-emerald-950/30 px-4 py-3 text-sm text-emerald-300">
            {message}
          </div>
        ) : null}


        {loading ? (
          <div className="mt-6 rounded-2xl border border-slate-800 bg-slate-900/60 px-6 py-14 text-center text-slate-400">
            Loading Header Set...
          </div>
        ) : (

          <>

            <div className="mt-6 grid gap-4 md:grid-cols-4">

              <MetricCard
                label="Header Set"
                value={
                  headerSetId
                }
              />

              <MetricCard
                label="Files"
                value={String(
                  headerSetData
                    ?.manifest
                    ?.document_count ??
                  documents.length
                )}
              />

              <MetricCard
                label="Status"
                value={
                  formatStatus(
                    headerSetData
                      ?.manifest
                      ?.status
                  )
                }
              />

              <MetricCard
                label="Protocol Fields"
                value={String(
                  protocolHeaders.length
                )}
              />

            </div>


            <div className="mt-6 rounded-xl border border-sky-900/60 bg-sky-950/20 px-5 py-4">

              <div className="text-sm font-semibold text-sky-200">
                INSYT Header Recognition
              </div>

              <p className="mt-1 text-sm leading-6 text-slate-400">
                INSYT evaluates Row 1, representative column values,
                header aliases, and the assigned Project Protocol.
                Source CSV files remain unchanged during identification
                and approval.
              </p>

            </div>


            {!identification ? (

              <div className="mt-6 rounded-2xl border border-slate-800 bg-slate-900/60 p-6">

                <h2 className="text-lg font-semibold text-white">
                  Header Identification Required
                </h2>

                <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-400">
                  Run Header Identification to determine whether each
                  CSV contains headers in Row 1 and generate recommended
                  Project Protocol mappings from header text and column data.
                </p>

                <button
                  type="button"
                  onClick={
                    runIdentification
                  }
                  disabled={
                    identifying
                  }
                  className="mt-5 rounded-lg bg-sky-600 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-sky-500 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {identifying
                    ? "Analyzing Headers..."
                    : "Run Header Identification"}
                </button>

              </div>

            ) : (

              <>

                <div className="mt-6 grid gap-4 md:grid-cols-3">

                  <MetricCard
                    label="Headers in Row 1"
                    value={String(
                      identification
                        ?.header_presence_counts
                        ?.headers_in_row_1 ??
                      0
                    )}
                  />

                  <MetricCard
                    label="No Headers in Row 1"
                    value={String(
                      identification
                        ?.header_presence_counts
                        ?.no_headers_in_row_1 ??
                      0
                    )}
                  />

                  <MetricCard
                    label="Needs Review"
                    value={String(
                      identification
                        ?.header_presence_counts
                        ?.needs_review ??
                      0
                    )}
                  />

                </div>


                <div className="mt-6 flex flex-wrap items-center justify-between gap-3">

                  <div>

                    <h2 className="text-lg font-semibold text-white">
                      Identified CSVs
                    </h2>

                    <p className="mt-1 text-sm text-slate-500">
                      Open a CSV to review and approve INSYT's recommended mappings.
                    </p>

                  </div>


                  <button
                    type="button"
                    onClick={
                      runIdentification
                    }
                    disabled={
                      identifying
                    }
                    className="rounded-lg border border-slate-700 bg-slate-900 px-4 py-2 text-sm text-slate-200 hover:bg-slate-800 disabled:opacity-50"
                  >
                    {identifying
                      ? "Reanalyzing..."
                      : "Re-run Identification"}
                  </button>

                </div>


                <div className="mt-4 overflow-hidden rounded-2xl border border-slate-800 bg-slate-900/60">

                  <div className="max-h-[500px] overflow-auto">

                    <table className="w-full min-w-[1000px] text-sm">

                      <thead className="sticky top-0 bg-slate-950 text-left text-[11px] uppercase tracking-wide text-slate-500">

                        <tr>

                          <th className="px-4 py-3">
                            Doc ID
                          </th>

                          <th className="px-4 py-3">
                            Workbook / Source
                          </th>

                          <th className="px-4 py-3">
                            Worksheet
                          </th>

                          <th className="px-4 py-3">
                            Header Result
                          </th>

                          <th className="px-4 py-3">
                            Confidence
                          </th>

                          <th className="px-4 py-3">
                            Matched
                          </th>

                          <th className="px-4 py-3">
                            Unmatched
                          </th>

                          <th className="px-4 py-3 text-right">
                            Action
                          </th>

                        </tr>

                      </thead>


                      <tbody className="divide-y divide-slate-800">

                        {documents.map(
                          (document) => (

                            <tr
                              key={
                                document.doc_id
                              }
                              className="hover:bg-slate-900/70"
                            >

                              <td className="px-4 py-3 font-mono text-xs text-sky-400">
                                {
                                  document.doc_id
                                }
                              </td>


                              <td className="px-4 py-3 text-slate-300">
                                {
                                  document.original_workbook_name ||
                                  document.original_filename ||
                                  "—"
                                }
                              </td>


                              <td className="px-4 py-3 text-slate-400">
                                {
                                  document.sheet_name ||
                                  "—"
                                }
                              </td>


                              <td className="px-4 py-3">

                                <HeaderStatusBadge
                                  value={
                                    document.header_status
                                  }
                                />

                              </td>


                              <td className="px-4 py-3 text-slate-300">
                                {formatPercent(
                                  document.header_confidence
                                )}
                              </td>


                              <td className="px-4 py-3 text-emerald-300">
                                {
                                  document.matched_column_count ??
                                  0
                                }
                              </td>


                              <td className="px-4 py-3 text-amber-300">
                                {
                                  document.unmatched_column_count ??
                                  0
                                }
                              </td>


                              <td className="px-4 py-3 text-right">

                                {document.identification_status ===
                                "COMPLETED" ? (

                                  <button
                                    type="button"
                                    onClick={() =>
                                      setActiveDocId(
                                        document.doc_id
                                      )
                                    }
                                    className="rounded-lg bg-sky-600 px-4 py-2 text-xs font-semibold text-white hover:bg-sky-500"
                                  >
                                    Review Mapping
                                  </button>

                                ) : (

                                  <span className="text-xs text-red-400">
                                    {
                                      document.identification_error ||
                                      "Identification Error"
                                    }
                                  </span>

                                )}

                              </td>

                            </tr>

                          )
                        )}

                      </tbody>

                    </table>

                  </div>

                </div>


                {unmatchedKeys.length >
                0 ? (

                  <div className="mt-6 rounded-xl border border-amber-900/50 bg-amber-950/10 p-4">

                    <div className="flex flex-wrap items-center justify-between gap-3">

                      <div>

                        <div className="text-sm font-semibold text-amber-200">
                          Unmatched Fields
                        </div>

                        <p className="mt-1 text-xs text-slate-500">
                          Unmatched fields are placed after recommended
                          protocol matches. You can preserve, map, rename,
                          or mark them for deletion.
                        </p>

                      </div>


                      <div className="flex flex-wrap gap-2">

                        <button
                          type="button"
                          onClick={
                            selectAllUnmatched
                          }
                          className="rounded-lg border border-slate-700 px-3 py-2 text-xs text-slate-300 hover:bg-slate-800"
                        >
                          Select All Unmatched
                        </button>


                        <button
                          type="button"
                          onClick={
                            clearUnmatchedSelection
                          }
                          className="rounded-lg border border-slate-700 px-3 py-2 text-xs text-slate-300 hover:bg-slate-800"
                        >
                          Clear Selection
                        </button>


                        <button
                          type="button"
                          onClick={
                            deleteSelectedUnmatched
                          }
                          disabled={
                            selectedUnmatchedCount ===
                            0
                          }
                          className="rounded-lg border border-red-800 bg-red-950/30 px-3 py-2 text-xs font-semibold text-red-300 hover:bg-red-950/50 disabled:opacity-40"
                        >
                          Delete Selected (
                          {
                            selectedUnmatchedCount
                          }
                          )
                        </button>

                      </div>

                    </div>

                  </div>

                ) : null}


                <div className="mt-6 flex justify-end">

                  <button
                    type="button"
                    onClick={
                      approveMapping
                    }
                    disabled={
                      approving ||
                      completedDocuments.length ===
                        0
                    }
                    className="rounded-lg bg-emerald-600 px-6 py-3 text-sm font-semibold text-white transition hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {approving
                      ? "Saving Approval..."
                      : "Approve Header Mapping"}
                  </button>

                </div>

              </>

            )}

          </>

        )}


        {activeDocument ? (

          <MappingModal
            document={
              activeDocument
            }

            protocolHeaders={
              protocolHeaders
            }

            decisions={
              decisions
            }

            selectedUnmatched={
              selectedUnmatched
            }

            onToggleUnmatched={
              toggleUnmatched
            }

            onChangeDisposition={
              changeDisposition
            }

            onUpdateDecision={
              updateDecision
            }

            onClose={() =>
              setActiveDocId(
                null
              )
            }
          />

        ) : null}

      </PageContainer>

    </AppShell>
  );
}


function MappingModal({
  document,
  protocolHeaders,
  decisions,
  selectedUnmatched,
  onToggleUnmatched,
  onChangeDisposition,
  onUpdateDecision,
  onClose,
}: {
  document: IdentificationDocument;

  protocolHeaders: string[];

  decisions: DecisionState;

  selectedUnmatched: Record<
    string,
    boolean
  >;

  onToggleUnmatched: (
    docId: string,
    columnIndex: number
  ) => void;

  onChangeDisposition: (
    docId: string,
    column: HeaderColumn,
    disposition:
      ColumnDecision["disposition"]
  ) => void;

  onUpdateDecision: (
    docId: string,
    columnIndex: number,
    patch: Partial<ColumnDecision>
  ) => void;

  onClose: () => void;
}) {

  const columns =
    document.columns ||
    [];


  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/75 p-4">

      <div className="flex max-h-[92vh] w-full max-w-[1500px] flex-col overflow-hidden rounded-2xl border border-slate-700 bg-slate-950 shadow-2xl">

        <div className="flex items-start justify-between border-b border-slate-800 px-6 py-5">

          <div>

            <div className="text-xs uppercase tracking-[0.16em] text-slate-500">
              Header Mapping Review
            </div>

            <h2 className="mt-1 text-xl font-semibold text-white">
              {
                document.doc_id
              }
            </h2>

            <div className="mt-2 flex flex-wrap gap-3 text-xs text-slate-400">

              <span>
                Header Result:{" "}
                <strong className="text-slate-200">
                  {formatStatus(
                    document.header_status
                  )}
                </strong>
              </span>

              <span>
                Confidence:{" "}
                <strong className="text-slate-200">
                  {formatPercent(
                    document.header_confidence
                  )}
                </strong>
              </span>

              <span>
                Columns:{" "}
                <strong className="text-slate-200">
                  {
                    document.column_count ??
                    columns.length
                  }
                </strong>
              </span>

            </div>

          </div>


          <button
            type="button"
            onClick={
              onClose
            }
            className="rounded-lg border border-slate-700 px-3 py-2 text-sm text-slate-300 hover:bg-slate-800"
          >
            Close
          </button>

        </div>


        <div className="overflow-auto">

          <table className="w-full min-w-[1350px] text-sm">

            <thead className="sticky top-0 z-10 bg-slate-950 text-left text-[11px] uppercase tracking-wide text-slate-500">

              <tr>

                <th className="w-12 px-4 py-3">
                  Select
                </th>

                <th className="px-4 py-3">
                  Source Column
                </th>

                <th className="px-4 py-3">
                  Sample Data
                </th>

                <th className="px-4 py-3">
                  INSYT Recommendation
                </th>

                <th className="px-4 py-3">
                  Confidence
                </th>

                <th className="px-4 py-3">
                  Evidence
                </th>

                <th className="px-4 py-3">
                  Action
                </th>

                <th className="px-4 py-3">
                  Final Header
                </th>

              </tr>

            </thead>


            <tbody className="divide-y divide-slate-800">

              {columns.map(
                (column) => {

                  const key =
                    decisionKey(
                      document.doc_id,
                      column.column_index
                    );

                  const decision =
                    decisions[key] || {
                      disposition:
                        column.matched
                          ? "approve"
                          : "keep",

                      final_header:
                        column
                          .recommended_protocol_header ||
                        column.source_header ||
                        `Column ${
                          column.column_index +
                          1
                        }`,
                    };

                  const isUnmatched =
                    !column.matched;

                  const needsProtocolDropdown =
                    decision.disposition ===
                      "approve" ||
                    decision.disposition ===
                      "map";

                  const needsRename =
                    decision.disposition ===
                    "rename";

                  return (
                    <tr
                      key={
                        key
                      }
                      className={
                        isUnmatched
                          ? "bg-amber-950/10"
                          : "bg-slate-950/20"
                      }
                    >

                      <td className="px-4 py-4">

                        {isUnmatched ? (

                          <input
                            type="checkbox"
                            checked={
                              Boolean(
                                selectedUnmatched[
                                  key
                                ]
                              )
                            }
                            onChange={() =>
                              onToggleUnmatched(
                                document.doc_id,
                                column.column_index
                              )
                            }
                            className="h-4 w-4"
                          />

                        ) : (
                          <span className="text-slate-700">
                            —
                          </span>
                        )}

                      </td>


                      <td className="px-4 py-4">

                        <div className="font-semibold text-slate-200">
                          {
                            column.source_header ||
                            `Column ${
                              column.column_index +
                              1
                            }`
                          }
                        </div>

                        <div className="mt-1 text-[11px] text-slate-500">
                          Column{" "}
                          {
                            column.column_number ??
                            column.column_index +
                              1
                          }
                        </div>

                      </td>


                      <td className="max-w-[260px] px-4 py-4">

                        <div className="space-y-1">

                          {(
                            column.sample_values ||
                            []
                          )
                            .slice(
                              0,
                              4
                            )
                            .map(
                              (
                                value,
                                index
                              ) => (
                                <div
                                  key={
                                    index
                                  }
                                  className="truncate font-mono text-xs text-slate-400"
                                  title={
                                    value
                                  }
                                >
                                  {
                                    value
                                  }
                                </div>
                              )
                            )}

                          {!column
                            .sample_values
                            ?.length ? (
                            <span className="text-xs text-slate-600">
                              No sample values
                            </span>
                          ) : null}

                        </div>

                      </td>


                      <td className="px-4 py-4">

                        {column
                          .recommended_protocol_header ? (

                          <div>

                            <div className="font-semibold text-emerald-300">
                              {
                                column
                                  .recommended_protocol_header
                              }
                            </div>

                            <div className="mt-1 text-[11px] text-slate-500">
                              Protocol match
                            </div>

                          </div>

                        ) : (

                          <div>

                            <div className="font-semibold text-amber-300">
                              No Protocol Match
                            </div>

                            <div className="mt-1 text-[11px] text-slate-500">
                              Review required
                            </div>

                          </div>

                        )}

                        {column.ai_review_required ? (
                          <div className="mt-2 inline-flex rounded-md border border-violet-800/70 bg-violet-950/30 px-2 py-1 text-[11px] font-semibold text-violet-300">
                            AI Review Recommended
                          </div>
                        ) : null}

                      </td>


                      <td className="px-4 py-4">

                        <div className="font-semibold text-slate-200">
                          {formatPercent(
                            column.mapping_confidence
                          )}
                        </div>

                      </td>


                      <td className="px-4 py-4">

                        <div className="text-xs text-slate-400">
                          Type:{" "}
                          <span className="text-slate-200">
                            {
                              formatStatus(
                                column.semantic_type
                              )
                            }
                          </span>
                        </div>

                        <div className="mt-1 text-xs text-slate-500">
                          Data confidence:{" "}
                          {formatPercent(
                            column.semantic_confidence
                          )}
                        </div>

                        <div className="text-xs text-slate-400">
                          Type:{" "}
                          <span className="text-slate-200">
                            {
                              formatStatus(
                                column.semantic_type
                              )
                            }
                          </span>
                        </div>

                        <div className="mt-1 text-xs text-slate-500">
                          Data confidence:{" "}
                          {formatPercent(
                            column.semantic_confidence
                          )}
                        </div>

                        <div className="mt-1 text-[11px] text-slate-600">
                          {
                            formatStatus(
                              column.match_method
                            )
                          }
                        </div>

                        {column.ai_status ? (
                          <div className="mt-1 text-[11px] text-violet-400">
                            AI Status:{" "}
                            {formatStatus(
                              column.ai_status
                            )}
                          </div>
                        ) : null}

                      </td>


                      <td className="px-4 py-4">

                        <select
                          value={
                            decision.disposition
                          }
                          onChange={
                            (
                              event
                            ) =>
                              onChangeDisposition(
                                document.doc_id,
                                column,
                                event.target
                                  .value as ColumnDecision["disposition"]
                              )
                          }
                          className="min-w-[140px] rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-200"
                        >

                          {column.matched ? (
                            <option value="approve">
                              Approve Recommendation
                            </option>
                          ) : null}

                          <option value="map">
                            Map to Protocol Field
                          </option>

                          <option value="keep">
                            Keep As-Is
                          </option>

                          <option value="rename">
                            Rename
                          </option>

                          <option value="delete">
                            Delete
                          </option>

                        </select>

                      </td>


                      <td className="min-w-[280px] px-4 py-4">

                        {decision.disposition ===
                        "delete" ? (

                          <div className="rounded-lg border border-red-900/60 bg-red-950/20 px-3 py-2 text-sm text-red-300">
                            Column marked for deletion
                          </div>

                        ) : needsProtocolDropdown ? (

                          <select
                            value={
                              decision.final_header
                            }
                            onChange={
                              (
                                event
                              ) =>
                                onUpdateDecision(
                                  document.doc_id,
                                  column.column_index,
                                  {
                                    final_header:
                                      event.target
                                        .value,
                                  }
                                )
                            }
                            className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-200"
                          >

                            <option value="">
                              Select Protocol Header
                            </option>

                            {protocolHeaders.map(
                              (
                                header
                              ) => (
                                <option
                                  key={
                                    header
                                  }
                                  value={
                                    header
                                  }
                                >
                                  {
                                    header
                                  }
                                </option>
                              )
                            )}

                          </select>

                        ) : needsRename ? (

                          <input
                            type="text"
                            value={
                              decision.final_header
                            }
                            onChange={
                              (
                                event
                              ) =>
                                onUpdateDecision(
                                  document.doc_id,
                                  column.column_index,
                                  {
                                    final_header:
                                      event.target
                                        .value,
                                  }
                                )
                            }
                            placeholder="Enter new header"
                            className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-200"
                          />

                        ) : (

                          <div className="rounded-lg border border-slate-800 bg-slate-900/60 px-3 py-2 text-sm text-slate-300">
                            {
                              decision.final_header
                            }
                          </div>

                        )}

                      </td>

                    </tr>
                  );
                }
              )}

            </tbody>

          </table>

        </div>


        <div className="flex items-center justify-between border-t border-slate-800 px-6 py-4">

          <div className="text-xs text-slate-500">
            Changes are not written to the source CSV.
          </div>

          <button
            type="button"
            onClick={
              onClose
            }
            className="rounded-lg bg-sky-600 px-5 py-2 text-sm font-semibold text-white hover:bg-sky-500"
          >
            Done Reviewing
          </button>

        </div>

      </div>

    </div>
  );
}


function HeaderStatusBadge({
  value,
}: {
  value?: string;
}) {
  const status =
    String(
      value ||
      "NEEDS_REVIEW"
    ).toUpperCase();

  if (
    status ===
    "HEADER"
  ) {
    return (
      <span className="whitespace-nowrap rounded-md border border-emerald-800/70 bg-emerald-950/30 px-2 py-1 text-xs font-semibold text-emerald-300">
        Headers in Row 1
      </span>
    );
  }

  if (
    status ===
    "NO_HEADER"
  ) {
    return (
      <span className="whitespace-nowrap rounded-md border border-sky-800/70 bg-sky-950/30 px-2 py-1 text-xs font-semibold text-sky-300">
        No Headers in Row 1
      </span>
    );
  }

  return (
    <span className="whitespace-nowrap rounded-md border border-amber-800/70 bg-amber-950/30 px-2 py-1 text-xs font-semibold text-amber-300">
      Needs Review
    </span>
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
    <div className="rounded-2xl border border-slate-800 bg-slate-900/70 px-5 py-4">

      <div className="text-[11px] uppercase tracking-[0.16em] text-slate-500">
        {label}
      </div>

      <div
        className="mt-2 truncate text-lg font-semibold text-white"
        title={
          value
        }
      >
        {value}
      </div>

    </div>
  );
}


export default function Page() {
  return (
    <Suspense
      fallback={
        <div>
          Loading...
        </div>
      }
    >
      <SchemaMappingSetContent />
    </Suspense>
  );
}