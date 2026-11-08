"use client";

import {
  Suspense,
  useEffect,
  useState,
} from "react";
import { useSearchParams } from "next/navigation";

import AppShell from "../../../components/AppShell";
import PageContainer from "../../../components/PageContainer";
import PageHeader from "../../../components/PageHeader";
import ContentCard from "../../../components/ContentCard";
import CyberUtilityWorkflowNav from "../../../components/CyberUtilityWorkflowNav";
import { apiGet, apiPost } from "../../../lib/api";
import ExactMatchSpreadsheetModal, {
  type SpreadsheetPreview,
} from "../../../components/cyber2/ExactMatchSpreadsheetModal";
import CompletedMergeSetsPanel from "../../../components/cyber2/CompletedMergeSetsPanel";

type HeaderSet = {
  header_set_id: string;
  status?: string;
  document_count?: number;
  documents?: { doc_id: string }[];
  created_at?: string;
};

type MappingResponse = {
  approved_mapping_exists?: boolean;
  approved_mapping?: {
    status?: string;
    header_set_id?: string;
    canonical_column_order?: string[];
    protocol_headers?: string[];
  };
};

type Member = {
  ucid: string;
  doc_id: string;
};

type Group = {
  member_count: number;
  members: Member[];
  conflict_fields?: string[];
  reason?: string;
};

type Preview = {
  status: string;
  header_set_id: string;
  merge_index: string[];
  document_count: number;
  raw_record_count: number;
  duplicate_group_count: number;
  duplicate_record_count: number;
  working_record_count: number;
  conflict_group_count: number;
  groups: Group[];
  conflicts: Group[];
  unmatched: Member[];
  excluded: (Member & { reason: string })[];
  execution_enabled: boolean;
};

function errorMessage(reason: unknown): string {
  return reason instanceof Error
    ? reason.message
    : "The requested Cyber² operation failed.";
}

function MergeDedupeContent() {
  const params = useSearchParams();

  const workspace =
    params.get("workspace") === "discovery"
      ? "discovery"
      : "capture";

  const client = params.get("client") || "";
  const project = params.get("project") || "";

  const [sets, setSets] = useState<HeaderSet[]>([]);
  const [selectedSet, setSelectedSet] = useState("");
  const [headers, setHeaders] = useState<string[]>([]);
  const [mergeIndex, setMergeIndex] = useState<string[]>([]);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [spreadsheet, setSpreadsheet] =
    useState<SpreadsheetPreview | null>(null);
  const [showSpreadsheet, setShowSpreadsheet] = useState(false);
  const [executionRequestId, setExecutionRequestId] = useState("");
  const [executing, setExecuting] = useState(false);
  const [executionError, setExecutionError] = useState("");
  const [savedMergeSetId, setSavedMergeSetId] = useState("");
  const [completedRefresh, setCompletedRefresh] = useState(0);

  const [loadingSets, setLoadingSets] = useState(false);
  const [loadingMapping, setLoadingMapping] = useState(false);
  const [previewing, setPreviewing] = useState(false);
  const [error, setError] = useState("");

  const base = `/api/${workspace}/cyber2`;

  useEffect(() => {
    let active = true;

    async function loadSets() {
      setSets([]);
      setSelectedSet("");
      setHeaders([]);
      setMergeIndex([]);
      setPreview(null);
      setSpreadsheet(null);
      setShowSpreadsheet(false);
      setError("");

      if (!client || !project) {
        setError("Select a client and project first.");
        return;
      }

      setLoadingSets(true);

      try {
        const query = new URLSearchParams({ client, project });

        const response = await apiGet(
          `${base}/header-sets?${query.toString()}`
        );

        if (!Array.isArray(response?.header_sets)) {
          throw new Error("Invalid Header Set response.");
        }

        if (active) {
          setSets(response.header_sets);
        }
      } catch (reason) {
        if (active) setError(errorMessage(reason));
      } finally {
        if (active) setLoadingSets(false);
      }
    }

    void loadSets();

    return () => {
      active = false;
    };
  }, [base, client, project]);

  useEffect(() => {
    let active = true;

    async function loadMapping() {
      setHeaders([]);
      setMergeIndex([]);
      setPreview(null);
      setSpreadsheet(null);
      setShowSpreadsheet(false);
      setError("");

      if (!selectedSet) return;

      setLoadingMapping(true);

      try {
        const query = new URLSearchParams({ client, project });

        const response = await apiGet(
          `${base}/header-sets/${encodeURIComponent(
            selectedSet
          )}/mapping?${query.toString()}`
        ) as MappingResponse;

        const approved = response.approved_mapping;

        if (
          !response.approved_mapping_exists ||
          approved?.status !== "approved" ||
          approved.header_set_id !== selectedSet
        ) {
          throw new Error(
            "This Header Set does not have an approved mapping."
          );
        }

        const columns =
          approved.canonical_column_order ||
          approved.protocol_headers ||
          [];

        if (
          !Array.isArray(columns) ||
          !columns.length ||
          columns.some((field) => typeof field !== "string")
        ) {
          throw new Error("Approved protocol headers unavailable.");
        }

        if (active) {
          setHeaders(
            Array.from(
              new Set(columns.filter((field) => field.trim()))
            )
          );
        }
      } catch (reason) {
        if (active) setError(errorMessage(reason));
      } finally {
        if (active) setLoadingMapping(false);
      }
    }

    void loadMapping();

    return () => {
      active = false;
    };
  }, [base, client, project, selectedSet]);

  function toggleHeader(field: string) {
    setPreview(null);
      setSpreadsheet(null);
      setShowSpreadsheet(false);

    setMergeIndex((previous) =>
      previous.includes(field)
        ? previous.filter((item) => item !== field)
        : [...previous, field]
    );
  }

  async function runPreview() {
    if (!selectedSet || !mergeIndex.length || previewing) return;

    setPreview(null);
      setSpreadsheet(null);
      setShowSpreadsheet(false);
    setError("");
    setPreviewing(true);

    try {
      const result = await apiPost(
        `${base}/merge-dedupe/preview`,
        {
          client,
          project,
          header_set_id: selectedSet,
          merge_index: mergeIndex,
        }
      ) as Preview;

      if (
        result.status !== "preview" ||
        result.execution_enabled !== false ||
        result.header_set_id !== selectedSet ||
        !Array.isArray(result.groups) ||
        !Array.isArray(result.conflicts)
      ) {
        throw new Error("Invalid exact-dedupe preview response.");
      }

      const sheet = await apiPost(
        `${base}/merge-dedupe/spreadsheet-preview`,
        {
          client,
          project,
          header_set_id: selectedSet,
          merge_index: mergeIndex,
        }
      ) as SpreadsheetPreview;

      if (
        !/^[0-9a-f]{64}$/.test(sheet.snapshot_fingerprint || "") ||
        sheet.status !== "spreadsheet_preview" ||
        sheet.header_set_id !== selectedSet ||
        sheet.execution_enabled !== false ||
        sheet.preview_rows_complete !== true ||
        !Array.isArray(sheet.preview_columns) ||
        !Array.isArray(sheet.preview_rows) ||
        sheet.preview_row_count !== result.raw_record_count ||
        sheet.preview_rows.length !== result.raw_record_count ||
        new Set(sheet.preview_rows.map((row) => row.ucid)).size !==
          sheet.preview_rows.length ||
        sheet.preview_columns.length === 0 ||
        sheet.preview_columns.some(
          (field) => typeof field !== "string" || !field.trim()
        ) ||
        new Set(
          sheet.preview_columns.map((field) => field.trim().toLowerCase())
        ).size !== sheet.preview_columns.length ||
        sheet.preview_rows.some(
          (row) =>
            !row.cells ||
            typeof row.cells !== "object" ||
            Array.isArray(row.cells) ||
            Object.keys(row.cells).length !== sheet.preview_columns.length ||
            sheet.preview_columns.some(
              (field) => !Object.prototype.hasOwnProperty.call(row.cells, field)
            )
        ) ||
        sheet.preview_rows.some(
          (row) =>
            !row.ucid ||
            !row.doc_id ||
            !row.cells ||
            typeof row.cells !== "object"
        )
      ) {
        throw new Error("Invalid or incomplete spreadsheet preview.");
      }

      setPreview(result);
      setSpreadsheet(sheet);
      setExecutionRequestId(crypto.randomUUID());
      setExecutionError("");
      setShowSpreadsheet(true);
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setPreviewing(false);
    }
  }

  async function runExecute() {
    if (executing) return;

    if (
      !spreadsheet ||
      !executionRequestId ||
      !selectedSet ||
      spreadsheet.header_set_id !== selectedSet ||
      !/^[0-9a-f]{64}$/.test(spreadsheet.snapshot_fingerprint)
    ) {
      setExecutionError("Refresh the spreadsheet before execution.");
      return;
    }

    setExecuting(true);
    setExecutionError("");

    try {
      const receipt = await apiPost(
        `${base}/merge-dedupe/execute`,
        {
          client,
          project,
          header_set_id: selectedSet,
          merge_index: spreadsheet.merge_index,
          snapshot_fingerprint: spreadsheet.snapshot_fingerprint,
          request_id: executionRequestId,
        }
      ) as {
        status?: string;
        merge_set_id?: string;
      };

      if (
        receipt.status !== "completed" ||
        !receipt.merge_set_id?.startsWith("MSET-")
      ) {
        throw new Error("Invalid merge execution receipt.");
      }

      setSavedMergeSetId(receipt.merge_set_id);
      setShowSpreadsheet(false);
      setCompletedRefresh((value) => value + 1);
      setExecutionRequestId("");
    } catch (reason) {
      // Preserve request ID for safe retry.
      setExecutionError(errorMessage(reason));
    } finally {
      setExecuting(false);
    }
  }
  const selectedDetails = sets.find(
    (item) => item.header_set_id === selectedSet
  );

  const busy = loadingSets || loadingMapping || previewing;

  const summary = [
    ["Documents", preview?.document_count],
    ["RAW records", preview?.raw_record_count],
    ["Exact groups", preview?.duplicate_group_count],
    ["Working rows", preview?.working_record_count],
    ["QC conflicts", preview?.conflict_group_count],
  ];

  return (
    <AppShell>
      <PageContainer>
        <CyberUtilityWorkflowNav />

        <PageHeader
          title="Merge & Dedupe"
          subtitle="Exact-match consolidation using approved INSYT protocol headers."
        />

        <div className="mb-5 rounded-xl border border-slate-800 bg-slate-900 p-4">
          <div className="grid gap-4 text-sm md:grid-cols-3">
            <div>
              <div className="text-slate-400">Workspace</div>
              <div className="font-semibold text-white">{workspace}</div>
            </div>
            <div>
              <div className="text-slate-400">Client</div>
              <div className="font-semibold text-white">
                {client || "Not selected"}
              </div>
            </div>
            <div>
              <div className="text-slate-400">Project</div>
              <div className="font-semibold text-sky-300">
                {project || "Not selected"}
              </div>
            </div>
          </div>
        </div>

        {error && (
          <div
            role="alert"
            className="mb-5 rounded-lg border border-rose-700 bg-rose-950/30 p-4 text-sm text-rose-300"
          >
            {error}
          </div>
        )}

        <ContentCard title="1. Select Header Set">
          <p className="mb-3 text-sm text-slate-400">
            Choose a previously mapped set. The set determines which
            source documents are included in exact matching.
          </p>

          <div className="flex flex-wrap gap-3">
            <select
              aria-label="Select Header Set"
              value={selectedSet}
              disabled={loadingSets}
              onChange={(event) => setSelectedSet(event.target.value)}
              className="min-w-[280px] flex-1 rounded-lg border border-slate-700 bg-slate-950 p-3 text-sm text-white"
            >
              <option value="">Select Header Set</option>
              {sets.map((item) => (
                <option
                  key={item.header_set_id}
                  value={item.header_set_id}
                >
                  {item.header_set_id}
                  {" — "}
                  {item.document_count ?? item.documents?.length ?? 0}
                  {" documents"}
                </option>
              ))}
            </select>

            <button
              type="button"
              onClick={() => window.location.reload()}
              disabled={busy}
              className="rounded-lg border border-slate-600 px-4 py-2 text-sm text-white disabled:opacity-50"
            >
              Refresh
            </button>
          </div>

          {selectedDetails && (
            <p className="mt-3 text-xs text-slate-400">
              Selected: {selectedDetails.header_set_id}
              {" | Status: "}
              {selectedDetails.status || "Unknown"}
            </p>
          )}
        </ContentCard>

        <div className="mt-5">
          <ContentCard title="2. Select Merge Index">
            <p className="mb-4 text-sm text-slate-400">
              Select the approved protocol fields that must match
              exactly. Missing values do not qualify for automatic
              grouping. Fuzzy matching occurs later in Entity Normalization.
            </p>

            {loadingMapping && (
              <p className="text-sm text-slate-400">
                Loading approved mapping...
              </p>
            )}

            {!loadingMapping && selectedSet && headers.length === 0 && (
              <p className="text-sm text-amber-300">
                No approved merge headers available for this set.
              </p>
            )}

            <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
              {headers.map((field) => (
                <label
                  key={field}
                  className="flex cursor-pointer items-center gap-3 rounded-lg border border-slate-800 bg-slate-950 p-3 text-sm text-white"
                >
                  <input
                    type="checkbox"
                    checked={mergeIndex.includes(field)}
                    onChange={() => toggleHeader(field)}
                    disabled={busy}
                  />
                  <span>{field}</span>
                </label>
              ))}
            </div>

            <div className="mt-4 text-sm text-slate-300">
              <span className="font-semibold">Selected index: </span>
              {mergeIndex.length
                ? mergeIndex.join(" + ")
                : "Select one or more headers"}
            </div>

            <button
              type="button"
              disabled={
                busy ||
                !selectedSet ||
                mergeIndex.length === 0
              }
              onClick={() => void runPreview()}
              className="mt-4 rounded-lg bg-sky-700 px-5 py-3 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-40"
            >
              {previewing ? "Analyzing..." : "Preview Exact Matches"}
            </button>
          </ContentCard>
        </div>

        <div className="mt-5">
          <ContentCard title="3. Exact-Match Preview">
            {spreadsheet && (
              <button
                type="button"
                onClick={() => setShowSpreadsheet(true)}
                className="mb-4 rounded-lg bg-sky-700 px-4 py-2 text-sm font-semibold text-white"
              >
                Open Full Spreadsheet
              </button>
            )}
            {!preview ? (
              <p className="text-sm text-slate-400">
                Select an approved Header Set and Merge Index,
                then run the read-only preview.
              </p>
            ) : (
              <>
                <div className="mb-5 grid grid-cols-2 gap-3 lg:grid-cols-5">
                  {summary.map(([label, value]) => (
                    <div
                      key={String(label)}
                      className="rounded-lg border border-slate-800 bg-slate-950 p-3"
                    >
                      <div className="text-xs text-slate-400">
                        {label}
                      </div>
                      <div className="mt-1 text-xl font-semibold text-white">
                        {value ?? 0}
                      </div>
                    </div>
                  ))}
                </div>

                <p className="mb-4 text-sm text-slate-400">
                  Duplicate records matched:{" "}
                  {preview.duplicate_record_count}.
                  Unmatched records: {preview.unmatched.length}.
                  Excluded records: {preview.excluded.length}.
                </p>

                <div className="overflow-x-auto rounded-lg border border-slate-800">
                  <table className="w-full text-left text-sm">
                    <thead className="bg-slate-900 text-slate-300">
                      <tr>
                        <th className="p-3">Result</th>
                        <th className="p-3">RAW members</th>
                        <th className="p-3">Source documents</th>
                      </tr>
                    </thead>
                    <tbody>
                      {preview.groups.map((group, index) => (
                        <tr
                          key={`group-${index}`}
                          className="border-t border-slate-800 text-slate-200"
                        >
                          <td className="p-3">
                            Exact group {index + 1}
                          </td>
                          <td className="p-3">
                            {group.member_count}
                          </td>
                          <td className="p-3">
                            {Array.from(
                              new Set(
                                group.members.map((item) => item.doc_id)
                              )
                            ).join(", ")}
                          </td>
                        </tr>
                      ))}

                      {preview.conflicts.map((group, index) => (
                        <tr
                          key={`conflict-${index}`}
                          className="border-t border-slate-800 text-amber-300"
                        >
                          <td className="p-3">
                            QC conflict:{" "}
                            {(group.conflict_fields || []).join(", ")}
                          </td>
                          <td className="p-3">
                            {group.member_count}
                          </td>
                          <td className="p-3">
                            {Array.from(
                              new Set(
                                group.members.map((item) => item.doc_id)
                              )
                            ).join(", ")}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                <p className="mt-4 text-xs text-slate-400">
                  Preview only. No RAW records, memberships, or
                  Azure processing data have been modified.
                </p>
              </>
            )}
          </ContentCard>
        </div>

        <div className="mt-5">
          <ContentCard title="5. Completed Merge Sets">
            {savedMergeSetId && (
              <p role="status" className="mb-3 text-sm text-emerald-300">
                Completed merge set saved: {savedMergeSetId}
              </p>
            )}
            <CompletedMergeSetsPanel
              base={base}
              client={client}
              project={project}
              refreshKey={completedRefresh}
            />
          </ContentCard>
        </div>
      </PageContainer>
      {showSpreadsheet && spreadsheet && (
        <ExactMatchSpreadsheetModal
          data={spreadsheet}
          onClose={() => {
            if (!executing) setShowSpreadsheet(false);
          }}
          onExecute={() => void runExecute()}
          executing={executing}
          executionError={executionError}
        />
      )}
    </AppShell>
  );
}

export default function Page() {
  return (
    <Suspense fallback={<div>Loading Cyber²...</div>}>
      <MergeDedupeContent />
    </Suspense>
  );
}