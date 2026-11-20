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
  sha256: string;
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

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError("");
    setResult(null);

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
            <div className="grid gap-3 md:grid-cols-2">
              <div className="rounded-lg border border-slate-700 p-3">
                <div className="text-xs text-slate-400">Source format</div>
                <strong>{result.source_format.toUpperCase()}</strong>
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
              <h3 className="mb-1 font-semibold">Native JSON source preview</h3>
              <p className="mb-3 text-xs text-slate-400">
                Showing bounded original JSON entries and their source pointers. The authoritative record count is determined after approved Header Mapping and mapped CSV creation.
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
