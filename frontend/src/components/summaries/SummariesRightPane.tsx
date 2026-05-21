"use client";

import { SummaryDocument } from "../../types/summaries";

type Props = {
  document: SummaryDocument;
  qcText: string;
  setQcText: (value: string) => void;
  codingStatus: string;
  setCodingStatus: (value: string) => void;
  onSave: () => void;
  onSaveAndNext: () => void;
};

export default function SummariesRightPane({
  document,
  qcText,
  setQcText,
  codingStatus,
  setCodingStatus,
  onSave,
  onSaveAndNext,
}: Props) {
  return (
    <div className="w-[420px] border-l border-slate-800 bg-slate-900 flex flex-col">
      <div className="border-b border-slate-800 p-4">
        <h2 className="font-bold mb-3 text-white">Document Coding</h2>

        <select
          value={codingStatus}
          onChange={(e) => setCodingStatus(e.target.value)}
          className="w-full bg-slate-800 rounded p-2 text-white"
        >
          <option value="">Select Coding Status</option>
          <option value="Responsive">Responsive</option>
          <option value="Not Responsive">Not Responsive</option>
          <option value="Needs Further Review">Needs Further Review</option>
          <option value="Foreign Language">Foreign Language</option>
          <option value="Tech Issue">Tech Issue</option>
          <option value="Password Protected">Password Protected</option>
        </select>
      </div>

      <div className="flex-1 border-b border-slate-800 p-4 flex flex-col min-h-0">
        <h2 className="font-bold mb-3 text-white">Summary QC Entry</h2>

        <textarea
          value={qcText}
          onChange={(e) => setQcText(e.target.value)}
          className="flex-1 min-h-[260px] bg-slate-800 rounded p-4 resize-none text-white"
          placeholder="QC edits..."
        />

        <div className="grid grid-cols-2 gap-3 mt-4 shrink-0">
          <button
            type="button"
            onClick={onSave}
            className="bg-slate-700 hover:bg-teal-500 text-white rounded px-4 py-2 font-semibold"
          >
            Save
          </button>

          <button
            type="button"
            onClick={onSaveAndNext}
            className="bg-teal-500 hover:bg-teal-500 text-white rounded px-4 py-2 font-semibold"
          >
            Save & Next
          </button>
        </div>
      </div>

      <div className="h-72 overflow-auto p-4 shrink-0">
        <h2 className="font-bold mb-3 text-white">Linked Entries</h2>

        <div className="space-y-2 text-sm text-white">
          {document.linkedEntries.map((entry, index) => (
            <div key={index} className="bg-slate-800 rounded p-2">
              {entry.label}: {entry.value}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}








