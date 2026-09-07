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

  schema_signature?: string;

  schema_group_id?: string;

  exact_schema_groupable?: boolean;

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

  schema_group_count?: number;

  schema_groups?: {
    schema_group_id: string;
    document_count: number;
    doc_ids: string[];
    }[];

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

type MappedCsvDocument = {
  doc_id?: string;
  status?: string;
  source_csv_path?: string;
  mapped_csv_path?: string;
  header_status?: string;
  source_delimiter?: string;
  output_delimiter?: string;
  source_row_count?: number;
  mapped_row_count?: number;
  source_column_count?: number;
  mapped_column_count?: number;
  output_headers?: string[];
  protocol_headers_present?: string[];
  custom_headers_retained?: string[];
  deleted_headers?: string[];
  generated_at?: string;
};

type MappedCsvManifest = {
  status?: string;
  generated_at?: string;
  generated_by?: string;
  document_count?: number;
  generated_document_count?: number;
  failed_document_count?: number;
  total_source_rows?: number;
  total_mapped_rows?: number;
  documents?: MappedCsvDocument[];
  failed_documents?: any[];
};

type MappedCsvResponse = {
  workspace?: string;
  client?: string;
  project?: string;
  header_set_id?: string;
  mapped_csv_manifest_exists?: boolean;
  mapped_csv_manifest_path?: string;
  mapped_csv_manifest?: MappedCsvManifest | null;
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
    mappedCsvData,
    setMappedCsvData,
    ] =
    useState<MappedCsvResponse | null>(
        null
    );

  const [
    generatingMappedCsvs,
    setGeneratingMappedCsvs,
    ] =
    useState(false);

  const [
    generatingRawCapture,
    setGeneratingRawCapture,
  ] =
    useState(false);

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

  const [
    activeSchemaGroupId,
    setActiveSchemaGroupId,
  ] =
    useState<string | null>(
      null
    );

  const [
    approvedDataElements,
    setApprovedDataElements,
  ] =
    useState<Record<string, boolean>>(
      {}
    );

  const [
    expandedDataElement,
    setExpandedDataElement,
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

  function openMappedCsv(
    document: MappedCsvDocument
  ) {
    const mappedPath =
      String(
        document.mapped_csv_path ||
        ""
      ).trim();

    const docId =
      String(
        document.doc_id ||
        ""
      ).trim();

    if (
      !mappedPath ||
      !docId
    ) {
      setError(
        "Mapped CSV path or Doc ID is missing."
      );

      return;
    }

    const params =
      new URLSearchParams({
        workspace,
        client,
        project,
        doc_id: docId,
        blob_path: mappedPath,
        source: "cyber2_mapped_csv",
      });

    router.push(
      `/capture/review/doc?${params.toString()}`
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
        await loadMappedCsvs();
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

  async function loadMappedCsvs() {
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
        )}/mapping/mapped-csvs?${params.toString()}`
      );

    setMappedCsvData(
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

  const protocolHeaderOrder =
    useMemo(() => {
      const order =
        new Map<string, number>();

      protocolHeaders.forEach(
        (header, index) => {
          order.set(
            String(header)
              .trim()
              .toLowerCase(),
            index
          );
        }
      );

      return order;
    }, [
      protocolHeaders,
    ]);


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

  const exactSchemaGroups =
    useMemo(() => {
        const grouped = new Map<
        string,
        IdentificationDocument[]
        >();

        for (
        const document
        of completedDocuments
        ) {
        const groupId =
            String(
            document.schema_group_id ||
            ""
            ).trim();

        if (!groupId) {
            continue;
        }

        const current =
            grouped.get(groupId) ||
            [];

        current.push(document);

        grouped.set(
            groupId,
            current
        );
        }

        return Array.from(
        grouped.entries()
        ).map(
        ([
            schemaGroupId,
            groupDocuments,
        ]) => ({
            schemaGroupId,
            documents:
            groupDocuments,
            representative:
            groupDocuments[0],
        })
        );
    }, [
        completedDocuments,
    ]);

  const sharedSchemaGroups =
    useMemo(
      () =>
        exactSchemaGroups.filter(
          (group) =>
            group.documents.length > 1
        ),
      [
        exactSchemaGroups,
      ]
    );

  const sharedSchemaDocIds =
    useMemo(() => {
      const ids =
        new Set<string>();

      for (
        const group
        of sharedSchemaGroups
      ) {
        for (
          const document
          of group.documents
        ) {
          ids.add(
            document.doc_id
          );
        }
      }

      return ids;
    }, [
      sharedSchemaGroups,
    ]);

  const individualReviewDocuments =
    useMemo(
      () =>
        completedDocuments.filter(
          (document) =>
            !sharedSchemaDocIds.has(
              document.doc_id
            )
        ),
      [
        completedDocuments,
        sharedSchemaDocIds,
      ]
    );

  const activeSchemaGroup =
    useMemo(
      () =>
        sharedSchemaGroups.find(
          (group) =>
            group.schemaGroupId ===
            activeSchemaGroupId
        ) || null,
      [
        sharedSchemaGroups,
        activeSchemaGroupId,
      ]
    );

  function getProtocolOrderedColumns(
    document:
      IdentificationDocument
  ) {
    const columns = [
      ...(document.columns || []),
    ];

    columns.sort(
      (a, b) => {
        const aHeader =
          String(
            a.recommended_protocol_header ||
            ""
          ).trim();

        const bHeader =
          String(
            b.recommended_protocol_header ||
            ""
          ).trim();

        const aOrder =
          aHeader
            ? protocolHeaderOrder.get(
                aHeader.toLowerCase()
              )
            : undefined;

        const bOrder =
          bHeader
            ? protocolHeaderOrder.get(
                bHeader.toLowerCase()
              )
            : undefined;

        const normalizedA =
          aOrder ??
          Number.MAX_SAFE_INTEGER;

        const normalizedB =
          bOrder ??
          Number.MAX_SAFE_INTEGER;

        if (
          normalizedA !==
          normalizedB
        ) {
          return (
            normalizedA -
            normalizedB
          );
        }

        return (
          a.column_index -
          b.column_index
        );
      }
    );

    return columns;
  }

  const consolidatedReviewRows =
    useMemo(() => {
      const rows: {
        document:
          IdentificationDocument;
        column:
          HeaderColumn;
        key: string;
        protocolOrder: number;
      }[] = [];

      for (
        const document
        of individualReviewDocuments
      ) {
        for (
          const column
          of document.columns || []
        ) {
          const recommended =
            String(
              column
                .recommended_protocol_header ||
              ""
            ).trim();

          const protocolIndex =
            recommended
              ? protocolHeaderOrder.get(
                  recommended.toLowerCase()
                )
              : undefined;

          rows.push({
            document,
            column,

            key:
              decisionKey(
                document.doc_id,
                column.column_index
              ),

            protocolOrder:
              protocolIndex !== undefined
                ? protocolIndex
                : Number.MAX_SAFE_INTEGER,
          });
        }
      }

      rows.sort(
        (a, b) => {
          if (
            a.protocolOrder !==
            b.protocolOrder
          ) {
            return (
              a.protocolOrder -
              b.protocolOrder
            );
          }

          const aConfidence =
            Number(
              a.column
                .mapping_confidence ||
              0
            );

          const bConfidence =
            Number(
              b.column
                .mapping_confidence ||
              0
            );

          if (
            aConfidence !==
            bConfidence
          ) {
            return (
              bConfidence -
              aConfidence
            );
          }

          return (
            a.document.doc_id.localeCompare(
              b.document.doc_id
            )
          );
        }
      );

      return rows;
    }, [
      individualReviewDocuments,
      protocolHeaderOrder,
    ]);

  const consolidatedReviewGroups =
    useMemo(() => {
      const groups: {
        groupKey: string;
        protocolHeader: string;
        rows: typeof consolidatedReviewRows;
        unmatched: boolean;
      }[] = [];

      const byKey =
        new Map<
          string,
          typeof consolidatedReviewRows
        >();

      for (
        const row
        of consolidatedReviewRows
      ) {
        const recommended =
          String(
            row.column
              .recommended_protocol_header ||
            ""
          ).trim();

        const groupKey =
          recommended ||
          "__UNMATCHED__";

        if (!byKey.has(groupKey)) {
          byKey.set(
            groupKey,
            []
          );
        }

        byKey.get(
          groupKey
        )!.push(row);
      }

      for (
        const protocolHeader
        of protocolHeaders
      ) {
        const rows =
          byKey.get(
            protocolHeader
          );

        if (
          !rows ||
          rows.length === 0
        ) {
          continue;
        }

        groups.push({
          groupKey:
            protocolHeader,

          protocolHeader,

          rows,

          unmatched:
            false,
        });
      }

      const unmatchedRows =
        byKey.get(
          "__UNMATCHED__"
        ) || [];

      if (
        unmatchedRows.length > 0
      ) {
        groups.push({
          groupKey:
            "__UNMATCHED__",

          protocolHeader:
            "Unmatched Fields",

          rows:
            unmatchedRows,

          unmatched:
            true,
        });
      }

      return groups;
    }, [
      consolidatedReviewRows,
      protocolHeaders,
    ]);

  useEffect(() => {
    if (
      consolidatedReviewGroups.length ===
      0
    ) {
      setExpandedDataElement(
        null
      );

      return;
    }

    setExpandedDataElement(
      (current) => {
        if (
          current &&
          consolidatedReviewGroups.some(
            (group) =>
              group.groupKey ===
              current
          )
        ) {
          return current;
        }

        return (
          consolidatedReviewGroups[0]
            ?.groupKey ||
          null
        );
      }
    );
  }, [
    consolidatedReviewGroups,
  ]);

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
      () =>
        consolidatedReviewRows
          .filter(
            (row) =>
              !String(
                row.column
                  .recommended_protocol_header ||
                ""
              ).trim()
          )
          .map(
            (row) =>
              row.key
          ),
      [
        consolidatedReviewRows,
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

  function updateGroupDecision(
    documents:
        IdentificationDocument[],
    columnIndex: number,
    patch:
        Partial<ColumnDecision>
    ) {
    setDecisions(
        (current) => {
        const next = {
            ...current,
        };

        for (
            const document
            of documents
        ) {
            const key =
            decisionKey(
                document.doc_id,
                columnIndex
            );

            next[key] = {
            disposition:
                current[key]
                ?.disposition ||
                "keep",

            final_header:
                current[key]
                ?.final_header ||
                "",

            ...patch,
            };
        }

        return next;
        }
    );
    }

  function changeGroupDisposition(
    documents:
        IdentificationDocument[],
    column: HeaderColumn,
    disposition:
        ColumnDecision[
        "disposition"
        ]
    ) {
    const representative =
        documents[0];

    if (!representative) {
        return;
    }

    const key =
        decisionKey(
        representative.doc_id,
        column.column_index
        );

    let finalHeader =
        decisions[key]
        ?.final_header ||
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
            column.column_index + 1
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
        if (
        !protocolHeaders.includes(
            finalHeader
        )
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

    updateGroupDecision(
        documents,
        column.column_index,
        {
        disposition,
        final_header:
            finalHeader,
        }
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

  function approveDataElement(
    groupKey: string
  ) {
    setApprovedDataElements(
      (current) => ({
        ...current,
        [groupKey]: true,
      })
    );

    const currentIndex =
      consolidatedReviewGroups.findIndex(
        (group) =>
          group.groupKey ===
          groupKey
      );

    let nextGroupKey:
      string | null = null;

    for (
      let index =
        currentIndex + 1;
      index <
        consolidatedReviewGroups.length;
      index += 1
    ) {
      const candidate =
        consolidatedReviewGroups[
          index
        ];

      if (
        !approvedDataElements[
          candidate.groupKey
        ]
      ) {
        nextGroupKey =
          candidate.groupKey;

        break;
      }
    }

    setExpandedDataElement(
      nextGroupKey
    );
  }


  function reopenDataElement(
    groupKey: string
  ) {
    setApprovedDataElements(
      (current) => ({
        ...current,
        [groupKey]: false,
      })
    );

    setExpandedDataElement(
      groupKey
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

  async function generateMappedCsvs() {
    if (
      !client ||
      !project ||
      !headerSetId
    ) {
      return;
    }

    setGeneratingMappedCsvs(true);
    setError("");
    setMessage("");

    try {
      const result =
        await apiPost(
          `/api/${encodeURIComponent(
            workspace
          )}/cyber2/header-sets/${encodeURIComponent(
            headerSetId
          )}/mapping/generate-mapped-csvs`,
          {
            client,
            project,
            generated_by: "",
            overwrite_existing: true,
          }
        );

      setMessage(
        result?.message ||
        "Mapped CSV generation completed."
      );

      await loadMappedCsvs();

    } catch (err: any) {
      console.error(
        "Mapped CSV generation failed:",
        err
      );

      setError(
        err?.message ||
        "Mapped CSV generation failed."
      );

    } finally {
      setGeneratingMappedCsvs(false);
    }
  }

  async function generateRawCapture() {
    if (
      !client ||
      !project ||
      !headerSetId
    ) {
      return;
    }

    setGeneratingRawCapture(true);
    setError("");
    setMessage("");

    try {
      const result =
        await apiPost(
          `/api/${encodeURIComponent(
            workspace
          )}/cyber2/header-sets/${encodeURIComponent(
            headerSetId
          )}/mapping/generate-raw-capture`,
          {
            client,
            project,
            generated_by: "",
            replace_header_set_rows: true,
          }
        );

      setMessage(
        result?.message ||
        "Raw XL capture generation completed."
      );

    } catch (err: any) {
      console.error(
        "Raw XL capture generation failed:",
        err
      );

      setError(
        err?.message ||
        "Raw XL capture generation failed."
      );

    } finally {
      setGeneratingRawCapture(false);
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


                <div className="mt-6">

                  <div className="flex flex-wrap items-center justify-between gap-3">

                    <div>

                      <h2 className="text-lg font-semibold text-white">
                        Exact Schema Groups
                      </h2>

                      <p className="mt-1 text-sm text-slate-500">
                        CSVs with identical Row 1 headers are reviewed once
                        and the approved mapping is applied to every CSV in
                        the matching schema group.
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


                  <div className="mt-4 space-y-3">

                    {sharedSchemaGroups.length ===
                    0 ? (

                      <div className="rounded-xl border border-dashed border-slate-700 bg-slate-900/30 px-5 py-8 text-center text-sm text-slate-500">
                        No multi-file exact schema groups were found.
                      </div>

                    ) : (

                      sharedSchemaGroups.map(
                        (group) => {

                          const representative =
                            group.representative;

                          const orderedColumns =
                            representative
                              ? getProtocolOrderedColumns(
                                  representative
                                )
                              : [];

                          return (
                            <div
                              key={
                                group.schemaGroupId
                              }
                              className="overflow-hidden rounded-xl border border-slate-800 bg-slate-900/60"
                            >

                              <div className="flex flex-wrap items-center justify-between gap-4 px-5 py-4">

                                <div>

                                  <div className="font-mono text-sm font-semibold text-sky-400">
                                    {
                                      group.schemaGroupId
                                    }
                                  </div>

                                  <div className="mt-1 text-xs text-slate-400">
                                    {
                                      group.documents.length
                                    }{" "}
                                    CSVs with identical headers
                                  </div>

                                </div>


                                <button
                                  type="button"
                                  onClick={() =>
                                    setActiveSchemaGroupId(
                                      group.schemaGroupId
                                    )
                                  }
                                  className="rounded-lg bg-sky-600 px-4 py-2 text-xs font-semibold text-white hover:bg-sky-500"
                                >
                                  Review Mapping for All{" "}
                                  {
                                    group.documents.length
                                  }
                                </button>

                              </div>


                              <div className="border-t border-slate-800 px-5 py-4">

                                <div className="text-[11px] uppercase tracking-wide text-slate-500">
                                  Protocol-Aligned Mapping Preview
                                </div>

                                <div className="mt-3 flex flex-wrap gap-2">

                                  {orderedColumns.map(
                                    (column) => (

                                      <div
                                        key={
                                          column.column_index
                                        }
                                        className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2"
                                      >

                                        <div className="text-[11px] text-slate-500">
                                          {
                                            column.source_header ||
                                            `Column ${
                                              column.column_index +
                                              1
                                            }`
                                          }
                                        </div>

                                        <div className="mt-1 text-xs font-semibold text-emerald-300">
                                          →{" "}
                                          {
                                            column.recommended_protocol_header ||
                                            "Unmatched"
                                          }
                                        </div>

                                      </div>

                                    )
                                  )}

                                </div>


                                <div className="mt-4 flex flex-wrap gap-2">

                                  {group.documents.map(
                                    (document) => (

                                      <span
                                        key={
                                          document.doc_id
                                        }
                                        className="rounded-md border border-slate-800 bg-slate-950 px-2 py-1 font-mono text-[11px] text-slate-400"
                                      >
                                        {
                                          document.doc_id
                                        }
                                      </span>

                                    )
                                  )}

                                </div>

                              </div>

                            </div>
                          );
                        }
                      )

                    )}

                  </div>

                </div>


                <div className="mt-8">

                  <div>

                    <h2 className="text-lg font-semibold text-white">
                      Consolidated Mapping Review
                    </h2>

                    <p className="mt-1 max-w-4xl text-sm leading-6 text-slate-500">
                      Unique and headerless CSV schemas are consolidated by
                      INSYT&apos;s recommended Project Protocol field. Protocol
                      fields are shown in the exact order defined by the
                      assigned Project Protocol, with unmatched fields last.
                    </p>

                  </div>


                  {consolidatedReviewGroups.length ===
                  0 ? (

                    <div className="mt-4 rounded-xl border border-dashed border-slate-700 bg-slate-900/30 px-5 py-8 text-center text-sm text-slate-500">
                      All identified CSVs are covered by multi-file exact schema groups.
                    </div>

                  ) : (

                    <div className="mt-4 space-y-5">

                      {consolidatedReviewGroups.map(
                        (group) => {

                            const approved =
                            Boolean(
                                approvedDataElements[
                                group.groupKey
                                ]
                            );

                            const expanded =
                            expandedDataElement ===
                            group.groupKey;

                            return (

                          <div
                            key={
                              group.groupKey
                            }
                            className={
                              group.unmatched
                                ? "overflow-hidden rounded-2xl border border-amber-900/60 bg-amber-950/10"
                                : "overflow-hidden rounded-2xl border border-slate-800 bg-slate-900/60"
                            }
                          >

                            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 px-5 py-4">

                              <div>

                                <div
                                  className={
                                    group.unmatched
                                      ? "text-sm font-semibold text-amber-300"
                                      : "text-sm font-semibold text-emerald-300"
                                  }
                                >
                                  {
                                    group.protocolHeader
                                  }
                                </div>

                                <div className="mt-1 text-xs text-slate-500">
                                  {
                                    group.rows.length
                                  }{" "}
                                  source column
                                  {
                                    group.rows.length ===
                                    1
                                      ? ""
                                      : "s"
                                  }
                                </div>

                              </div>


                              <div className="flex flex-wrap items-center gap-2">

                                {group.unmatched ? (
                                    <>
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
                                    </>
                                ) : null}


                                {approved ? (
                                    <span className="rounded-md border border-emerald-800 bg-emerald-950/30 px-3 py-1.5 text-xs font-semibold text-emerald-300">
                                    Approved
                                    </span>
                                ) : (
                                    <span className="rounded-md border border-amber-800 bg-amber-950/20 px-3 py-1.5 text-xs font-semibold text-amber-300">
                                    Needs Review
                                    </span>
                                )}


                                <button
                                    type="button"
                                    onClick={() => {
                                    if (approved) {
                                        reopenDataElement(
                                        group.groupKey
                                        );
                                    } else {
                                        setExpandedDataElement(
                                        expanded
                                            ? null
                                            : group.groupKey
                                        );
                                    }
                                    }}
                                    className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-xs font-semibold text-slate-300 hover:bg-slate-800"
                                >
                                    {approved
                                    ? "Reopen"
                                    : expanded
                                        ? "Collapse ▲"
                                        : "Review ▼"}
                                </button>

                                </div>

                            </div>


                            {expanded ? (
                                <>

                                    <div className="overflow-x-auto">

                                    <table className="w-full min-w-[1450px] text-sm">

                                <thead className="bg-slate-950 text-left text-[11px] uppercase tracking-wide text-slate-500">

                                  <tr>

                                    <th className="w-12 px-4 py-3">
                                      Select
                                    </th>

                                    <th className="px-4 py-3">
                                      Source Header
                                    </th>

                                    <th className="px-4 py-3">
                                      Doc ID
                                    </th>

                                    <th className="px-4 py-3">
                                      Workbook / Sheet
                                    </th>

                                    <th className="px-4 py-3">
                                      Sample Data
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

                                  {group.rows.map(
                                    ({
                                      document,
                                      column,
                                      key,
                                    }) => {

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
                                        !column
                                          .recommended_protocol_header;

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
                                                  toggleUnmatched(
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
                                              Source Column{" "}
                                              {
                                                column.column_number ??
                                                column.column_index +
                                                1
                                              }
                                            </div>

                                          </td>


                                          <td className="whitespace-nowrap px-4 py-4 font-mono text-xs text-sky-400">
                                            {
                                              document.doc_id
                                            }
                                          </td>


                                          <td className="max-w-[260px] px-4 py-4">

                                            <div className="truncate text-xs text-slate-300">
                                              {
                                                document.original_workbook_name ||
                                                document.original_filename ||
                                                "—"
                                              }
                                            </div>

                                            <div className="mt-1 truncate text-[11px] text-slate-500">
                                              {
                                                document.sheet_name ||
                                                "—"
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
                                                  3
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

                                            <div className="font-semibold text-slate-200">
                                              {formatPercent(
                                                column.mapping_confidence
                                              )}
                                            </div>

                                            {column.ai_confidence !==
                                            null &&
                                            column.ai_confidence !==
                                            undefined ? (

                                              <div className="mt-1 text-[11px] text-violet-400">
                                                AI{" "}
                                                {formatPercent(
                                                  column.ai_confidence
                                                )}
                                              </div>

                                            ) : null}

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

                                            <div className="mt-1 text-[11px] text-slate-500">
                                              {
                                                formatStatus(
                                                  column.match_method
                                                )
                                              }
                                            </div>

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
                                                  changeDisposition(
                                                    document.doc_id,
                                                    column,
                                                    event.target
                                                      .value as ColumnDecision["disposition"]
                                                  )
                                              }
                                              className="min-w-[160px] rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-200"
                                            >

                                              {column
                                                .recommended_protocol_header ? (
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
                                                    updateDecision(
                                                      document.doc_id,
                                                      column.column_index,
                                                      {
                                                        final_header:
                                                          event.target.value,
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
                                                    updateDecision(
                                                      document.doc_id,
                                                      column.column_index,
                                                      {
                                                        final_header:
                                                          event.target.value,
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

                                <div className="flex items-center justify-between gap-4 border-t border-slate-800 px-5 py-4">

                                    <div className="text-xs text-slate-500">
                                        Approving this data element accepts the current mapping decisions for all source columns shown above.
                                    </div>

                                    <button
                                        type="button"
                                        onClick={() =>
                                        approveDataElement(
                                            group.groupKey
                                        )
                                        }
                                        className="rounded-lg bg-emerald-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-emerald-500"
                                    >
                                        {group.unmatched
                                        ? "Approve Unmatched Review"
                                        : `Approve ${group.protocolHeader}`}
                                    </button>

                                    </div>

                                </>
                                ) : null}

                          </div>
                          );
                        }
                    )}

                    </div>

                  )}

                </div>


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

                <div className="mt-8 rounded-2xl border border-slate-800 bg-slate-900/60">

                    <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-800 px-5 py-4">

                        <div>

                            <h2 className="text-lg font-semibold text-white">
                                Mapped CSV Outputs
                            </h2>

                            <p className="mt-1 text-sm text-slate-500">
                                Generate new protocol-aligned working CSVs from the approved Header Set mapping.
                                Source CSV files remain unchanged.
                            </p>

                        </div>

                        <div className="flex flex-wrap gap-2">

                            <button
                                type="button"
                                onClick={
                                generateMappedCsvs
                                }
                                disabled={
                                generatingMappedCsvs ||
                                !mappingData?.approved_mapping_exists
                                }
                                className="rounded-lg bg-sky-600 px-4 py-2 text-sm font-semibold text-white hover:bg-sky-500 disabled:cursor-not-allowed disabled:opacity-40"
                            >
                                {generatingMappedCsvs
                                ? "Generating..."
                                : "Generate Mapped CSVs"}
                            </button>

                            <button
                                type="button"
                                onClick={
                                generateRawCapture
                                }
                                disabled={
                                generatingRawCapture ||
                                !mappedCsvData?.mapped_csv_manifest_exists ||
                                (
                                    mappedCsvData
                                    ?.mapped_csv_manifest
                                    ?.generated_document_count ??
                                    0
                                ) === 0
                                }
                                className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-40"
                            >
                                {generatingRawCapture
                                ? "Generating Raw Capture..."
                                : "Generate Raw Capture"}
                            </button>

                        </div>

                    </div>


                    {!mappingData?.approved_mapping_exists ? (

                        <div className="px-5 py-8 text-center text-sm text-slate-500">
                        Approve Header Mapping before generating mapped CSV outputs.
                        </div>

                    ) : !mappedCsvData
                        ?.mapped_csv_manifest_exists ? (

                        <div className="px-5 py-8 text-center text-sm text-slate-500">
                        No mapped CSV outputs have been generated yet.
                        </div>

                    ) : (

                        <>

                        <div className="grid gap-4 border-b border-slate-800 px-5 py-4 md:grid-cols-4">

                            <MetricCard
                            label="Generated"
                            value={String(
                                mappedCsvData
                                ?.mapped_csv_manifest
                                ?.generated_document_count ??
                                0
                            )}
                            />

                            <MetricCard
                            label="Failed"
                            value={String(
                                mappedCsvData
                                ?.mapped_csv_manifest
                                ?.failed_document_count ??
                                0
                            )}
                            />

                            <MetricCard
                            label="Source Rows"
                            value={String(
                                mappedCsvData
                                ?.mapped_csv_manifest
                                ?.total_source_rows ??
                                0
                            )}
                            />

                            <MetricCard
                            label="Mapped Rows"
                            value={String(
                                mappedCsvData
                                ?.mapped_csv_manifest
                                ?.total_mapped_rows ??
                                0
                            )}
                            />

                        </div>


                        <div className="overflow-x-auto">

                            <table className="w-full min-w-[1100px] text-sm">

                            <thead className="bg-slate-950 text-left text-[11px] uppercase tracking-wide text-slate-500">

                                <tr>

                                <th className="px-4 py-3">
                                    Doc ID
                                </th>

                                <th className="px-4 py-3">
                                    Rows
                                </th>

                                <th className="px-4 py-3">
                                    Columns
                                </th>

                                <th className="px-4 py-3">
                                    Protocol Fields
                                </th>

                                <th className="px-4 py-3">
                                    Custom Fields
                                </th>

                                <th className="px-4 py-3">
                                    Deleted
                                </th>

                                <th className="px-4 py-3">
                                    Status
                                </th>

                                <th className="px-4 py-3">
                                    Merge Ready
                                </th>

                                <th className="px-4 py-3">
                                    Action
                                </th>

                                </tr>

                            </thead>


                            <tbody className="divide-y divide-slate-800">

                                {(
                                mappedCsvData
                                    ?.mapped_csv_manifest
                                    ?.documents ||
                                []
                                ).map(
                                (document) => (

                                    <tr
                                    key={
                                        document.doc_id
                                    }
                                    className="bg-slate-950/20"
                                    >

                                    <td className="px-4 py-4 font-mono text-xs text-sky-400">
                                        {
                                        document.doc_id
                                        }
                                    </td>

                                    <td className="px-4 py-4 text-slate-300">
                                        {
                                        document.mapped_row_count ??
                                        0
                                        }
                                    </td>

                                    <td className="px-4 py-4 text-slate-300">
                                        {
                                        document.mapped_column_count ??
                                        0
                                        }
                                    </td>

                                    <td className="px-4 py-4 text-slate-300">
                                        {
                                        document
                                            .protocol_headers_present
                                            ?.length ??
                                        0
                                        }
                                    </td>

                                    <td className="px-4 py-4 text-slate-300">
                                        {
                                        document
                                            .custom_headers_retained
                                            ?.length ??
                                        0
                                        }
                                    </td>

                                    <td className="px-4 py-4 text-slate-300">
                                        {
                                        document
                                            .deleted_headers
                                            ?.length ??
                                        0
                                        }
                                    </td>

                                    <td className="px-4 py-4">
                                        <span className="rounded-md border border-emerald-800 bg-emerald-950/30 px-2 py-1 text-xs font-semibold text-emerald-300">
                                            {
                                            formatStatus(
                                                document.status
                                            )
                                            }
                                        </span>
                                        </td>

                                        <td className="px-4 py-4">
                                        <span className="rounded-md border border-sky-800 bg-sky-950/30 px-2 py-1 text-xs font-semibold text-sky-300">
                                            Ready
                                        </span>
                                        </td>

                                        <td className="px-4 py-4">

                                        <button
                                            type="button"
                                            onClick={() =>
                                            openMappedCsv(
                                                document
                                            )
                                            }
                                            disabled={
                                            !document.mapped_csv_path
                                            }
                                            className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-xs font-semibold text-slate-200 hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-40"
                                        >
                                            Open
                                        </button>

                                        </td>

                                        </tr>

                                    )
                                )}

                            </tbody>

                            </table>

                        </div>

                        </>

                    )}

                    </div>

              </>

            )}

          </>

        )}

        {activeSchemaGroup &&
        activeSchemaGroup.representative ? (

          <MappingModal
            document={
              activeSchemaGroup.representative
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
              (
                _docId,
                column,
                disposition
              ) =>
                changeGroupDisposition(
                  activeSchemaGroup.documents,
                  column,
                  disposition
                )
            }

            onUpdateDecision={
              (
                _docId,
                columnIndex,
                patch
              ) =>
                updateGroupDecision(
                  activeSchemaGroup.documents,
                  columnIndex,
                  patch
                )
            }

            onClose={() =>
              setActiveSchemaGroupId(
                null
              )
            }
          />

        ) : null}


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

  const protocolOrder =
    new Map<string, number>();

  protocolHeaders.forEach(
    (header, index) => {
      protocolOrder.set(
        String(header)
          .trim()
          .toLowerCase(),
        index
      );
    }
  );

  const columns = [
    ...(document.columns || []),
  ].sort(
    (a, b) => {
      const aHeader =
        String(
          a.recommended_protocol_header ||
          ""
        ).trim();

      const bHeader =
        String(
          b.recommended_protocol_header ||
          ""
        ).trim();

      const aOrder =
        aHeader
          ? protocolOrder.get(
              aHeader.toLowerCase()
            )
          : undefined;

      const bOrder =
        bHeader
          ? protocolOrder.get(
              bHeader.toLowerCase()
            )
          : undefined;

      const normalizedA =
        aOrder ??
        Number.MAX_SAFE_INTEGER;

      const normalizedB =
        bOrder ??
        Number.MAX_SAFE_INTEGER;

      if (
        normalizedA !==
        normalizedB
      ) {
        return (
          normalizedA -
          normalizedB
        );
      }

      return (
        a.column_index -
        b.column_index
      );
    }
  );


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