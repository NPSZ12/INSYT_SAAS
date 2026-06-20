"use client";

import { useEffect, useState } from "react";

import Button from "../Button";
import type { PdfOutlineItem } from "./PdfOutlinePane";


type Props = {
  summaryDocId: string;

  title: string;
  citation?: string;

  originalSummary: string;
  qcSummary?: string;

  outlineItems?: PdfOutlineItem[];
  selectedOutlineId?: string;
  onSelectOutlineItem?: (item: PdfOutlineItem) => void;
  isSummarySetReview?: boolean;

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
  outlineItems = [],
  selectedOutlineId = "",
  onSelectOutlineItem,
  isSummarySetReview = false,
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

        {/* PDF OUTLINE */}

        {outlineItems.length > 0 && onSelectOutlineItem && (
          <section>
            <div className="mb-3 flex items-center justify-between gap-3">
              <div>
                <h3 className="text-s uppercase tracking-[0.16em] text-slate-100">
                  PDF Outline
                </h3>

                <p className="mt-1 text-xs text-slate-500">
                  Select a summary section to QC.
                </p>
              </div>

              {isSummarySetReview && (
                <span className="rounded-full border border-lime-400/40 bg-lime-400/10 px-3 py-1 text-xs font-semibold text-lime-300">
                  Summary Set
                </span>
              )}
            </div>

            <div className="max-h-64 space-y-2 overflow-y-auto rounded-xl border border-slate-800 bg-slate-950 p-3">
              {outlineItems.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => onSelectOutlineItem(item)}
                  className={
                    selectedOutlineId === item.id
                      ? "w-full rounded-lg border border-lime-400 bg-lime-50 px-3 py-2 text-left text-sm text-slate-950"
                      : "w-full rounded-lg border border-slate-800 bg-slate-900 px-3 py-2 text-left text-sm text-slate-300 hover:bg-slate-800"
                  }
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-semibold">
                      {item.title || item.id}
                    </span>

                    {item.citation && (
                      <span className="shrink-0 text-xs opacity-70">
                        {item.citation}
                      </span>
                    )}
                  </div>
                </button>
              ))}
            </div>
          </section>
        )}

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