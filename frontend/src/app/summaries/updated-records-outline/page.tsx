"use client";

import AppShell from "../../../components/AppShell";

export default function UpdatedRecordsOutlinePage() {
  return (
    <AppShell>
      <main className="p-8 text-white">
        <h1 className="text-3xl font-bold mb-2">
          Updated Records Outline
        </h1>

        <p className="text-slate-400 mb-6">
          Updated records outlines generated from Summary QC edits.
        </p>

        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6">
          <div className="text-slate-400">
            Saved QC outlines will populate here once backend persistence is connected.
          </div>
        </div>
      </main>
    </AppShell>
  );
}








