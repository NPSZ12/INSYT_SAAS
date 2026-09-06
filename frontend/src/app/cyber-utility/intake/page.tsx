"use client";

import {
  Suspense,
  useEffect,
  useMemo,
  useState,
} from "react";

import {
  ArrowLeft,
  FileSpreadsheet,
  RefreshCw,
  ShieldCheck,
} from "lucide-react";

import {
  useRouter,
  useSearchParams,
} from "next/navigation";

import AppShell from "../../../components/AppShell";
import PageContainer from "../../../components/PageContainer";
import PageHeader from "../../../components/PageHeader";
import { apiGet, apiPost } from "../../../lib/api";
import CyberUtilityWorkflowNav from "../../../components/CyberUtilityWorkflowNav";

type Cyber2IntakeDocument = {
  doc_id: string;

  file_id?: string;

  status?: string;

  source_job_id?: string;
  detection_job_id?: string;

  classification?: string;
  source_type?: string;

  source_csv_path?: string;

  original_filename?: string;
  original_workbook_name?: string;
  original_workbook_file_id?: string;

  sheet_name?: string;
  sheet_index?: number | null;
  sheet_visibility?: string;

  entity_types?: string[];

  profiled_entity_count?: number;

  detection_mode?: string;

  type_profile_complete?: boolean | null;
  entity_counts_complete?: boolean | null;

  intake_index_path?: string;

  sent_to_cyber2_at?: string;
  sent_to_cyber2_by?: string;

  last_modified?: string;

  header_set_id?: string;
  cyber2_stage?: string;
  header_set_status?: string;
  sent_to_header_mapping_at?: string;
  sent_to_header_mapping_by?: string;
};

type Cyber2IntakeResponse = {
  workspace?: string;
  client?: string;
  project?: string;

  intake_count?: number;

  source_storage_account?: string;
  source_container?: string;
  source_mode?: string;

  documents?: Cyber2IntakeDocument[];
};

function Cyber2IntakeContent() {
  const searchParams =
    useSearchParams();

  const router =
    useRouter();

  const workspace =
    searchParams.get("workspace") ||
    "capture";

  const client =
    searchParams.get("client") ||
    "";

  const project =
    searchParams.get("project") ||
    "";

  const [
    intakeData,
    setIntakeData,
  ] =
    useState<Cyber2IntakeResponse | null>(
      null
    );

  const [
    loading,
    setLoading,
  ] =
    useState(false);

  const [
    error,
    setError,
  ] =
    useState("");

  const [
    creatingHeaderSet,
    setCreatingHeaderSet,
  ] =
    useState(false);

  const [
    headerSetMessage,
    setHeaderSetMessage,
  ] =
    useState("");

  const [
    selectedDocIds,
    setSelectedDocIds,
  ] = useState<Record<string, boolean>>({});

  const [
    classificationFilter,
    setClassificationFilter,
  ] = useState<"all" | "hit" | "no_hit">("all");

  const [
    entityTypeFilter,
    setEntityTypeFilter,
  ] = useState("all");

  const [
    workbookFilter,
    setWorkbookFilter,
  ] = useState("all");

  const [
    searchText,
    setSearchText,
  ] = useState("");

  const [
    sentClassificationFilter,
    setSentClassificationFilter,
  ] =
    useState<
      "all" | "hit" | "no_hit"
    >("all");

  const [
    sentEntityTypeFilter,
    setSentEntityTypeFilter,
  ] =
    useState("all");

  const [
    sentWorkbookFilter,
    setSentWorkbookFilter,
  ] =
    useState("all");

  const [
    sentSearchText,
    setSentSearchText,
  ] =
    useState("");

  const [
    expandedHeaderSets,
    setExpandedHeaderSets,
  ] =
    useState<Record<string, boolean>>(
      {}
    );

  const [
    intakeExpanded,
    setIntakeExpanded,
  ] = useState(true);

  async function loadIntake() {
    if (!client || !project) {
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
          )}/cyber2/intake?${params.toString()}`
        );

      setIntakeData(
        response
      );

    } catch (err: any) {
      console.error(
        "Failed to load Cyber² Intake:",
        err
      );

      setError(
        err?.message ||
          "Unable to load Cyber² Intake."
      );

    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadIntake();
  }, [
    workspace,
    client,
    project,
  ]);

  const documents =
    intakeData?.documents ||
    [];

  const availableDocuments =
    documents.filter(
      (doc) =>
        !String(
          doc.header_set_id ||
          ""
        ).trim()
    );

  const sentToHeaderDocuments =
    documents.filter(
      (doc) =>
        Boolean(
          String(
            doc.header_set_id ||
            ""
          ).trim()
        )
    );

  function normalizeClassification(
    value?: string
  ) {
    return String(value || "")
      .trim()
      .toUpperCase()
      .replace(/[_-]+/g, " ")
      .replace(/\s+/g, " ");
  }

  const entityTypeOptions = useMemo(() => {
    const values = new Set<string>();

    for (const doc of documents) {
      for (const entityType of doc.entity_types || []) {
        const clean = String(entityType || "").trim();

        if (clean) {
          values.add(clean);
        }
      }
    }

    return Array.from(values).sort((a, b) =>
      a.localeCompare(b)
    );
  }, [documents]);

  const workbookOptions = useMemo(() => {
    const values = new Set<string>();

    for (const doc of documents) {
      const workbook =
        String(
          doc.original_workbook_name ||
            doc.original_filename ||
            ""
        ).trim();

      if (workbook) {
        values.add(workbook);
      }
    }

    return Array.from(values).sort((a, b) =>
      a.localeCompare(b)
    );
  }, [documents]);

  const filteredDocuments = useMemo(() => {
    const search = searchText
      .trim()
      .toLowerCase();

    return availableDocuments.filter((doc) => {
      const classification =
        normalizeClassification(
          doc.classification
        );

      if (
        classificationFilter === "hit" &&
        classification !== "HIT"
      ) {
        return false;
      }

      if (
        classificationFilter === "no_hit" &&
        classification === "HIT"
      ) {
        return false;
      }

      if (
        entityTypeFilter !== "all" &&
        !(doc.entity_types || []).includes(
          entityTypeFilter
        )
      ) {
        return false;
      }

      const workbook =
        String(
          doc.original_workbook_name ||
            doc.original_filename ||
            ""
        ).trim();

      if (
        workbookFilter !== "all" &&
        workbook !== workbookFilter
      ) {
        return false;
      }

      if (search) {
        const searchable = [
          doc.doc_id,
          doc.original_filename,
          doc.original_workbook_name,
          doc.sheet_name,
          doc.source_csv_path,
          doc.classification,
          ...(doc.entity_types || []),
        ]
          .filter(Boolean)
          .join(" ")
          .toLowerCase();

        if (!searchable.includes(search)) {
          return false;
        }
      }

      return true;
    });
  }, [
    availableDocuments,
    classificationFilter,
    entityTypeFilter,
    workbookFilter,
    searchText,
  ]);

  const filteredSentToHeaderDocuments =
    useMemo(() => {
      const search =
        sentSearchText
          .trim()
          .toLowerCase();

      return sentToHeaderDocuments.filter(
        (doc) => {
          const classification =
            normalizeClassification(
              doc.classification
            );

          if (
            sentClassificationFilter ===
              "hit" &&
            classification !== "HIT"
          ) {
            return false;
          }

          if (
            sentClassificationFilter ===
              "no_hit" &&
            classification === "HIT"
          ) {
            return false;
          }

          if (
            sentEntityTypeFilter !==
              "all" &&
            !(
              doc.entity_types || []
            ).includes(
              sentEntityTypeFilter
            )
          ) {
            return false;
          }

          const workbook =
            String(
              doc.original_workbook_name ||
                doc.original_filename ||
                ""
            ).trim();

          if (
            sentWorkbookFilter !==
              "all" &&
            workbook !==
              sentWorkbookFilter
          ) {
            return false;
          }

          if (search) {
            const searchable = [
              doc.doc_id,
              doc.header_set_id,
              doc.original_filename,
              doc.original_workbook_name,
              doc.sheet_name,
              doc.source_csv_path,
              doc.classification,
              ...(doc.entity_types ||
                []),
            ]
              .filter(Boolean)
              .join(" ")
              .toLowerCase();

            if (
              !searchable.includes(
                search
              )
            ) {
              return false;
            }
          }

          return true;
        }
      );
    }, [
      sentToHeaderDocuments,
      sentClassificationFilter,
      sentEntityTypeFilter,
      sentWorkbookFilter,
      sentSearchText,
    ]);
  
  const sentHeaderSets =
    useMemo(() => {
      const grouped: Record<
        string,
        Cyber2IntakeDocument[]
      > = {};

      for (
        const doc
        of filteredSentToHeaderDocuments
      ) {
        const headerSetId =
          String(
            doc.header_set_id ||
              "UNASSIGNED"
          ).trim();

        if (!grouped[headerSetId]) {
          grouped[headerSetId] = [];
        }

        grouped[headerSetId].push(
          doc
        );
      }

      return Object.entries(
        grouped
      )
        .map(
          ([
            headerSetId,
            docs,
          ]) => ({
            headerSetId,
            docs,
            sentAt:
              docs
                .map(
                  (doc) =>
                    doc.sent_to_header_mapping_at ||
                    ""
                )
                .sort()
                .reverse()[0] || "",
          })
        )
        .sort(
          (a, b) =>
            b.sentAt.localeCompare(
              a.sentAt
            )
        );
    }, [
      filteredSentToHeaderDocuments,
    ]);

  const selectedCount = Object.values(
    selectedDocIds
  ).filter(Boolean).length;

  function toggleDocument(
    docId: string,
    selected: boolean
  ) {
    setSelectedDocIds((current) => ({
      ...current,
      [docId]: selected,
    }));
  }

  function selectAllFiltered() {
    setSelectedDocIds((current) => {
      const next = {
        ...current,
      };

      for (const doc of filteredDocuments) {
        next[doc.doc_id] = true;
      }

      return next;
    });
  }

  function clearSelection() {
    setSelectedDocIds({});
  }

  async function createHeaderSet() {
    const selectedDocuments =
      availableDocuments.filter(
        (doc) =>
          Boolean(
            selectedDocIds[
              doc.doc_id
            ]
          )
      );

    if (
      selectedDocuments.length === 0
    ) {
      setHeaderSetMessage(
        "Select at least one CSV."
      );

      return;
    }

    setCreatingHeaderSet(true);
    setHeaderSetMessage("");
    setError("");

    try {
      const result =
        await apiPost(
          `/api/${encodeURIComponent(
            workspace
          )}/cyber2/header-sets`,
          {
            client,
            project,

            doc_ids:
              selectedDocuments.map(
                (doc) =>
                  doc.doc_id
              ),

            requested_by: "",
          }
        );

      setHeaderSetMessage(
        result?.message ||
          "Header Set created."
      );

      setSelectedDocIds({});

      await loadIntake();

    } catch (err: any) {
      console.error(
        "Failed to create Header Set:",
        err
      );

      setError(
        err?.message ||
          "Unable to create Header Set."
      );

    } finally {
      setCreatingHeaderSet(
        false
      );
    }
  }

  const cyber2LandingParams =
    new URLSearchParams();

  cyber2LandingParams.set(
    "workspace",
    workspace
  );

  if (client) {
    cyber2LandingParams.set(
      "client",
      client
    );
  }

  if (project) {
    cyber2LandingParams.set(
      "project",
      project
    );
  }

  const cyber2LandingHref =
    `/cyber-utility?${cyber2LandingParams.toString()}`;

  function openDocument(
    doc: Cyber2IntakeDocument
  ) {
    const docId =
      String(
        doc.doc_id ||
        ""
      ).trim();

    const nativeBlob =
      String(
        doc.source_csv_path ||
        ""
      ).trim();

    if (!docId) {
      console.error(
        "Unable to open Cyber² Intake file because doc_id is missing.",
        doc
      );

      return;
    }

    if (!nativeBlob) {
      console.error(
        "Unable to open Cyber² Intake file because source_csv_path is missing.",
        doc
      );

      setError(
        "Unable to open this file because its staged CSV path is missing."
      );

      return;
    }

    const params =
      new URLSearchParams();

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

    params.set(
      "doc",
      docId
    );

    params.set(
      "native_blob",
      nativeBlob
    );

    const returnParams =
      new URLSearchParams();

    returnParams.set(
      "workspace",
      workspace
    );

    if (client) {
      returnParams.set(
        "client",
        client
      );
    }

    if (project) {
      returnParams.set(
        "project",
        project
      );
    }

    params.set(
      "return_to",
      `/cyber-utility/intake?${returnParams.toString()}`
    );

    params.set(
      "return_label",
      "Intake & Preparation"
    );

    router.push(
      `/capture/review/doc?${params.toString()}`
    );
  }

  function toggleHeaderSet(
    headerSetId: string
  ) {
    setExpandedHeaderSets(
      (current) => ({
        ...current,
        [headerSetId]:
          !current[headerSetId],
      })
    );
  }

  return (
    <AppShell>
      <PageContainer>
        <CyberUtilityWorkflowNav />

        <div className="mb-6">

          <div className="mb-4">
            <button
              type="button"
              onClick={() =>
                router.push(
                  cyber2LandingHref
                )
              }
              className="inline-flex items-center gap-2 rounded-xl border border-slate-700 bg-slate-900 px-4 py-2 text-sm font-medium text-slate-200 transition-colors hover:border-slate-600 hover:bg-slate-800 hover:text-white"
            >
              <ArrowLeft className="h-4 w-4" />

              Return to Cyber² Landing
            </button>
          </div>

          <div className="flex flex-wrap items-start justify-between gap-4">

            <PageHeader
              title="Cyber² Intake & Preparation"
              subtitle="Structured-data source files registered from INSYT Promotion for the active project."
            />

            <button
              type="button"
              onClick={loadIntake}
              disabled={loading}
              className="inline-flex items-center gap-2 rounded-xl border border-slate-700 bg-slate-900 px-4 py-2 text-sm text-slate-200 hover:bg-slate-800 disabled:opacity-50"
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

        </div>


        <div className="mb-6 grid gap-4 md:grid-cols-4">

          <MetricCard
            label="Files Ready"
            value={String(
              availableDocuments.length
            )}
          />

          <MetricCard
            label="Workspace"
            value={workspace}
          />

          <MetricCard
            label="Client"
            value={client || "—"}
          />

          <MetricCard
            label="Project"
            value={
              project
                ? project.replaceAll(
                    "_",
                    " "
                  )
                : "—"
            }
          />

        </div>


        <div className="mb-6 rounded-xl border border-violet-900/60 bg-violet-950/20 px-5 py-4">

          <div className="flex items-start gap-3">

            <ShieldCheck className="mt-0.5 h-5 w-5 shrink-0 text-violet-300" />

            <div>

              <div className="text-sm font-semibold text-violet-200">
                Source-Preserving Intake
              </div>

              <p className="mt-1 text-xs leading-5 text-slate-400">
                Cyber² Intake references the existing staged CSV
                created during Initial Ingestion. No duplicate source
                CSV is created. New working files will be created only
                when processing changes the data.
              </p>

            </div>

          </div>

        </div>

        <div className="mb-6 overflow-hidden rounded-2xl border border-slate-800 bg-slate-900/60">

          <div className="flex flex-wrap items-center justify-between gap-3 px-5 py-4">

            <button
              type="button"
              onClick={() =>
                setIntakeExpanded(
                  (current) => !current
                )
              }
              className="flex items-center gap-3 text-left"
            >
              <div>
                <div className="text-sm font-semibold text-white">
                  CSV Intake Inventory
                </div>

                <div className="mt-1 text-xs text-slate-500">
                  Filter and select promoted CSVs for downstream Header & Schema Mapping.
                </div>
              </div>

              <span className="text-sm text-slate-400">
                {intakeExpanded
                  ? "Collapse ▲"
                  : "Expand ▼"}
              </span>
            </button>

            <div className="text-sm text-slate-300">
              Ready:{" "}
              <span className="font-semibold text-sky-400">
                {availableDocuments.length}
              </span>
              {" • "}
              Selected:{" "}
              <span className="font-semibold text-sky-400">
                {selectedCount}
              </span>
            </div>

          </div>


          {intakeExpanded ? (

            <div className="border-t border-slate-800 p-5">

              <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">

                <div>
                  <label className="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-500">
                    Classification
                  </label>

                  <select
                    value={classificationFilter}
                    onChange={(event) =>
                      setClassificationFilter(
                        event.target.value as
                          | "all"
                          | "hit"
                          | "no_hit"
                      )
                    }
                    className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200"
                  >
                    <option value="all">
                      All Files
                    </option>

                    <option value="hit">
                      HIT
                    </option>

                    <option value="no_hit">
                      No Hit
                    </option>
                  </select>
                </div>


                <div>
                  <label className="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-500">
                    Detected Entity
                  </label>

                  <select
                    value={entityTypeFilter}
                    onChange={(event) =>
                      setEntityTypeFilter(
                        event.target.value
                      )
                    }
                    className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200"
                  >
                    <option value="all">
                      All Entity Types
                    </option>

                    {entityTypeOptions.map(
                      (entityType) => (
                        <option
                          key={entityType}
                          value={entityType}
                        >
                          {entityType}
                        </option>
                      )
                    )}
                  </select>
                </div>


                <div>
                  <label className="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-500">
                    Workbook / Source
                  </label>

                  <select
                    value={workbookFilter}
                    onChange={(event) =>
                      setWorkbookFilter(
                        event.target.value
                      )
                    }
                    className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200"
                  >
                    <option value="all">
                      All Workbooks
                    </option>

                    {workbookOptions.map(
                      (workbook) => (
                        <option
                          key={workbook}
                          value={workbook}
                        >
                          {workbook}
                        </option>
                      )
                    )}
                  </select>
                </div>


                <div>
                  <label className="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-500">
                    Search
                  </label>

                  <input
                    type="text"
                    value={searchText}
                    onChange={(event) =>
                      setSearchText(
                        event.target.value
                      )
                    }
                    placeholder="Doc ID, sheet, path..."
                    className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200 placeholder:text-slate-600"
                  />
                </div>

              </div>


              <div className="mt-4 flex flex-wrap items-center gap-2">

                <button
                  type="button"
                  onClick={selectAllFiltered}
                  disabled={
                    filteredDocuments.length === 0
                  }
                  className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200 transition hover:bg-slate-800 disabled:opacity-40"
                >
                  Select All Filtered
                </button>

                <button
                  type="button"
                  onClick={clearSelection}
                  disabled={
                    selectedCount === 0
                  }
                  className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200 transition hover:bg-slate-800 disabled:opacity-40"
                >
                  Clear Selection
                </button>

                <div className="ml-auto text-xs text-slate-500">
                  Showing{" "}
                  <span className="text-slate-300">
                    {filteredDocuments.length}
                  </span>{" "}
                  of{" "}
                  <span className="text-slate-300">
                    {availableDocuments.length}
                  </span>{" "}
                  CSVs
                </div>

                <button
                  type="button"
                  onClick={createHeaderSet}
                  disabled={
                    selectedCount === 0 ||
                    creatingHeaderSet
                  }
                  className="rounded-lg bg-sky-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-sky-500 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  {creatingHeaderSet
                    ? "Creating..."
                    : `Create Header Set${
                        selectedCount
                          ? ` (${selectedCount})`
                          : ""
                      }`}
                </button>

              </div>


              {headerSetMessage ? (
                <div className="mt-3 rounded-lg border border-emerald-900/60 bg-emerald-950/20 px-4 py-3 text-sm text-emerald-300">
                  {headerSetMessage}
                </div>
              ) : null}


              {loading ? (

                <div className="mt-5 rounded-xl border border-slate-800 bg-slate-950/40 px-6 py-16 text-center text-slate-400">
                  Loading Cyber² Intake...
                </div>

              ) : availableDocuments.length === 0 ? (

                <div className="mt-5 rounded-xl border border-dashed border-slate-700 bg-slate-950/30 px-6 py-16 text-center">

                  <FileSpreadsheet className="mx-auto mb-4 h-8 w-8 text-slate-600" />

                  <div className="text-base font-medium text-slate-300">
                    No CSVs are currently ready for Header Set creation.
                  </div>

                  <p className="mx-auto mt-2 max-w-2xl text-sm leading-6 text-slate-500">
                    All current Cyber² Intake CSVs may already be assigned to Header Sets.
                    New promoted spreadsheet or CSV documents will appear here when available.
                  </p>

                </div>

              ) : (

                <div className="mt-5 overflow-hidden rounded-xl border border-slate-800 bg-slate-950/30">

                  <div className="max-h-[700px] overflow-auto">

                    <table className="min-w-[1300px] w-full text-sm">

                      <thead className="sticky top-0 z-20 bg-slate-950 text-left text-[11px] uppercase tracking-wide text-slate-500">
                        <tr>

                          <th className="w-12 px-4 py-3">
                            Select
                          </th>

                          <th className="px-4 py-3">
                            Doc ID
                          </th>

                          <th className="px-4 py-3">
                            Classification
                          </th>

                          <th className="px-4 py-3">
                            Workbook / Source
                          </th>

                          <th className="px-4 py-3">
                            Worksheet
                          </th>

                          <th className="px-4 py-3">
                            Visibility
                          </th>

                          <th className="px-4 py-3">
                            Detected Types
                          </th>

                          <th className="px-4 py-3">
                            Status
                          </th>

                          <th className="px-4 py-3">
                            Source CSV
                          </th>

                        </tr>
                      </thead>


                      <tbody className="divide-y divide-slate-800">

                        {filteredDocuments.map(
                          (doc) => (

                            <tr
                              key={doc.doc_id}
                              className="bg-slate-950/20 hover:bg-slate-900/70"
                            >

                              <td className="px-4 py-3">
                                <input
                                  type="checkbox"
                                  checked={
                                    Boolean(
                                      selectedDocIds[
                                        doc.doc_id
                                      ]
                                    )
                                  }
                                  onChange={(event) =>
                                    toggleDocument(
                                      doc.doc_id,
                                      event.target.checked
                                    )
                                  }
                                  className="h-4 w-4 rounded border-slate-600 bg-slate-950"
                                />
                              </td>


                              <td className="whitespace-nowrap px-4 py-3 font-mono text-xs">
                                <button
                                  type="button"
                                  onClick={() =>
                                    openDocument(
                                      doc
                                    )
                                  }
                                  className="text-sky-400 underline transition-colors hover:text-sky-300"
                                  title="Open in Review"
                                >
                                  {doc.doc_id}
                                </button>
                              </td>


                              <td className="whitespace-nowrap px-4 py-3">
                                {normalizeClassification(
                                  doc.classification
                                ) === "HIT" ? (
                                  <span className="rounded-md border border-emerald-700/70 bg-emerald-950/40 px-2 py-1 text-xs font-semibold text-emerald-300">
                                    HIT
                                  </span>
                                ) : (
                                  <span className="rounded-md border border-slate-700 bg-slate-900 px-2 py-1 text-xs font-medium text-slate-400">
                                    No Hit
                                  </span>
                                )}
                              </td>


                              <td className="max-w-[320px] px-4 py-3 text-slate-200">
                                <div className="truncate">
                                  {doc.original_workbook_name ||
                                    doc.original_filename ||
                                    "—"}
                                </div>
                              </td>


                              <td className="whitespace-nowrap px-4 py-3 text-slate-300">
                                {doc.sheet_index
                                  ? `Sheet ${doc.sheet_index} - `
                                  : ""}

                                {doc.sheet_name ||
                                  "—"}
                              </td>


                              <td className="px-4 py-3 text-slate-400">
                                {doc.sheet_visibility ||
                                  "—"}
                              </td>


                              <td className="max-w-[400px] px-4 py-3">

                                <div className="flex flex-wrap gap-1.5">

                                  {(
                                    doc.entity_types ||
                                    []
                                  ).map(
                                    (
                                      entityType
                                    ) => (
                                      <span
                                        key={
                                          entityType
                                        }
                                        className="rounded-md border border-slate-700 bg-slate-900 px-2 py-1 text-[11px] text-slate-300"
                                      >
                                        {
                                          entityType
                                        }
                                      </span>
                                    )
                                  )}

                                </div>

                              </td>


                              <td className="px-4 py-3">
                                <span className="text-xs font-medium text-emerald-300">
                                  Ready
                                </span>
                              </td>


                              <td
                                className="max-w-[420px] px-4 py-3"
                                title={
                                  doc.source_csv_path ||
                                  ""
                                }
                              >
                                <div className="truncate font-mono text-[11px] text-slate-500">
                                  {doc.source_csv_path ||
                                    "—"}
                                </div>
                              </td>

                            </tr>
                          )
                        )}

                      </tbody>

                    </table>

                  </div>

                </div>

              )}

            </div>

          ) : null}

        </div>

        <div className="mt-6 rounded-2xl border border-slate-800 bg-slate-900/60 p-5">

          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">

            <div>
              <div className="text-sm font-semibold text-white">
                Sent to Header & Schema Mapping
              </div>

              <div className="mt-1 text-xs text-slate-500">
                CSVs already assigned to Header Sets are grouped below and removed from the active Intake inventory.
              </div>
            </div>

            <div className="text-xs text-slate-500">
              {
                filteredSentToHeaderDocuments.length
              }{" "}
              CSVs in{" "}
              {
                sentHeaderSets.length
              }{" "}
              Header Sets
            </div>

          </div>


          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">

            <div>
              <label className="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-500">
                Classification
              </label>

              <select
                value={
                  sentClassificationFilter
                }
                onChange={(event) =>
                  setSentClassificationFilter(
                    event.target.value as
                      | "all"
                      | "hit"
                      | "no_hit"
                  )
                }
                className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200"
              >
                <option value="all">
                  All Files
                </option>

                <option value="hit">
                  HIT
                </option>

                <option value="no_hit">
                  No Hit
                </option>
              </select>
            </div>


            <div>
              <label className="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-500">
                Detected Entity
              </label>

              <select
                value={
                  sentEntityTypeFilter
                }
                onChange={(event) =>
                  setSentEntityTypeFilter(
                    event.target.value
                  )
                }
                className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200"
              >
                <option value="all">
                  All Entity Types
                </option>

                {entityTypeOptions.map(
                  (entityType) => (
                    <option
                      key={entityType}
                      value={entityType}
                    >
                      {entityType}
                    </option>
                  )
                )}
              </select>
            </div>


            <div>
              <label className="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-500">
                Workbook / Source
              </label>

              <select
                value={
                  sentWorkbookFilter
                }
                onChange={(event) =>
                  setSentWorkbookFilter(
                    event.target.value
                  )
                }
                className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200"
              >
                <option value="all">
                  All Workbooks
                </option>

                {workbookOptions.map(
                  (workbook) => (
                    <option
                      key={workbook}
                      value={workbook}
                    >
                      {workbook}
                    </option>
                  )
                )}
              </select>
            </div>


            <div>
              <label className="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-500">
                Search
              </label>

              <input
                type="text"
                value={sentSearchText}
                onChange={(event) =>
                  setSentSearchText(
                    event.target.value
                  )
                }
                placeholder="Header Set, Doc ID, sheet..."
                className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200 placeholder:text-slate-600"
              />
            </div>

          </div>


          <div className="mt-5 space-y-3">

            {sentHeaderSets.length ===
            0 ? (

              <div className="rounded-xl border border-dashed border-slate-700 px-5 py-8 text-center text-sm text-slate-500">
                No CSVs have been sent to Header & Schema Mapping.
              </div>

            ) : (

              sentHeaderSets.map(
                ({
                  headerSetId,
                  docs,
                  sentAt,
                }) => {

                  const expanded =
                    Boolean(
                      expandedHeaderSets[
                        headerSetId
                      ]
                    );

                  return (
                    <div
                      key={headerSetId}
                      className="overflow-hidden rounded-xl border border-slate-800 bg-slate-950/60"
                    >

                      <button
                        type="button"
                        onClick={() =>
                          toggleHeaderSet(
                            headerSetId
                          )
                        }
                        className="flex w-full items-center justify-between gap-4 px-5 py-4 text-left hover:bg-slate-900"
                      >
                        <div>

                          <div className="font-mono text-sm font-semibold text-sky-400">
                            {headerSetId}
                          </div>

                          <div className="mt-1 text-xs text-slate-500">
                            {docs.length} CSV
                            {docs.length === 1
                              ? ""
                              : "s"}
                            {" • "}
                            {
                              docs[0]
                                ?.header_set_status ||
                              "assigned"
                            }
                            {sentAt
                              ? ` • ${new Date(
                                  sentAt
                                ).toLocaleString()}`
                              : ""}
                          </div>

                        </div>

                        <div className="text-sm text-slate-400">
                          {expanded
                            ? "Collapse ▲"
                            : "Expand ▼"}
                        </div>
                      </button>


                      {expanded ? (

                        <div className="overflow-x-auto border-t border-slate-800">

                          <table className="w-full min-w-[1100px] text-sm">

                            <thead className="bg-slate-950 text-left text-[11px] uppercase tracking-wide text-slate-500">
                              <tr>
                                <th className="px-4 py-3">
                                  Doc ID
                                </th>

                                <th className="px-4 py-3">
                                  Classification
                                </th>

                                <th className="px-4 py-3">
                                  Workbook / Source
                                </th>

                                <th className="px-4 py-3">
                                  Worksheet
                                </th>

                                <th className="px-4 py-3">
                                  Visibility
                                </th>

                                <th className="px-4 py-3">
                                  Detected Types
                                </th>

                                <th className="px-4 py-3">
                                  Status
                                </th>

                                <th className="px-4 py-3 text-right">
                                  Action
                                </th>
                              </tr>
                            </thead>


                            <tbody className="divide-y divide-slate-800">

                              {docs.map(
                                (doc) => (
                                  <tr
                                    key={doc.doc_id}
                                    className="hover:bg-slate-900/70"
                                  >

                                    <td className="px-4 py-3 font-mono text-xs text-sky-400">
                                      {
                                        doc.doc_id
                                      }
                                    </td>

                                    <td className="px-4 py-3 text-emerald-300">
                                      {
                                        doc.classification ||
                                        "—"
                                      }
                                    </td>

                                    <td className="px-4 py-3 text-slate-300">
                                      {
                                        doc.original_workbook_name ||
                                        doc.original_filename ||
                                        "—"
                                      }
                                    </td>

                                    <td className="px-4 py-3 text-slate-400">
                                      {
                                        doc.sheet_name ||
                                        "—"
                                      }
                                    </td>

                                    <td className="px-4 py-3 text-slate-400">
                                      {
                                        doc.sheet_visibility ||
                                        "—"
                                      }
                                    </td>

                                    <td className="px-4 py-3">

                                      <div className="flex flex-wrap gap-1">

                                        {(
                                          doc.entity_types ||
                                          []
                                        ).map(
                                          (
                                            entityType
                                          ) => (
                                            <span
                                              key={
                                                entityType
                                              }
                                              className="rounded-md border border-violet-900 bg-violet-950/30 px-2 py-1 text-[11px] text-violet-300"
                                            >
                                              {
                                                entityType
                                              }
                                            </span>
                                          )
                                        )}

                                      </div>

                                    </td>

                                    <td className="px-4 py-3 text-slate-400">
                                      {
                                        doc.header_set_status ||
                                        "assigned"
                                      }
                                    </td>

                                    <td className="px-4 py-3 text-right">

                                      <button
                                        type="button"
                                        onClick={() =>
                                          openDocument(
                                            doc
                                          )
                                        }
                                        className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-xs font-semibold text-slate-200 hover:bg-slate-800"
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

                      ) : null}

                    </div>
                  );
                }
              )

            )}

          </div>

        </div>

      </PageContainer>
    </AppShell>
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

      <div className="mt-2 text-xl font-semibold text-white">
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
          Loading Cyber² Intake...
        </div>
      }
    >
      <Cyber2IntakeContent />
    </Suspense>
  );
}