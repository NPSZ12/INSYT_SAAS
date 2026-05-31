"use client";

import { useEffect, useState } from "react";

import Button from "../Button";

type Props = {
  summaryDocId: string;

  title: string;
  citation?: string;

  originalSummary: string;
  qcSummary?: string;

  onSaveQcSummary?: (
    summaryDocId: string,
    qcSummary: string
  ) => Promise<void>;
};

export default function SummariesRightPane({
  summaryDocId,
  title,
  citation,
  originalSummary,
  qcSummary,
  onSaveQcSummary,
}: Props) {
  const [editableQcSummary, setEditableQcSummary] =
    useState("");

  const [message, setMessage] = useState("");

  useEffect(() => {
    setEditableQcSummary(
      qcSummary?.trim()
        ? qcSummary
        : originalSummary
    );

    setMessage("");
  }, [
    summaryDocId,
    qcSummary,
    originalSummary,
  ]);

  async function handleSave() {
    try {
      await onSaveQcSummary?.(
        summaryDocId,
        editableQcSummary
      );

      setMessage("QC Summary saved.");
    } catch (error) {
      console.error(error);
      setMessage("Failed to save QC Summary.");
    }
  }

  return (
    <aside className="w-full border-l border-slate-800 bg-slate-900 h-full flex flex-col">
      <div className="shrink-0 border-b border-slate-800 px-6 py-5">
        <h2 className="text-lg font-semibold text-white">
          Summary QC Review
        </h2>
      </div>

      <div className="flex-1 overflow-y-auto p-6 space-y-6">

        {/* TITLE */}

        <section>
          <h3 className="text-s uppercase tracking-[0.16em] text-slate-100 mb-2">
            Title
          </h3>

          <div className="rounded-xl border border-slate-800 bg-slate-950 p-4 text-sm text-slate-200">
            {title || "No title loaded."}
          </div>
        </section>

        {/* CITATION */}

        <section>
          <h3 className="text-s uppercase tracking-[0.16em] text-slate-100 mb-2">
            Citation
          </h3>

          <div className="rounded-xl border border-slate-800 bg-slate-950 p-4 text-sm text-slate-300 whitespace-pre-wrap">
            {citation || "No citation loaded."}
          </div>
        </section>

        {/* ORIGINAL SUMMARY */}

        <section>
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-s uppercase tracking-[0.16em] text-slate-100">
              Original Summary
            </h3>

            <span className="text-xs text-slate-500">
              Read Only
            </span>
          </div>

          <div className="rounded-xl border border-slate-800 bg-slate-950 p-4 text-sm text-slate-300 whitespace-pre-wrap">
            {originalSummary ||
              "No original summary loaded."}
          </div>
        </section>

        {/* QC SUMMARY */}

        <section>
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-s uppercase tracking-[0.16em] text-slate-100">
              QC Summary
            </h3>

            <span className="text-xs text-slate-500">
              Editable
            </span>
          </div>

          <textarea
            value={editableQcSummary}
            onChange={(event) =>
              setEditableQcSummary(
                event.target.value
              )
            }
            className="w-full min-h-[24rem] rounded-xl border border-slate-800 bg-slate-950 p-4 text-sm text-slate-200 outline-none focus:border-sky-500 resize-none"
          />
        </section>

      </div>

      <div className="shrink-0 border-t border-slate-800 p-5">
        <Button fullWidth onClick={handleSave}>
          Save QC Summary
        </Button>

        {message && (
          <p className="mt-3 text-sm text-sky-400">
            {message}
          </p>
        )}
      </div>
    </aside>
  );
}