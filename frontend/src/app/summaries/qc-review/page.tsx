"use client";

import { useEffect, useState } from "react";
import AppShell from "../../../components/AppShell";

type SavedSummaryQc = {
  codingStatus: string;
  qcText: string;
  updatedOutlineItems: string[];
};

export default function SummariesQcReviewPage() {
  const [savedQc, setSavedQc] =
    useState<Record<string, SavedSummaryQc>>({});

  useEffect(() => {
    const stored = localStorage.getItem("insyt_summaries_qc");

    if (stored) {
      setSavedQc(JSON.parse(stored));
    }
  }, []);

  function deleteSavedEntry(docId: string) {
    const next = { ...savedQc };

    delete next[docId];

    setSavedQc(next);

    localStorage.setItem(
      "insyt_summaries_qc",
      JSON.stringify(next)
    );
  }

  function exportQcSession() {
    const blob = new Blob(
      [JSON.stringify(savedQc, null, 2)],
      {
        type: "application/json",
      }
    );

    const url = URL.createObjectURL(blob);

    const a = document.createElement("a");

    a.href = url;

    a.download = "insyt_summaries_qc_export.json";

    document.body.appendChild(a);

    a.click();

    document.body.removeChild(a);

    URL.revokeObjectURL(url);
  }

  return (
    <AppShell>
      <main className="p-8 text-white">
        <h1 className="text-3xl font-bold mb-2">
          Saved Summary QC Entries
        </h1>

        <p className="text-slate-400 mb-6">
          Review saved Summary QC edits, coding decisions, and updated outlines.
        </p>

        <div className="mb-6">
          <button
            type="button"
            onClick={exportQcSession}
            className="bg-teal-500 hover:bg-teal-500 text-white rounded px-4 py-2 font-semibold"
          >
            Export QC Session
          </button>
        </div>

        <div className="space-y-4">
          {Object.keys(savedQc).length === 0 ? (
            <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 text-slate-400">
              No saved Summary QC entries yet.
            </div>
          ) : (
            Object.entries(savedQc).map(([docId, entry]) => (
              <div
                key={docId}
                className="bg-slate-900 border border-slate-800 rounded-2xl p-6"
              >
                <h2 className="text-xl font-bold mb-2">
                  {docId}
                </h2>
                <button
                  type="button"
                  onClick={() => deleteSavedEntry(docId)}
                  className="mb-4 bg-red-600 hover:bg-red-500 text-white rounded px-4 py-2 text-sm font-semibold"
                >
                  Delete Saved QC
                </button>

                <div className="text-sm text-slate-400 mb-4">
                  Coding Status:{" "}
                  <span className="text-white font-semibold">
                    {entry.codingStatus}
                  </span>
                </div>

                <div className="mb-4">
                  <h3 className="font-semibold mb-2">
                    QC Text
                  </h3>

                  <div className="bg-slate-800 rounded-xl p-4 whitespace-pre-wrap text-sm">
                    {entry.qcText}
                  </div>
                </div>

                <div>
                  <h3 className="font-semibold mb-2">
                    Updated Records Outline
                  </h3>

                  <div className="bg-slate-800 rounded-xl p-4 text-sm space-y-1">
                    {entry.updatedOutlineItems.map((item, index) => (
                      <div key={index}>
                        {index + 1}. {item}
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            ))
          )}
        </div>
      </main>
    </AppShell>
  );
}








