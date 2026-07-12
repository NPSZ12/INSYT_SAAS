"use client";

import {
  Suspense,
  useEffect,
  useMemo,
  useState,
} from "react";
import { useSearchParams } from "next/navigation";

import AppShell from "../../../../components/AppShell";
import PageContainer from "../../../../components/PageContainer";
import PageHeader from "../../../../components/PageHeader";
import ContentCard from "../../../../components/ContentCard";
import { apiGet, apiPost } from "../../../../lib/api";

type CsvFile = {
  file_name: string;
  blob_path: string;
  size?: string;
  last_modified?: string;
};

type DeduplicationCenterState = {
  workspace: string;
  client: string;
  project: string;
  merged_outputs: CsvFile[];
  completed_inputs: CsvFile[];
  deduped_outputs: CsvFile[];
};

function formatDate(value?: string) {
  if (!value) return "";
  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
}

function getApiBaseUrl() {
  return (
    process.env.NEXT_PUBLIC_API_BASE_URL ||
    process.env.NEXT_PUBLIC_API_URL ||
    "https://api.insyt360.com"
  ).replace(/\/$/, "");
}

function buildApiUrl(path: string) {
  return `${getApiBaseUrl()}${path}`;
}

function fileSizeLabel(value?: string) {
  const size = Number(value || 0);

  if (!size) return "";
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${Math.round(size / 1024)} KB`;

  return `${(size / (1024 * 1024)).toFixed(2)} MB`;
}

function EmptyTableRow({ colSpan, message }: { colSpan: number; message: string }) {
  return (
    <tr>
      <td colSpan={colSpan} className="px-3 py-4 text-center text-sm text-slate-500">
        {message}
      </td>
    </tr>
  );
}

function CsvSelectTable({
  files,
  selected,
  setSelected,
  emptyMessage,
}: {
  files: CsvFile[];
  selected: Record<string, boolean>;
  setSelected: React.Dispatch<React.SetStateAction<Record<string, boolean>>>;
  emptyMessage: string;
}) {
  return (
    <div className="max-h-72 overflow-auto rounded-md border border-slate-800">
      <table className="w-full text-left text-sm">
        <thead className="bg-slate-900 text-slate-300">
          <tr>
            <th className="px-3 py-2"></th>
            <th className="px-3 py-2">File Name</th>
            <th className="px-3 py-2">Blob Path</th>
            <th className="px-3 py-2">Size</th>
            <th className="px-3 py-2">Last Modified</th>
          </tr>
        </thead>

        <tbody>
          {files.length ? (
            files.map((file) => (
              <tr key={file.blob_path} className="border-t border-slate-800">
                <td className="px-3 py-2">
                  <input
                    type="checkbox"
                    checked={!!selected[file.blob_path]}
                    onChange={(event) =>
                      setSelected((current) => ({
                        ...current,
                        [file.blob_path]: event.target.checked,
                      }))
                    }
                  />
                </td>
                <td className="px-3 py-2 text-slate-100">{file.file_name}</td>
                <td className="px-3 py-2 font-mono text-xs text-slate-400">
                  {file.blob_path}
                </td>
                <td className="px-3 py-2 text-slate-300">{fileSizeLabel(file.size)}</td>
                <td className="px-3 py-2 text-slate-300">{formatDate(file.last_modified)}</td>
              </tr>
            ))
          ) : (
            <EmptyTableRow colSpan={5} message={emptyMessage} />
          )}
        </tbody>
      </table>
    </div>
  );
}

function OutputTable({
  files,
  onOpen,
  emptyMessage,
}: {
  files: CsvFile[];
  onOpen: (blobPath: string) => void;
  emptyMessage: string;
}) {
  return (
    <div className="max-h-72 overflow-auto rounded-md border border-slate-800">
      <table className="w-full text-left text-sm">
        <thead className="bg-slate-900 text-slate-300">
          <tr>
            <th className="px-3 py-2">File Name</th>
            <th className="px-3 py-2">Blob Path</th>
            <th className="px-3 py-2">Size</th>
            <th className="px-3 py-2">Last Modified</th>
            <th className="px-3 py-2">Actions</th>
          </tr>
        </thead>

        <tbody>
          {files.length ? (
            files.map((file) => (
              <tr key={file.blob_path} className="border-t border-slate-800">
                <td className="px-3 py-2 text-slate-100">{file.file_name}</td>
                <td className="px-3 py-2 font-mono text-xs text-slate-400">
                  {file.blob_path}
                </td>
                <td className="px-3 py-2 text-slate-300">{fileSizeLabel(file.size)}</td>
                <td className="px-3 py-2 text-slate-300">{formatDate(file.last_modified)}</td>
                <td className="px-3 py-2">
                  <button
                    className="rounded-md bg-slate-800 px-2 py-1 text-xs text-white hover:bg-slate-700"
                    onClick={() => onOpen(file.blob_path)}
                  >
                    Open
                  </button>
                </td>
              </tr>
            ))
          ) : (
            <EmptyTableRow colSpan={5} message={emptyMessage} />
          )}
        </tbody>
      </table>
    </div>
  );
}

function DeduplicationCenterContent() {
  const searchParams = useSearchParams();

  const clientId = searchParams.get("client") || "";
  const projectId = searchParams.get("project") || "";
  const workspace = "capture";

  const [state, setState] = useState<DeduplicationCenterState | null>(null);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [selectedMerged, setSelectedMerged] = useState<Record<string, boolean>>({});
  const [selectedCompletedInputs, setSelectedCompletedInputs] = useState<Record<string, boolean>>({});
  const [dedupeHeaders, setDedupeHeaders] = useState<string[]>([]);
  const [showDedupeModal, setShowDedupeModal] = useState(false);
  const [availableHeaders, setAvailableHeaders] = useState<string[]>([]);
  const [mergeDelimiter, setMergeDelimiter] = useState(" | ");
  const [enableFuzzy, setEnableFuzzy] = useState(false);
  const [fuzzyThreshold, setFuzzyThreshold] = useState(0.85);

  const selectedMergedBlobPaths = useMemo(
    () =>
      Object.entries(selectedMerged)
        .filter(([, value]) => value)
        .map(([blob]) => blob),
    [selectedMerged]
  );

  const selectedCompletedInputBlobPaths = useMemo(
    () =>
      Object.entries(selectedCompletedInputs)
        .filter(([, value]) => value)
        .map(([blob]) => blob),
    [selectedCompletedInputs]
  );

  async function refreshCenter() {
    if (!clientId || !projectId) {
      setState(null);
      setMessage("Select a client and project first.");
      return;
    }

    setBusy(true);
    setMessage("");

    try {
      const data = await apiGet(
        `/api/cyber-utility/xl-processing/deduplication-center?workspace=${encodeURIComponent(
          workspace
        )}&client=${encodeURIComponent(clientId)}&project=${encodeURIComponent(projectId)}`
      );

      setState(data);
    } catch (err: any) {
      setMessage(err?.message || "Failed to load Deduplication Center.");
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    refreshCenter();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clientId, projectId]);

  function toggleAllMerged(selected: boolean) {
    const next: Record<string, boolean> = {};

    for (const file of state?.merged_outputs || []) {
      next[file.blob_path] = selected;
    }

    setSelectedMerged(next);
  }

  function toggleAllCompletedInputs(selected: boolean) {
    const next: Record<string, boolean> = {};

    for (const file of state?.completed_inputs || []) {
      next[file.blob_path] = selected;
    }

    setSelectedCompletedInputs(next);
  }

  async function openDedupeSetup() {
    if (!selectedMergedBlobPaths.length) {
      setMessage("Select one or more merged CSV outputs first.");
      return;
    }

    setBusy(true);
    setMessage("");

    try {
      const firstBlob = selectedMergedBlobPaths[0];

      const data = await apiGet(
        `/api/cyber-utility/xl-processing/csv-headers?workspace=${encodeURIComponent(
          workspace
        )}&client=${encodeURIComponent(clientId)}&project=${encodeURIComponent(
          projectId
        )}&blob_path=${encodeURIComponent(firstBlob)}`
      );

      const headers = Array.isArray(data.headers) ? data.headers : [];

      if (!headers.length) {
        setAvailableHeaders([]);
        setMessage("No headers found in the selected merged CSV.");
        return;
      }

      setAvailableHeaders(headers);
      setDedupeHeaders([]);
      setShowDedupeModal(true);
    } catch (err: any) {
      setAvailableHeaders([]);
      setMessage(err?.message || "Failed to load merged CSV headers.");
    } finally {
      setBusy(false);
    }
  }

  function toggleDedupeHeader(header: string, selected: boolean) {
    setDedupeHeaders((current) => {
      if (selected) {
        return current.includes(header) ? current : [...current, header];
      }

      return current.filter((item) => item !== header);
    });
  }

  async function runDedupe() {
    if (!dedupeHeaders.length) {
      setMessage("Select at least one dedupe header.");
      return;
    }

    const outputName = window.prompt(
      "Output filename for deduped CSV:",
      `DEDUPED_OUTPUT_${new Date()
        .toISOString()
        .slice(0, 19)
        .replace(/[-:T]/g, "")}.csv`
    );

    if (!outputName) return;

    setBusy(true);
    setMessage("");

    try {
      const result = await apiPost("/api/cyber-utility/xl-processing/dedupe-selected", {
        workspace,
        client: clientId,
        project_id: projectId,
        selected_csv_blobs: selectedMergedBlobPaths,
        dedupe_headers: dedupeHeaders,
        merge_delimiter: mergeDelimiter,
        enable_fuzzy: enableFuzzy,
        fuzzy_threshold: fuzzyThreshold,
        output_name: outputName,
      });

      setMessage(
        `${result.message || "Deduplication completed."} Rows In: ${result.rows_in}; Rows Out: ${result.rows_out}`
      );

      setShowDedupeModal(false);
      setDedupeHeaders([]);
      setSelectedMerged({});
      await refreshCenter();
    } catch (err: any) {
      setMessage(err?.message || "Deduplication failed.");
    } finally {
      setBusy(false);
    }
  }

  async function moveCompletedInputsBack() {
    if (!selectedCompletedInputBlobPaths.length) {
      setMessage("Select one or more completed deduplication input files.");
      return;
    }

    const confirmed = window.confirm(
      `Move ${selectedCompletedInputBlobPaths.length} completed input file(s) back to Merged Outputs Available for Deduplication?`
    );

    if (!confirmed) return;

    setBusy(true);
    setMessage("");

    try {
      const result = await apiPost(
        "/api/cyber-utility/xl-processing/rework-deduplication-inputs",
        {
          workspace,
          client: clientId,
          project_id: projectId,
          selected_blob_paths: selectedCompletedInputBlobPaths,
        }
      );

      setMessage(result.message || "Completed inputs moved back.");
      setSelectedCompletedInputs({});
      await refreshCenter();
    } catch (err: any) {
      setMessage(err?.message || "Failed to move completed inputs back.");
    } finally {
      setBusy(false);
    }
  }

  function openCsv(blobPath: string) {
    const path =
      `/api/cyber-utility/xl-processing/open-output?workspace=${encodeURIComponent(
        workspace
      )}&client=${encodeURIComponent(clientId)}&project=${encodeURIComponent(
        projectId
      )}&blob_path=${encodeURIComponent(blobPath)}`;

    window.open(buildApiUrl(path), "_blank", "noopener,noreferrer");
  }

  return (
    <AppShell>
      <PageContainer>
        <PageHeader
          title="Processing Center - Deduplication"
          subtitle="Combine merged spreadsheet outputs, select dedupe headers, and create deduplicated CSV outputs."
        />

        {message ? (
          <div className="mb-4 rounded-md border border-slate-700 bg-slate-900 px-4 py-3 text-sm text-slate-100">
            {message}
          </div>
        ) : null}

        <ContentCard title="Deduplication Controls">
          <div className="flex flex-wrap gap-2">
            <button
              className="rounded-md bg-slate-800 px-3 py-2 text-sm text-white hover:bg-slate-700 disabled:opacity-50"
              onClick={refreshCenter}
              disabled={busy}
            >
              Refresh
            </button>

            <button
              className="rounded-md bg-slate-800 px-3 py-2 text-sm text-white hover:bg-slate-700 disabled:opacity-50"
              onClick={() => toggleAllMerged(true)}
              disabled={!state?.merged_outputs?.length}
            >
              Select All Merged Outputs
            </button>

            <button
              className="rounded-md bg-slate-800 px-3 py-2 text-sm text-white hover:bg-slate-700 disabled:opacity-50"
              onClick={() => toggleAllMerged(false)}
              disabled={!state?.merged_outputs?.length}
            >
              Clear Selection
            </button>

            <button
              className="rounded-md bg-emerald-700 px-3 py-2 text-sm text-white hover:bg-emerald-600 disabled:opacity-50"
              onClick={openDedupeSetup}
              disabled={!selectedMergedBlobPaths.length || busy}
            >
              Combine & Deduplicate
            </button>
          </div>
        </ContentCard>

        <ContentCard title="Merged Outputs Available for Deduplication">
          <CsvSelectTable
            files={state?.merged_outputs || []}
            selected={selectedMerged}
            setSelected={setSelectedMerged}
            emptyMessage="No merged spreadsheet outputs found."
          />
        </ContentCard>

        <ContentCard title="Completed">
          <div className="mb-3 flex flex-wrap gap-2">
            <button
              className="rounded-md bg-slate-800 px-3 py-2 text-sm text-white hover:bg-slate-700 disabled:opacity-50"
              onClick={() => toggleAllCompletedInputs(true)}
              disabled={!state?.completed_inputs?.length}
            >
              Select All
            </button>

            <button
              className="rounded-md bg-slate-800 px-3 py-2 text-sm text-white hover:bg-slate-700 disabled:opacity-50"
              onClick={() => toggleAllCompletedInputs(false)}
              disabled={!state?.completed_inputs?.length}
            >
              Clear Selection
            </button>

            <button
              className="rounded-md bg-amber-700 px-3 py-2 text-sm text-white hover:bg-amber-600 disabled:opacity-50"
              onClick={moveCompletedInputsBack}
              disabled={!selectedCompletedInputBlobPaths.length || busy}
            >
              Move Back to Merged Outputs Available
            </button>
          </div>

          <CsvSelectTable
            files={state?.completed_inputs || []}
            selected={selectedCompletedInputs}
            setSelected={setSelectedCompletedInputs}
            emptyMessage="No completed deduplication input files found."
          />
        </ContentCard>

        <ContentCard title="Deduplicated Outputs">
          <OutputTable
            files={state?.deduped_outputs || []}
            onOpen={openCsv}
            emptyMessage="No deduplicated outputs found."
          />
        </ContentCard>

        {showDedupeModal ? (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70">
            <div className="w-full max-w-3xl rounded-xl border border-slate-700 bg-slate-950 p-5 shadow-2xl">
              <div className="mb-4">
                <h2 className="text-lg font-semibold text-white">
                  Select Deduplication Headers
                </h2>
                <p className="text-sm text-slate-400">
                  Select one or more headers. Fuzzy matching only applies when First Name, Middle Name, or Last Name is selected.
                </p>
              </div>

              <div className="mb-4 grid grid-cols-1 gap-3 md:grid-cols-3">
                <label className="text-sm text-slate-300">
                  Merge Delimiter
                  <select
                    className="mt-1 w-full rounded-md border border-slate-700 bg-slate-900 px-2 py-2 text-slate-100"
                    value={mergeDelimiter}
                    onChange={(event) => setMergeDelimiter(event.target.value)}
                  >
                    <option value=" | "> | </option>
                    <option value="; ">; </option>
                    <option value=", ">, </option>
                    <option value=" / "> / </option>
                    <option value={" \n "}>New Line</option>
                  </select>
                </label>

                <label className="flex items-center gap-2 pt-6 text-sm text-slate-300">
                  <input
                    type="checkbox"
                    checked={enableFuzzy}
                    onChange={(event) => setEnableFuzzy(event.target.checked)}
                  />
                  Enable Fuzzy Matching
                </label>

                <label className="text-sm text-slate-300">
                  Fuzzy Threshold: {fuzzyThreshold.toFixed(2)}
                  <input
                    className="mt-2 w-full"
                    type="range"
                    min="0.7"
                    max="0.95"
                    step="0.01"
                    value={fuzzyThreshold}
                    onChange={(event) => setFuzzyThreshold(Number(event.target.value))}
                  />
                </label>
              </div>

              <div className="max-h-72 overflow-auto rounded-md border border-slate-800">
                <table className="w-full text-left text-sm">
                  <thead className="bg-slate-900 text-slate-300">
                    <tr>
                      <th className="px-3 py-2"></th>
                      <th className="px-3 py-2">Header</th>
                    </tr>
                  </thead>
                  <tbody>
                    {availableHeaders.map((header) => (
                      <tr key={header} className="border-t border-slate-800">
                        <td className="px-3 py-2">
                          <input
                            type="checkbox"
                            checked={dedupeHeaders.includes(header)}
                            onChange={(event) =>
                              toggleDedupeHeader(header, event.target.checked)
                            }
                          />
                        </td>
                        <td className="px-3 py-2 text-slate-100">{header}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="mt-5 flex justify-end gap-2">
                <button
                  className="rounded-md bg-slate-800 px-3 py-2 text-sm text-white hover:bg-slate-700"
                  onClick={() => setShowDedupeModal(false)}
                >
                  Cancel
                </button>

                <button
                  className="rounded-md bg-emerald-700 px-3 py-2 text-sm text-white hover:bg-emerald-600 disabled:opacity-50"
                  onClick={runDedupe}
                  disabled={!dedupeHeaders.length || busy}
                >
                  Execute Deduplication
                </button>
              </div>
            </div>
          </div>
        ) : null}
      </PageContainer>
    </AppShell>
  );
}

export default function DeduplicationCenterPage() {
  return (
    <Suspense
      fallback={
        <AppShell>
          <PageContainer>
            <PageHeader
              title="Processing Center - Deduplication"
              subtitle="Loading deduplication center..."
            />
          </PageContainer>
        </AppShell>
      }
    >
      <DeduplicationCenterContent />
    </Suspense>
  );
}