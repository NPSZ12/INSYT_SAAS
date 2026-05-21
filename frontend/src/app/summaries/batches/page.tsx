"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";

import AppShell from "../../../components/AppShell";
import { apiGet, apiPost } from "../../../lib/api";

type Batch = {
  batch_name: string;
  status: string;
  level: string;
  workflow_type: string;
  batch_size: number;
  document_count: number;
  doc_ids: string[];
};

function SummariesBatchesPageContent() {
  const searchParams = useSearchParams();

  const queryProject = searchParams.get("project");

  const storedProject =
    typeof window !== "undefined"
      ? localStorage.getItem("insyt_selected_project")
      : "";

  const selectedProject = queryProject || storedProject;

  const [batches, setBatches] = useState<Batch[]>([]);
  const [loading, setLoading] = useState(true);

  const [docsPerBatch, setDocsPerBatch] = useState("10");
  const [customDocsPerBatch, setCustomDocsPerBatch] = useState("");
  const [level, setLevel] = useState("1L");

  const resolvedBatchSize =
    docsPerBatch === "Custom"
      ? Number(customDocsPerBatch)
      : Number(docsPerBatch);

  async function loadBatches() {
    if (!selectedProject) {
      setLoading(false);
      return;
    }

    try {
      const data = await apiGet(
        `/api/summaries/projects/${selectedProject}/batches`
      );

      setBatches(data.batches || []);
    } catch (error) {
      console.error(error);
      setBatches([]);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadBatches();
  }, [selectedProject]);

  async function createBatch() {
    if (!selectedProject) {
      alert("Select a project first.");
      return;
    }

    if (!resolvedBatchSize || resolvedBatchSize <= 0) {
      alert("Enter a valid Docs / Batch value.");
      return;
    }

    try {
      await apiPost(
        `/api/summaries/projects/${selectedProject}/batches/create`,
        {
          batch_size: resolvedBatchSize,
          level,
          workflow_type:
            level === "ALT Workflow" ? "alt_workflow" : "standard",
          created_by: "admin",
          search_folder_doc_ids: null,
        }
      );

      await loadBatches();

      alert("Batch created.");
    } catch (error) {
      console.error(error);
      alert("Failed to create batch.");
    }
  }

  return (
    <AppShell>
      <main className="p-8 text-white">
        <h1 className="text-3xl font-bold mb-2">
          INSYT Summaries Batches
        </h1>

        <p className="text-slate-400 mb-6">
          Create and manage review batches for the selected Summaries project.
        </p>

        {!selectedProject ? (
          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 text-slate-400">
            No project selected. Go to Projects and select a Summaries project first.
          </div>
        ) : (
          <>
            <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 mb-6">
              <div className="text-sm text-slate-400 mb-2">
                Selected Project
              </div>

              <div className="text-xl font-bold mb-6">
                {selectedProject}
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 items-end">
                <div>
                  <label className="block text-sm text-slate-400 mb-2">
                    Docs / Batch
                  </label>

                  <select
                    value={docsPerBatch}
                    onChange={(e) => setDocsPerBatch(e.target.value)}
                    className="w-full bg-slate-800 border border-slate-700 rounded-xl px-4 py-3 text-white"
                  >
                    <option value="1">1</option>
                    <option value="5">5</option>
                    <option value="10">10</option>
                    <option value="20">20</option>
                    <option value="50">50</option>
                    <option value="Custom">Custom</option>
                  </select>
                </div>

                {docsPerBatch === "Custom" && (
                  <div>
                    <label className="block text-sm text-slate-400 mb-2">
                      Custom Docs / Batch
                    </label>

                    <input
                      type="number"
                      min="1"
                      value={customDocsPerBatch}
                      onChange={(e) =>
                        setCustomDocsPerBatch(e.target.value)
                      }
                      className="w-full bg-slate-800 border border-slate-700 rounded-xl px-4 py-3 text-white"
                    />
                  </div>
                )}

                <div>
                  <label className="block text-sm text-slate-400 mb-2">
                    Level
                  </label>

                  <select
                    value={level}
                    onChange={(e) => setLevel(e.target.value)}
                    className="w-full bg-slate-800 border border-slate-700 rounded-xl px-4 py-3 text-white"
                  >
                    <option value="1L">1L</option>
                    <option value="QC">QC</option>
                    <option value="ALT Workflow">ALT Workflow</option>
                  </select>
                </div>

                <button
                  type="button"
                  onClick={createBatch}
                  className="bg-teal-500 hover:bg-teal-500 text-white rounded-xl px-4 py-3 font-semibold"
                >
                  Create Batch
                </button>
              </div>

              <div className="text-xs text-slate-500 mt-4">
                1L excludes already 1L-batched documents. QC excludes already QC-batched documents. ALT Workflow requires Search Folder Results.
              </div>
            </div>

            {loading ? (
              <div className="text-slate-400">Loading batches...</div>
            ) : batches.length === 0 ? (
              <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 text-slate-400">
                No batches found.
              </div>
            ) : (
              <div className="space-y-4">
                {batches.map((batch) => (
                  <div
                    key={batch.batch_name}
                    className="bg-slate-900 border border-slate-800 rounded-2xl p-6"
                  >
                    <div className="flex items-center justify-between gap-4">
                      <div>
                        <div className="text-xl font-bold">
                          {batch.batch_name}
                        </div>

                        <div className="text-slate-400 text-sm mt-1">
                          {batch.document_count} documents · {batch.level} · {batch.workflow_type}
                        </div>
                      </div>

                      <div className="bg-slate-800 rounded-full px-3 py-1 text-sm">
                        {batch.status}
                      </div>
                    </div>

                    <div className="text-xs text-slate-500 mt-4">
                      Docs: {batch.doc_ids.join(", ")}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </main>
    </AppShell>
  );
}










export default function Page() {
  return (
    <Suspense fallback={<div>Loading...</div>}>
      <SummariesBatchesPageContent />
    </Suspense>
  );
}

