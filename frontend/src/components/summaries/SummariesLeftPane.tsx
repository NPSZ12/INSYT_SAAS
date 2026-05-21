"use client";

import { SummaryDocument } from "../../types/summaries";

type Props = {
  documents: SummaryDocument[];

  selectedDocument: SummaryDocument;

  updatedOutlineItems: string[];

  savedDocIds: string[];

  onSelectDocument: (doc: SummaryDocument) => void;

  onSelectHyperlink: (text: string) => void;
};

export default function SummariesLeftPane({
  documents,
  selectedDocument,
  updatedOutlineItems,
  savedDocIds,
  onSelectDocument,
  onSelectHyperlink,
}: Props) {
  const originalOutlineItems =
    selectedDocument.originalSummary
      .split(".")
      .map((item) => item.trim())
      .filter(Boolean);

  return (
    <div className="w-80 border-r border-slate-800 bg-slate-900 flex flex-col">
      <div className="border-b border-slate-800 p-4">
        <h2 className="font-bold text-lg text-white">Files</h2>
      </div>

      <div className="p-3 space-y-2 overflow-auto">
        {documents.map((doc) => (
          <div
            key={doc.id}
            onClick={() => onSelectDocument(doc)}
            className={
              selectedDocument.id === doc.id
                ? "bg-teal-500 rounded p-2 cursor-pointer"
                : "bg-slate-800 rounded p-2 hover:bg-slate-700 cursor-pointer"
            }
          >
            <div className="flex items-center justify-between gap-2">
              <span className="truncate">{doc.filename}</span>

              {savedDocIds.includes(doc.id) && (
                <span className="text-xs bg-lime-200 text-white rounded-full px-2 py-0.5">
                  Saved
                </span>
              )}
            </div>
          </div>
        ))}
      </div>

      <div className="border-t border-slate-800 p-4">
        <h2 className="font-bold mb-2 text-white">PDF Outline</h2>

        <div className="space-y-1 text-sm">
          {selectedDocument.outlineItems.map((item) => (
            <div
              key={item.id}
              className="text-blue-400 cursor-pointer hover:underline"
              onClick={() => onSelectHyperlink(item.linkedText)}
            >
              {item.title}
            </div>
          ))}
        </div>
      </div>

      <div className="border-t border-slate-800 p-4">
        <h2 className="font-bold mb-2 text-white">Original Records Outline</h2>

        <div className="space-y-1 text-sm text-slate-300">
          {originalOutlineItems.map((item, index) => (
            <div key={index}>
              {index + 1}. {item}
            </div>
          ))}
        </div>
      </div>

      <div className="border-t border-slate-800 p-4">
        <h2 className="font-bold mb-2 text-white">Updated Records Outline</h2>

        <div className="space-y-1 text-sm text-slate-300">
          {updatedOutlineItems.length > 0 ? (
            updatedOutlineItems.map((item, index) => (
              <div key={index}>
                {index + 1}. {item}
              </div>
            ))
          ) : (
            <div className="text-slate-500">
              QC edits will generate the updated outline.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}








