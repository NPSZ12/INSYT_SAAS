"use client";

import {
  Suspense,
  useEffect,
  useState,
} from "react";

import {
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
import { apiGet } from "../../../lib/api";

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

  return (
    <AppShell>
      <PageContainer>

        <div className="mb-6 flex flex-wrap items-start justify-between gap-4">

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


        <div className="mb-6 grid gap-4 md:grid-cols-4">

          <MetricCard
            label="Files Ready"
            value={String(
              intakeData?.intake_count ??
                documents.length
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


        {error ? (
          <div className="mb-6 rounded-xl border border-red-900 bg-red-950/30 px-4 py-3 text-sm text-red-300">
            {error}
          </div>
        ) : null}


        {loading ? (

          <div className="rounded-2xl border border-slate-800 bg-slate-900/60 px-6 py-16 text-center text-slate-400">
            Loading Cyber² Intake...
          </div>

        ) : documents.length === 0 ? (

          <div className="rounded-2xl border border-dashed border-slate-700 bg-slate-900/40 px-6 py-16 text-center">

            <FileSpreadsheet className="mx-auto mb-4 h-8 w-8 text-slate-600" />

            <div className="text-base font-medium text-slate-300">
              No files have been sent to Cyber².
            </div>

            <p className="mx-auto mt-2 max-w-2xl text-sm leading-6 text-slate-500">
              Responsive spreadsheet or CSV documents will appear
              here after they are sent from Processing Center -
              Promotion.
            </p>

          </div>

        ) : (

          <div className="overflow-hidden rounded-2xl border border-slate-800 bg-slate-900/60">

            <div className="max-h-[700px] overflow-auto">

              <table className="min-w-[1300px] w-full text-sm">

                <thead className="sticky top-0 z-20 bg-slate-950 text-left text-[11px] uppercase tracking-wide text-slate-500">

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

                  {documents.map(
                    (doc) => (

                      <tr
                        key={doc.doc_id}
                        className="bg-slate-950/20 hover:bg-slate-900/70"
                      >

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