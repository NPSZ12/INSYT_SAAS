"use client";

import { SummaryDocument } from "../../types/summaries";

type Props = {
  document: SummaryDocument;

  extractedMode: boolean;

  setExtractedMode: (value: boolean) => void;
};

export default function SummariesCenterPane({
  document,
  extractedMode,
  setExtractedMode,
}: Props) {
  return (
    <div className="flex-1 flex flex-col bg-slate-950">

      {/* HEADER */}
      <div className="border-b border-slate-800 p-4 flex justify-between items-center">

        <div>
          <h1 className="text-xl font-bold text-white">
            {document.filename}
          </h1>

          <p className="text-slate-400 text-sm">
            INSYT Summaries Review Workspace
          </p>
        </div>

        <div className="flex gap-2">

          <button
            className={`px-4 py-2 rounded ${
              !extractedMode
                ? "bg-lime-50"
                : "bg-slate-800"
            }`}
            onClick={() => setExtractedMode(false)}
          >
            Native
          </button>

          <button
            className={`px-4 py-2 rounded ${
              extractedMode
                ? "bg-lime-50"
                : "bg-slate-800"
            }`}
            onClick={() => setExtractedMode(true)}
          >
            Extracted Text
          </button>

        </div>
      </div>

      {/* DOCUMENT */}
      <div className="flex-1 overflow-auto p-8">

        <div className="max-w-5xl mx-auto bg-white text-black rounded-xl shadow-2xl p-10 min-h-[1400px]">

          <h2 className="text-2xl font-bold mb-6">
            Original Summary
          </h2>

          <div className="whitespace-pre-wrap leading-relaxed">
            {document.originalSummary}
          </div>

          <div className="mt-10 border-t pt-6">

            <h3 className="font-bold mb-4">
              {extractedMode
                ? "Extracted Text"
                : "Native Document"}
            </h3>

            <div className="bg-slate-100 rounded p-4 whitespace-pre-wrap text-sm">
              {extractedMode
                ? document.extractedText
                : document.nativeText}
            </div>

          </div>

        </div>

      </div>

    </div>
  );
}








