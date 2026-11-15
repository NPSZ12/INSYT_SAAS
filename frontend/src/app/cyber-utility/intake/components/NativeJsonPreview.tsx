"use client";

import { useEffect, useState } from "react";
import { apiGet, apiPost } from "../../../../lib/api";

type NativeJsonField = {
  json_pointer: string;
  preview_occurrences: number;
};

type NativeJsonRow = {
  record_index: number;
  source_pointer: string;
  values: Record<string, unknown>;
};

type NativeJsonResult = {
  doc_id: string;
  source_format: string;
  record_count: number;
  preview_record_count: number;
  preview_truncated: boolean;
  source_sha256_verified: boolean;
  sha256: string;
  source_bytes: number;
  fields: NativeJsonField[];
  preview: NativeJsonRow[];
  csv_generated: false;
};

type MappingColumn = {
  header: string;
  json_pointer: string;
  present_count: number;
  missing_count: number;
  null_count: number;
};

type MappingResult = {
  record_count: number;
  validated_record_count: number;
  validation_complete: boolean;
  source_integrity_verified: boolean;
  source_sha256: string;
  columns: MappingColumn[];
  preview: NativeJsonRow[];
  preview_truncated: boolean;
  csv_generated: boolean;
  mapping_saved: boolean;
  mapping_approved: boolean;
};

type Props = {
  workspace: string;
  client: string;
  project: string;
  docId: string;
  onClose: () => void;
};

function displayValue(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "string") return value;
  return JSON.stringify(value);
}

export default function NativeJsonPreview({
  workspace,
  client,
  project,
  docId,
  onClose,
}: Props) {
  const [result, setResult] = useState<NativeJsonResult | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [selectedFields, setSelectedFields] = useState<string[]>([]);
  const [headers, setHeaders] = useState<Record<string, string>>({});
  const [mapping, setMapping] = useState<MappingResult | null>(null);
  const [mappingError, setMappingError] = useState("");
  const [validating, setValidating] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError("");
    setResult(null);
    setSelectedFields([]);
    setHeaders({});
    setMapping(null);
    setMappingError("");

    const params = new URLSearchParams({
      client,
      project,
      doc_id: docId,
    });

    apiGet(
      `/api/${encodeURIComponent(workspace)}/cyber2/intake/json-native-preview?${params.toString()}`
    ).then((data: NativeJsonResult) => {
      if (!cancelled) setResult(data);
    }).catch((reason: unknown) => {
      if (!cancelled) {
        setError(
          reason instanceof Error
            ? reason.message
            : "Unable to open native JSON preview."
        );
      }
    }).finally(() => {
      if (!cancelled) setLoading(false);
    });

    return () => { cancelled = true; };
  }, [workspace, client, project, docId]);

  function toggleField(path: string) {
    setSelectedFields((current) =>
      current.includes(path)
        ? current.filter((item) => item !== path)
        : [...current, path]
    );
    setMapping(null);
    setMappingError("");
  }

  function suggestedHeader(path: string): string {
    const last = path.split("/").pop() || "Column";
    return last.replace(/~1/g, "/").replace(/~0/g, "~");
  }

  function editHeader(path: string, value: string) {
    setHeaders((current) => ({ ...current, [path]: value }));
    setMapping(null);
    setMappingError("");
  }

  async function validateMapping() {
    if (!result || selectedFields.length === 0) {
      setMappingError("Select at least one JSON field.");
      return;
    }

    const columns = selectedFields.map((path) => ({
      json_pointer: path,
      header: headers[path] ?? suggestedHeader(path),
    }));

    setMapping(null);
    setMappingError("");
    setValidating(true);

    try {
      const response = await apiPost(
        `/api/${encodeURIComponent(workspace)}/cyber2/intake/json-native-mapping/validate`,
        { client, project, doc_id: docId, columns }
      ) as MappingResult;

      if (
        !response.validation_complete ||
        !response.source_integrity_verified ||
        response.source_sha256 !== result.sha256 ||
        response.csv_generated
      ) {
        throw new Error(
          "Mapping response did not pass source verification."
        );
      }

      setMapping(response);
    } catch (reason: unknown) {
      setMappingError(
        reason instanceof Error
          ? reason.message
          : "Unable to validate JSON field mapping."
      );
    } finally {
      setValidating(false);
    }
  }

  const shownFields = result?.fields ?? [];
  const selected = shownFields.filter((field) =>
    selectedFields.includes(field.json_pointer)
  );

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Native JSON preview"
      className="fixed inset-0 z-[100] overflow-y-auto bg-slate-950/95 p-4 text-slate-100"
    >
      <div className="mx-auto max-w-7xl space-y-5">
        <div className="flex flex-wrap items-start justify-between gap-4 border-b border-slate-700 pb-4">
          <div>
            <h2 className="text-xl font-semibold">Native JSON — Record & Field Preview</h2>
            <p className="mt-1 font-mono text-xs text-slate-400">
              {docId}
            </p>
            <p className="mt-1 text-xs text-slate-400">
              Read only. Original native preserved. No CSV generated.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border border-slate-600 px-4 py-2 text-sm hover:bg-slate-800"
          >
            Close preview
          </button>
        </div>

        {loading && <p role="status">Loading verified JSON preview…</p>}

        {error && (
          <div role="alert" className="rounded-lg border border-rose-700 p-4 text-rose-300">
            {error}
          </div>
        )}

        {result && (
          <>
            <div className="grid gap-3 md:grid-cols-4">
              <div className="rounded-lg border border-slate-700 p-3">
                <div className="text-xs text-slate-400">Source format</div>
                <strong>{result.source_format.toUpperCase()}</strong>
              </div>
              <div className="rounded-lg border border-slate-700 p-3">
                <div className="text-xs text-slate-400">Records</div>
                <strong>{result.record_count.toLocaleString()}</strong>
              </div>
              <div className="rounded-lg border border-slate-700 p-3">
                <div className="text-xs text-slate-400">Preview records</div>
                <strong>{result.preview_record_count.toLocaleString()}</strong>
              </div>
              <div className="rounded-lg border border-slate-700 p-3">
                <div className="text-xs text-slate-400">Source integrity</div>
                <strong>{result.source_sha256_verified ? "SHA-256 verified" : "Not verified"}</strong>
              </div>
            </div>

            {result.preview_truncated && (
              <p className="text-sm text-amber-300">
                Preview only: additional records may contain fields not displayed here.
              </p>
            )}

            <section className="rounded-lg border border-slate-700 p-4">
              <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h3 className="font-semibold">Preview fields</h3>
                  <p className="text-xs text-slate-400">
                    Select paths for a future reviewer-approved mapping.
                    Selection is local and is not saved or exported.
                  </p>
                </div>
                <span className="text-xs text-slate-400">
                  {selected.length} selected / {shownFields.length} preview fields
                </span>
              </div>
              <div className="grid max-h-64 gap-2 overflow-y-auto md:grid-cols-2">
                {shownFields.map((field) => (
                  <label
                    key={field.json_pointer}
                    className="flex cursor-pointer items-start gap-2 rounded border border-slate-700 p-2 text-xs"
                  >
                    <input
                      type="checkbox"
                      checked={selectedFields.includes(field.json_pointer)}
                      onChange={() => toggleField(field.json_pointer)}
                    />
                    <span className="min-w-0 flex-1">
                      <span className="block break-all font-mono">
                        {field.json_pointer}
                      </span>
                      {selectedFields.includes(field.json_pointer) && (
                        <input
                          aria-label={`Column header for ${field.json_pointer}`}
                          className="mt-2 w-full rounded border border-slate-600 bg-slate-950 px-2 py-1 text-slate-100"
                          value={
                            headers[field.json_pointer] ??
                            suggestedHeader(field.json_pointer)
                          }
                          onChange={(event) =>
                            editHeader(field.json_pointer, event.target.value)
                          }
                        />
                      )}
                    </span>
                    <span className="ml-auto text-slate-500">
                      {field.preview_occurrences}
                    </span>
                  </label>
                ))}
              </div>
            </section>

            <section className="rounded-lg border border-slate-700 p-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h3 className="font-semibold">Validate JSON Mapping</h3>
                  <p className="text-xs text-slate-400">
                    Validate all source records within the current size limit.
                    This does not save, approve, or generate a CSV.
                  </p>
                </div>
                <button
                  type="button"
                  disabled={validating || selectedFields.length === 0}
                  onClick={validateMapping}
                  className="rounded-lg bg-sky-700 px-4 py-2 text-sm font-semibold text-white disabled:opacity-40"
                >
                  {validating ? "Validating..." : "Validate Mapping"}
                </button>
              </div>

              {mappingError && (
                <p role="alert" className="mt-3 text-sm text-rose-300">
                  {mappingError}
                </p>
              )}

              {mapping && (
                <div className="mt-4 space-y-4">
                  <p role="status" className="text-sm text-emerald-300">
                    Validated {mapping.validated_record_count.toLocaleString()}
                    {" "}of {mapping.record_count.toLocaleString()} records.
                    Source SHA-256 verified.
                  </p>

                  <div className="overflow-x-auto">
                    <table className="min-w-full text-left text-xs">
                      <thead>
                        <tr className="border-b border-slate-700">
                          <th className="p-2">Column</th>
                          <th className="p-2">JSON path</th>
                          <th className="p-2">Present</th>
                          <th className="p-2">Missing</th>
                          <th className="p-2">Null</th>
                        </tr>
                      </thead>
                      <tbody>
                        {mapping.columns.map((column) => (
                          <tr key={column.json_pointer} className="border-b border-slate-800">
                            <td className="p-2">{column.header}</td>
                            <td className="p-2 font-mono">{column.json_pointer}</td>
                            <td className="p-2">{column.present_count}</td>
                            <td className="p-2">{column.missing_count}</td>
                            <td className="p-2">{column.null_count}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>

                  <div className="overflow-x-auto">
                    <h4 className="mb-2 font-semibold">Normalized row preview</h4>
                    <table className="min-w-full text-left text-xs">
                      <thead>
                        <tr className="border-b border-slate-700">
                          <th className="p-2">Source pointer</th>
                          {mapping.columns.map((column) => (
                            <th key={column.header} className="p-2">
                              {column.header}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {mapping.preview.map((row) => (
                          <tr key={row.source_pointer} className="border-b border-slate-800">
                            <td className="p-2 font-mono">{row.source_pointer}</td>
                            {mapping.columns.map((column) => (
                              <td key={column.header} className="p-2">
                                {displayValue(row.values[column.header])}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>

                  {mapping.preview_truncated && (
                    <p className="text-xs text-amber-300">
                      The normalized table is a preview. Validation covered
                      the full bounded source.
                    </p>
                  )}

                  <p className="text-xs text-slate-400">
                    Mapping not saved or approved. No CSV created.
                  </p>
                </div>
              )}
            </section>

            <section className="rounded-lg border border-slate-700 p-4">
              <h3 className="mb-1 font-semibold">Records</h3>
              <p className="mb-3 text-xs text-slate-400">
                Showing bounded source records and their original JSON pointers.
              </p>
              <div className="max-h-[45vh] space-y-3 overflow-auto">
                {result.preview.map((row) => (
                  <div key={row.record_index} className="rounded border border-slate-700 p-3">
                    <div className="mb-2 font-mono text-xs text-sky-300">
                      {row.source_pointer}
                    </div>
                    <div className="grid gap-2 md:grid-cols-2">
                      {Object.entries(row.values).map(([path, value]) => (
                        <div key={path} className="min-w-0 text-xs">
                          <div className="break-all font-mono text-slate-400">{path}</div>
                          <div className="break-words whitespace-pre-wrap">
                            {displayValue(value)}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </section>
          </>
        )}
      </div>
    </div>
  );
}
