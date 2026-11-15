"use client";

import { useEffect, useState } from "react";
import { apiGet } from "../../../../lib/api";

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
  source_bytes: number;
  fields: NativeJsonField[];
  preview: NativeJsonRow[];
  csv_generated: false;
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

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError("");
    setResult(null);
    setSelectedFields([]);

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
                    <span className="break-all font-mono">
                      {field.json_pointer}
                    </span>
                    <span className="ml-auto text-slate-500">
                      {field.preview_occurrences}
                    </span>
                  </label>
                ))}
              </div>
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
