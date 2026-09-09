"use client";

import {
  Suspense,
  useEffect,
  useState,
} from "react";

import {
  useRouter,
  useSearchParams,
} from "next/navigation";

import AppShell from "../../../components/AppShell";
import PageContainer from "../../../components/PageContainer";
import PageHeader from "../../../components/PageHeader";
import { apiGet } from "../../../lib/api";
import CyberUtilityWorkflowNav from "../../../components/CyberUtilityWorkflowNav";


type HeaderSetDocument = {
  doc_id: string;

  source_csv_path?: string;

  classification?: string;

  entity_types?: string[];

  original_filename?: string;

  original_workbook_name?: string;

  sheet_name?: string;

  sheet_index?: number | null;

  sheet_visibility?: string;

  header_status?: string;

  header_confidence?: number | null;
};


type HeaderSet = {
  header_set_id: string;

  workspace?: string;

  client?: string;

  project?: string;

  status?: string;

  created_at?: string;

  completed_at?: string;

  created_by?: string;

  document_count?: number;

  doc_ids?: string[];

  documents?: HeaderSetDocument[];

  header_set_path?: string;

  last_modified?: string;
};


type HeaderSetsResponse = {
  workspace?: string;

  client?: string;

  project?: string;

  header_set_count?: number;

  header_sets?: HeaderSet[];

  header_sets_prefix?: string;
};


function SchemaMappingPageContent() {
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


  const [
    data,
    setData,
  ] =
    useState<HeaderSetsResponse | null>(
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


  async function loadHeaderSets() {
    if (
      !client ||
      !project
    ) {
      return;
    }

    setLoading(true);

    setError("");

    try {
      const params =
        new URLSearchParams();

      params.set(
        "client",
        client
      );

      params.set(
        "project",
        project
      );

      const response =
        await apiGet(
          `/api/${encodeURIComponent(
            workspace
          )}/cyber2/header-sets?${params.toString()}`
        );

      setData(
        response
      );

    } catch (err: any) {
      console.error(
        "Failed to load Cyber² Header Sets:",
        err
      );

      setError(
        err?.message ||
        "Unable to load Header Sets."
      );

    } finally {
      setLoading(false);
    }
  }


  useEffect(() => {
    loadHeaderSets();
  }, [
    workspace,
    client,
    project,
  ]);


  const headerSets =
    data?.header_sets ||
    [];

  const completedHeaderSets =
    headerSets.filter(
      (headerSet) =>
        String(
          headerSet.status || ""
        )
          .trim()
          .toLowerCase() ===
        "completed"
    );

  const activeHeaderSets =
    headerSets.filter(
      (headerSet) =>
        String(
          headerSet.status || ""
        )
          .trim()
          .toLowerCase() !==
        "completed"
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


  function returnToCyber2Landing() {
    const params =
      buildProjectParams();

    router.push(
      `/cyber-utility?${params.toString()}`
    );
  }


  function returnToIntake() {
    const params =
      buildProjectParams();

    router.push(
      `/cyber-utility/intake?${params.toString()}`
    );
  }


  function formatStatus(
    value?: string
  ) {
    const normalized =
      String(
        value ||
        "pending_header_identification"
      )
        .trim()
        .toLowerCase();

    if (
      normalized ===
        "pending_header_identification" ||
      normalized ===
        "header_identification_complete"
    ) {
      return "Needs Review";
    }

    if (
      normalized ===
      "schema_mapping_approved"
    ) {
      return "Approved";
    }

    if (
      normalized ===
      "completed"
    ) {
      return "Completed";
    }

    const clean =
      normalized
        .replaceAll(
          "_",
          " "
        )
        .trim();

    return clean.replace(
      /\b\w/g,
      (character) =>
        character.toUpperCase()
    );
  }


  function formatDate(
    value?: string
  ) {
    if (!value) {
      return "—";
    }

    const date =
      new Date(value);

    if (
      Number.isNaN(
        date.getTime()
      )
    ) {
      return value;
    }

    return date.toLocaleString();
  }


  return (
    <AppShell>

      <PageContainer>
        <CyberUtilityWorkflowNav />

        <div className="mb-4 flex flex-wrap gap-2">

          <button
            type="button"
            onClick={
              returnToCyber2Landing
            }
            className="rounded-lg border border-slate-700 bg-slate-900 px-4 py-2 text-sm font-medium text-slate-200 transition hover:bg-slate-800"
          >
            ← Return to Cyber² Landing
          </button>


          <button
            type="button"
            onClick={
              returnToIntake
            }
            className="rounded-lg border border-slate-700 bg-slate-900 px-4 py-2 text-sm font-medium text-slate-200 transition hover:bg-slate-800"
          >
            ← Return to Intake & Preparation
          </button>

        </div>


        <PageHeader
          title="Header & Schema Mapping"
          subtitle="Review Header Sets created from Cyber² Intake and prepare structured datasets for header identification and schema mapping."
        />


        <div className="mt-6 grid gap-4 md:grid-cols-4">

          <MetricCard
            label="Header Sets"
            value={String(
              data?.header_set_count ??
              headerSets.length
            )}
          />

          <MetricCard
            label="Workspace"
            value={
              workspace
            }
          />

          <MetricCard
            label="Client"
            value={
              client ||
              "—"
            }
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


        <div className="mt-6 rounded-xl border border-sky-900/60 bg-sky-950/20 px-5 py-4">

          <div className="text-sm font-semibold text-sky-200">
            Source-Preserving Header Workflow
          </div>

          <p className="mt-1 text-sm leading-6 text-slate-400">
            Header Sets reference the staged CSV files selected in
            Cyber² Intake. Creating or reviewing a Header Set does not
            move, rename, overwrite, or alter the source CSV.
          </p>

        </div>


        <div className="mt-6 flex items-center justify-between gap-4">

          <div>

            <h2 className="text-lg font-semibold text-white">
              Header Sets - Needs Review
            </h2>

            <p className="mt-1 text-sm text-slate-500">
              Review Header Sets requiring header identification,
              schema mapping, mapped CSV generation, or Raw Capture.
            </p>

          </div>


          <button
            type="button"
            onClick={
              loadHeaderSets
            }
            disabled={
              loading
            }
            className="rounded-lg border border-slate-700 bg-slate-900 px-4 py-2 text-sm font-medium text-slate-200 transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {loading
              ? "Refreshing..."
              : "Refresh Header Sets"}
          </button>

        </div>


        {error ? (
          <div className="mt-5 rounded-xl border border-red-900/70 bg-red-950/30 px-4 py-3 text-sm text-red-300">
            {error}
          </div>
        ) : null}


        <div className="mt-4">

          {loading &&
          headerSets.length === 0 ? (

            <div className="rounded-2xl border border-slate-800 bg-slate-900/60 px-6 py-14 text-center text-sm text-slate-400">
              Loading Header Sets...
            </div>

          ) : headerSets.length === 0 ? (

            <div className="rounded-2xl border border-dashed border-slate-700 bg-slate-900/40 px-6 py-14 text-center">

              <div className="text-base font-medium text-slate-300">
                No Header Sets Found
              </div>

              <p className="mx-auto mt-2 max-w-2xl text-sm leading-6 text-slate-500">
                Return to Cyber² Intake & Preparation, select one or
                more CSVs, and choose Create Header Set.
              </p>

            </div>

          ) : (

            <div className="overflow-hidden rounded-2xl border border-slate-800 bg-slate-900/60">

              <div className="max-h-[650px] overflow-auto">

                <table className="w-full min-w-[1050px] text-sm">

                  <thead className="sticky top-0 z-10 bg-slate-950 text-left text-[11px] uppercase tracking-wide text-slate-500">

                    <tr>

                      <th className="px-4 py-3">
                        Header Set ID
                      </th>

                      <th className="px-4 py-3">
                        Files
                      </th>

                      <th className="px-4 py-3">
                        Status
                      </th>

                      <th className="px-4 py-3">
                        Created
                      </th>

                      <th className="px-4 py-3">
                        Created By
                      </th>

                      <th className="px-4 py-3">
                        Manifest
                      </th>

                      <th className="px-4 py-3 text-right">
                        Action
                      </th>

                    </tr>

                  </thead>


                  <tbody className="divide-y divide-slate-800">

                    {activeHeaderSets.map(
                      (headerSet) => (

                        <tr
                          key={
                            headerSet.header_set_id
                          }
                          className="bg-slate-950/20 hover:bg-slate-900/70"
                        >

                          <td className="whitespace-nowrap px-4 py-3 font-mono text-xs font-semibold text-sky-400">
                            {
                              headerSet.header_set_id
                            }
                          </td>


                          <td className="px-4 py-3 text-slate-200">
                            {
                              headerSet.document_count ??
                              headerSet.documents?.length ??
                              0
                            }
                          </td>


                          <td className="px-4 py-3">

                            <span className="whitespace-nowrap rounded-md border border-amber-800/70 bg-amber-950/30 px-2 py-1 text-xs font-medium text-amber-300">
                              {formatStatus(
                                headerSet.status
                              )}
                            </span>

                          </td>


                          <td className="whitespace-nowrap px-4 py-3 text-xs text-slate-400">
                            {formatDate(
                              headerSet.created_at ||
                              headerSet.last_modified
                            )}
                          </td>


                          <td className="px-4 py-3 text-slate-400">
                            {
                              headerSet.created_by ||
                              "—"
                            }
                          </td>


                          <td
                            className="max-w-[340px] px-4 py-3"
                            title={
                              headerSet.header_set_path ||
                              ""
                            }
                          >

                            <div className="truncate font-mono text-[11px] text-slate-500">
                              {
                                headerSet.header_set_path ||
                                "—"
                              }
                            </div>

                          </td>


                          <td className="whitespace-nowrap px-4 py-3 text-right">

                            <button
                              type="button"
                              onClick={() => {
                                const params =
                                  new URLSearchParams();

                                params.set(
                                  "workspace",
                                  workspace
                                );

                                params.set(
                                  "client",
                                  client
                                );

                                params.set(
                                  "project",
                                  project
                                );

                                params.set(
                                  "header_set",
                                  headerSet.header_set_id
                                );

                                router.push(
                                  `/cyber-utility/schema-mapping/set?${params.toString()}`
                                );
                              }}
                              className="rounded-lg bg-sky-600 px-4 py-2 text-xs font-semibold text-white transition hover:bg-sky-500"
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

            </div>

          )}

        </div>

        <div className="mt-8">

          <div className="mb-4">

            <h2 className="text-lg font-semibold text-white">
              Completed
            </h2>

            <p className="mt-1 text-sm text-slate-500">
              Header Sets that completed mapping, mapped CSV
              generation, and Raw Capture. Reopen a completed
              set if header changes are required.
            </p>

          </div>

          {completedHeaderSets.length === 0 ? (

            <div className="rounded-2xl border border-dashed border-slate-700 bg-slate-900/40 px-6 py-10 text-center text-sm text-slate-500">
              No completed Header Sets.
            </div>

          ) : (

            <div className="overflow-hidden rounded-2xl border border-emerald-900/60 bg-slate-900/60">

              <div className="max-h-[500px] overflow-auto">

                <table className="w-full min-w-[1050px] text-sm">

                  <thead className="sticky top-0 z-10 bg-slate-950 text-left text-[11px] uppercase tracking-wide text-slate-500">

                    <tr>

                      <th className="px-4 py-3">
                        Header Set ID
                      </th>

                      <th className="px-4 py-3">
                        Files
                      </th>

                      <th className="px-4 py-3">
                        Status
                      </th>

                      <th className="px-4 py-3">
                        Completed
                      </th>

                      <th className="px-4 py-3">
                        Created By
                      </th>

                      <th className="px-4 py-3">
                        Manifest
                      </th>

                      <th className="px-4 py-3 text-right">
                        Action
                      </th>

                    </tr>

                  </thead>

                  <tbody className="divide-y divide-slate-800">

                    {completedHeaderSets.map(
                      (headerSet) => (

                        <tr
                          key={
                            headerSet.header_set_id
                          }
                          className="bg-emerald-950/10 hover:bg-slate-900/70"
                        >

                          <td className="whitespace-nowrap px-4 py-3 font-mono text-xs font-semibold text-emerald-300">
                            {
                              headerSet.header_set_id
                            }
                          </td>

                          <td className="px-4 py-3 text-slate-200">
                            {
                              headerSet.document_count ??
                              headerSet.documents?.length ??
                              0
                            }
                          </td>

                          <td className="px-4 py-3">

                            <span className="whitespace-nowrap rounded-md border border-emerald-800/70 bg-emerald-950/30 px-2 py-1 text-xs font-medium text-emerald-300">
                              Completed
                            </span>

                          </td>

                          <td className="whitespace-nowrap px-4 py-3 text-xs text-slate-400">
                            {formatDate(
                              headerSet.completed_at ||
                              headerSet.last_modified
                            )}
                          </td>

                          <td className="px-4 py-3 text-slate-400">
                            {
                              headerSet.created_by ||
                              "—"
                            }
                          </td>

                          <td
                            className="max-w-[340px] px-4 py-3"
                            title={
                              headerSet.header_set_path ||
                              ""
                            }
                          >

                            <div className="truncate font-mono text-[11px] text-slate-500">
                              {
                                headerSet.header_set_path ||
                                "—"
                              }
                            </div>

                          </td>

                          <td className="whitespace-nowrap px-4 py-3 text-right">

                            <button
                              type="button"
                              onClick={() => {
                                const params =
                                  new URLSearchParams();

                                params.set(
                                  "workspace",
                                  workspace
                                );

                                params.set(
                                  "client",
                                  client
                                );

                                params.set(
                                  "project",
                                  project
                                );

                                params.set(
                                  "header_set",
                                  headerSet.header_set_id
                                );

                                router.push(
                                  `/cyber-utility/schema-mapping/set?${params.toString()}`
                                );
                              }}
                              className="rounded-lg border border-emerald-700 bg-emerald-950/40 px-4 py-2 text-xs font-semibold text-emerald-200 transition hover:bg-emerald-900/60"
                            >
                              Reopen Mapping
                            </button>

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
    <div className="rounded-2xl border border-slate-800 bg-slate-900/70 px-5 py-4">

      <div className="text-[11px] uppercase tracking-[0.16em] text-slate-500">
        {label}
      </div>

      <div className="mt-2 truncate text-lg font-semibold text-white">
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
      <SchemaMappingPageContent />
    </Suspense>
  );
}