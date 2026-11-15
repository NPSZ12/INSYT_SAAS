"use client";

import { useState } from "react";

export type JsonHeaderReviewColumn = {
  column_index: number;
  source_header: string;
  json_pointer: string;
  json_kind: string;
  sample_values: string[];
  recommended_protocol_header?: string | null;
  mapping_confidence?: number | null;
  ai_confidence?: number | null;
  match_method?: string;
  occurrence_count?: number;
  record_count_with_field?: number;
  allowed_data_treatments?: string[];
};

export type JsonHeaderReviewContract = {
  source_sha256: string;
  source_kind: string;
  protocol_headers: string[];
  field_count: number;
  columns: JsonHeaderReviewColumn[];
  mapping_approved: boolean;
  csv_generated: boolean;
};

type Action = "approve" | "keep" | "map" | "discard";

type Treatment =
  | "text"
  | "concatenate"
  | "mask"
  | "yes_if_present"
  | "maximum"
  | "latest"
  | "discard";

type Decision = {
  action: Action;
  header: string;
  treatment: Treatment;
  reviewed: boolean;
};

const TREATMENTS: { value: Treatment; label: string }[] = [
  { value: "text", label: "Text — retain value" },
  { value: "concatenate", label: "Concatenate distinct values" },
  { value: "mask", label: "Mask sensitive value" },
  { value: "yes_if_present", label: "Yes if qualifying data exists" },
  { value: "maximum", label: "Maximum numeric value" },
  { value: "latest", label: "Latest date" },
  { value: "discard", label: "Discard from CSV" },
];

type OutputHeaderPreview = {
  json_pointer: string;
  protocol_header: string;
  output_header: string;
  treatment: Treatment;
};

function previewOutputHeaders(
  columns: JsonHeaderReviewColumn[],
  decisions: Record<string, Decision>,
  protocol: string[]
): OutputHeaderPreview[] {
  const reserved = new Set(
    protocol.map((header) => header.toLowerCase())
  );
  const assigned = new Set<string>();
  const output: OutputHeaderPreview[] = [];

  // Preserve the source-field order used by the backend.
  for (const column of columns) {
    const decision = decisions[column.json_pointer];

    if (!decision?.reviewed) continue;
    if (decision.action === "discard") continue;
    if (decision.treatment === "discard") continue;

    const base = protocol.find(
      (header) => header === decision.header
    );

    if (!base) continue;

    let candidate = base;
    let suffix = 2;

    while (
      assigned.has(candidate.toLowerCase()) ||
      (candidate !== base &&
        reserved.has(candidate.toLowerCase()))
    ) {
      candidate = `${base}_${suffix}`;
      suffix += 1;
    }

    assigned.add(candidate.toLowerCase());

    output.push({
      json_pointer: column.json_pointer,
      protocol_header: base,
      output_header: candidate,
      treatment: decision.treatment,
    });
  }

  return output;
}

function percent(value: number | null | undefined) {
  return typeof value === "number" && Number.isFinite(value)
    ? `${Math.round(value <= 1 ? value * 100 : value)}%`
    : "Not scored";
}

export default function JsonHeaderReviewPanel({
  review,
  docId,
}: {
  review?: JsonHeaderReviewContract;
  docId: string;
}) {
  const [index, setIndex] = useState(0);
  const [decisions, setDecisions] =
    useState<Record<string, Decision>>({});
  const [error, setError] = useState("");

  if (!review) {
    return (
      <section className="rounded-xl border border-slate-700 p-5">
        <h3 className="font-semibold">JSON Header Creation</h3>
        <p className="mt-2 text-sm text-amber-300">
          Approved project protocol and JSON header evidence
          are not yet available.
        </p>
      </section>
    );
  }

  const columns = review.columns || [];
  const protocol = review.protocol_headers || [];
  const current = columns[index];
  const completed = columns.filter(
    (column) => decisions[column.json_pointer]?.reviewed
  ).length;

  const outputPreview = previewOutputHeaders(
    columns,
    decisions,
    protocol
  );

  const allReviewed =
    columns.length > 0 && completed === columns.length;

  function defaultDecision(
    column: JsonHeaderReviewColumn
  ): Decision {
    const suggested = column.recommended_protocol_header || "";
    return {
      action: suggested ? "approve" : "discard",
      header: suggested,
      treatment: suggested ? "text" : "discard",
      reviewed: false,
    };
  }

  function change(patch: Partial<Decision>) {
    if (!current) return;
    const previous =
      decisions[current.json_pointer] ?? defaultDecision(current);
    setDecisions((state) => ({
      ...state,
      [current.json_pointer]: {
        ...previous,
        ...patch,
        reviewed: false,
      },
    }));
    setError("");
  }

  function approveCurrent() {
    if (!current) return;
    const decision =
      decisions[current.json_pointer] ?? defaultDecision(current);

    const excluded =
      decision.action === "discard" ||
      decision.treatment === "discard";

    if (!excluded && !protocol.includes(decision.header)) {
      setError(
        "Select an existing client-approved protocol header."
      );
      return;
    }

    if (
      !excluded &&
      decision.action === "approve" &&
      decision.header !== current.recommended_protocol_header
    ) {
      setError("The selected header differs from the recommendation.");
      return;
    }

    const finalDecision: Decision = {
      ...decision,
      action: excluded ? "discard" : decision.action,
      header: excluded ? "" : decision.header,
      treatment: excluded ? "discard" : decision.treatment,
      reviewed: true,
    };

    setDecisions((state) => ({
      ...state,
      [current.json_pointer]: finalDecision,
    }));
    setError("");

    const next = columns.findIndex(
      (column, candidate) =>
        candidate > index &&
        !(
          column.json_pointer === current.json_pointer
            ? true
            : decisions[column.json_pointer]?.reviewed
        )
    );

    if (next >= 0) setIndex(next);
  }

  if (!current) {
    return (
      <section className="rounded-xl border border-slate-700 p-5">
        No JSON header fields were discovered.
      </section>
    );
  }

  const decision =
    decisions[current.json_pointer] ?? defaultDecision(current);
  const eligibleAsIs = protocol.includes(current.source_header);
  const recommended = current.recommended_protocol_header || "";

  return (
    <section className="rounded-2xl border border-slate-800 bg-slate-900/60">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 px-5 py-4">
        <div>
          <h3 className="text-lg font-semibold text-white">
            Header & Schema Mapping — JSON Header Creation
          </h3>
          <p className="mt-1 text-sm text-slate-400">
            Same pre-approval review format as CSV. Native JSON
            is preserved; no CSV exists yet.
          </p>
        </div>
        <div className="text-sm text-slate-300">
          Field {index + 1} of {columns.length} · {completed} reviewed
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full min-w-[1450px] text-sm">
          <thead className="bg-slate-950 text-left text-[11px] uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-4 py-3">Source Header</th>
              <th className="px-4 py-3">Doc ID</th>
              <th className="px-4 py-3">Sample Data</th>
              <th className="px-4 py-3">Confidence</th>
              <th className="px-4 py-3">Evidence</th>
              <th className="px-4 py-3">Action</th>
              <th className="px-4 py-3">Final Header</th>
              <th className="px-4 py-3">Data Treatment</th>
            </tr>
          </thead>
          <tbody>
            <tr className="border-t border-slate-800 align-top">
              <td className="max-w-[260px] break-all px-4 py-4">
                <div className="font-semibold text-slate-200">
                  {current.source_header}
                </div>
                <div className="mt-2 font-mono text-xs text-slate-500">
                  {current.json_pointer}
                </div>
              </td>
              <td className="px-4 py-4 font-mono text-xs text-sky-400">
                {docId}
              </td>
              <td className="max-w-[260px] px-4 py-4">
                {(current.sample_values || []).slice(0, 3).map(
                  (value, i) => (
                    <div key={i} className="mb-1 break-words font-mono text-xs text-slate-300">
                      {value}
                    </div>
                  )
                )}
                {!current.sample_values?.length && (
                  <span className="text-slate-500">No sample values</span>
                )}
              </td>
              <td className="px-4 py-4 text-sm">
                <div>Mapping: {percent(current.mapping_confidence)}</div>
                <div className="mt-1 text-violet-400">
                  AI: {percent(current.ai_confidence)}
                </div>
              </td>
              <td className="px-4 py-4 text-xs text-slate-300">
                <div>Type: {current.json_kind}</div>
                <div className="mt-1">
                  Match: {current.match_method || "Unreviewed"}
                </div>
                <div className="mt-1">
                  Occurrences: {current.occurrence_count ?? 0}
                </div>
                <div className="mt-1">
                  Records: {current.record_count_with_field ?? 0}
                </div>
              </td>
              <td className="px-4 py-4">
                <select
                  aria-label="Mapping action"
                  value={decision.action}
                  onChange={(e) => {
                    const action = e.target.value as Action;
                    change({
                      action,
                      header:
                        action === "approve"
                          ? recommended
                          : action === "keep"
                            ? (eligibleAsIs ? current.source_header : "")
                            : action === "discard"
                              ? ""
                              : decision.header,
                      treatment:
                        action === "discard"
                          ? "discard"
                          : decision.treatment === "discard"
                            ? "text"
                            : decision.treatment,
                    });
                  }}
                  className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-slate-200"
                >
                  {recommended && (
                    <option value="approve">Approve Recommendation</option>
                  )}
                  <option value="map">Map to Protocol Field</option>
                  <option value="keep">Keep As-Is</option>
                  <option value="discard">Discard</option>
                </select>
              </td>
              <td className="px-4 py-4">
                {decision.action === "discard" ? (
                  <span className="text-rose-300">Excluded from CSV</span>
                ) : (
                  <select
                    aria-label="Approved protocol header"
                    value={decision.header}
                    onChange={(e) =>
                      change({
                        action: "map",
                        header: e.target.value,
                      })
                    }
                    className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-slate-200"
                  >
                    <option value="">Select Protocol Header</option>
                    {protocol.map((header) => (
                      <option key={header} value={header}>
                        {header}
                      </option>
                    ))}
                  </select>
                )}
              </td>
              <td className="px-4 py-4">
                <select
                  aria-label="JSON data treatment"
                  value={decision.treatment}
                  onChange={(e) =>
                    change({
                      treatment: e.target.value as Treatment,
                    })
                  }
                  className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-slate-200"
                >
                  {TREATMENTS.map((item) => (
                    <option key={item.value} value={item.value}>
                      {item.label}
                    </option>
                  ))}
                </select>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      {error && (
        <p role="alert" className="px-5 pt-3 text-sm text-rose-300">
          {error}
        </p>
      )}

      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-800 px-5 py-4">
        <div className="flex gap-2">
          <button
            type="button"
            disabled={index === 0}
            onClick={() => setIndex((n) => Math.max(0, n - 1))}
            className="rounded-lg border border-slate-700 px-3 py-2 disabled:opacity-40"
          >
            Previous
          </button>
          <button
            type="button"
            disabled={index === columns.length - 1}
            onClick={() =>
              setIndex((n) => Math.min(columns.length - 1, n + 1))
            }
            className="rounded-lg border border-slate-700 px-3 py-2 disabled:opacity-40"
          >
            Next
          </button>
        </div>
        <button
          type="button"
          onClick={approveCurrent}
          className="rounded-lg bg-emerald-600 px-5 py-2.5 font-semibold text-white hover:bg-emerald-500"
        >
          {decision.reviewed ? "Reapprove Data Element" : "Approve Data Element"}
        </button>
      </div>

      <div className="border-t border-slate-800 px-5 py-4">
        <h4 className="font-semibold text-white">
          JSON Output Header Preview
        </h4>
        <p className="mt-1 text-xs text-slate-400">
          Separate approved JSON fields remain separate CSV columns.
          Duplicate protocol headers use _2, _3, and subsequent
          suffixes. These assignments are provisional until the
          backend validates and saves the mapping.
        </p>

        <div className="mt-3 overflow-x-auto">
          <table className="min-w-full text-left text-xs">
            <thead className="border-b border-slate-700 text-slate-400">
              <tr>
                <th className="p-2">Output CSV Header</th>
                <th className="p-2">Approved Protocol Header</th>
                <th className="p-2">Original JSON Path</th>
                <th className="p-2">Data Treatment</th>
              </tr>
            </thead>
            <tbody>
              {outputPreview.map((item) => (
                <tr
                  key={item.json_pointer}
                  className="border-b border-slate-800"
                >
                  <td className="p-2 font-semibold text-sky-300">
                    {item.output_header}
                  </td>
                  <td className="p-2">{item.protocol_header}</td>
                  <td className="p-2 font-mono">
                    {item.json_pointer}
                  </td>
                  <td className="p-2">{item.treatment}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {outputPreview.length === 0 && (
          <p className="mt-3 text-sm text-slate-500">
            No reportable JSON fields approved yet.
          </p>
        )}

        <p className="mt-3 text-xs text-slate-400">
          {allReviewed
            ? "All source fields have been reviewed locally."
            : `${columns.length - completed} fields still require review.`}
        </p>
      </div>

      <div className="border-t border-slate-800 px-5 py-3 text-xs text-slate-400">
        {completed} of {columns.length} fields reviewed locally.
        Decisions are not saved. No AI matching has been invoked,
        and no Mapped CSV has been created.
      </div>
    </section>
  );
}
