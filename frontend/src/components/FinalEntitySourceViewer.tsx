"use client";

import { useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import AppShell from "./AppShell";
import PageContainer from "./PageContainer";
import PageHeader from "./PageHeader";
import ContentCard from "./ContentCard";

type Workspace = "capture" | "discovery" | "summaries";

type FinalEntitySourceViewerProps = {
  workspace: Workspace;
};

function splitDocIds(value: string | null) {
  return String(value || "")
    .split(";")
    .map((item) => item.trim())
    .filter(Boolean);
}

export default function FinalEntitySourceViewer({
  workspace,
}: FinalEntitySourceViewerProps) {
  const searchParams = useSearchParams();
  const router = useRouter();

  const clientId = searchParams.get("client") || "";
  const projectId = searchParams.get("project") || "";
  const capturedEntity = searchParams.get("entity") || "";
  const rawDocIds = searchParams.get("docIds") || "";

  const docIds = useMemo(() => {
    return splitDocIds(rawDocIds);
  }, [rawDocIds]);

  const [selectedDocIds, setSelectedDocIds] =
    useState<string[]>(docIds);

  function isSelected(docId: string) {
    return selectedDocIds.includes(docId);
  }

  function toggleDoc(docId: string) {
    setSelectedDocIds((current) => {
      if (current.includes(docId)) {
        return current.filter((item) => item !== docId);
      }

      return [...current, docId];
    });
  }

  function selectAll() {
    setSelectedDocIds(docIds);
  }

  function clearSelection() {
    setSelectedDocIds([]);
  }

  function openReviewForDocs(targetDocIds: string[]) {
    const cleanDocIds = targetDocIds
      .map((item) => String(item || "").trim())
      .filter(Boolean);

    if (cleanDocIds.length === 0) {
      alert("Select at least one source document first.");
      return;
    }

    const params = new URLSearchParams();

    if (clientId) params.set("client", clientId);
    if (projectId) params.set("project", projectId);
    if (capturedEntity) params.set("entity", capturedEntity);

    params.set("doc", cleanDocIds[0]);
    params.set("docSet", cleanDocIds.join(";"));
    params.set("source", "final");

    router.push(`/${workspace}/review/doc?${params.toString()}`);
  }

  function openSingleDoc(docId: string) {
    openReviewForDocs([docId]);
  }

  function openSelectedDocs() {
    openReviewForDocs(selectedDocIds);
  }

  function openAllDocs() {
    openReviewForDocs(docIds);
  }

  if (!projectId || docIds.length === 0) {
    return (
      <AppShell>
        <PageContainer>
          <PageHeader
            title="Final Entity Source Documents"
            subtitle="No grouped source documents were provided."
          />

          <ContentCard title="Missing Source Documents">
            <p className="text-sm text-slate-500">
              Return to the Final tab and select a grouped Doc ID value again.
            </p>
          </ContentCard>
        </PageContainer>
      </AppShell>
    );
  }

  return (
    <AppShell>
      <PageContainer>
        <PageHeader
          title="Final Entity Source Documents"
          subtitle={`Source documents associated with the selected Final entity for ${projectId.replaceAll(
            "_",
            " "
          )}.`}
        />

        <ContentCard title="Source Document Set">
          <div className="mb-4 grid grid-cols-1 gap-3 text-sm text-slate-400 md:grid-cols-3">
            <p>
              Captured Entity:{" "}
              <span className="font-semibold text-slate-100">
                {capturedEntity || "Unknown Entity"}
              </span>
            </p>

            <p>
              Project:{" "}
              <span className="font-semibold text-slate-100">
                {projectId}
              </span>
            </p>

            <p>
              Source Docs:{" "}
              <span className="font-semibold text-slate-100">
                {docIds.length}
              </span>
            </p>
          </div>

          <div className="mb-4 rounded-xl border border-slate-800 bg-slate-950 p-3">
            <p className="mb-2 text-xs uppercase tracking-wide text-slate-500">
              Grouped Final Doc IDs
            </p>

            <p className="whitespace-pre-wrap text-sm text-slate-300">
              {docIds.join("; ")}
            </p>
          </div>

          <div className="mb-4 flex flex-wrap gap-2">
            <button
              type="button"
              onClick={selectAll}
              className="rounded-xl bg-slate-800 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-700"
            >
              Select All
            </button>

            <button
              type="button"
              onClick={clearSelection}
              className="rounded-xl bg-slate-800 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-700"
            >
              Clear Selection
            </button>

            <button
              type="button"
              onClick={openSelectedDocs}
              className="rounded-xl bg-sky-600 px-4 py-2 text-sm font-semibold text-white hover:bg-sky-500"
            >
              Open Review for Selected
            </button>

            <button
              type="button"
              onClick={openAllDocs}
              className="rounded-xl bg-teal-600 px-4 py-2 text-sm font-semibold text-white hover:bg-teal-500"
            >
              Open Review for All
            </button>

            <button
              type="button"
              disabled
              className="rounded-xl bg-slate-700 px-4 py-2 text-sm font-semibold text-white opacity-50"
              title="Export backend will be added later."
            >
              Export Selected
            </button>
          </div>

          <p className="mb-4 text-xs text-slate-500">
            Selected for review/export:{" "}
            {selectedDocIds.length === 0
              ? "None"
              : selectedDocIds.join("; ")}
          </p>

          <div className="overflow-auto rounded-xl border border-slate-800">
            <table className="min-w-full text-sm">
              <thead className="bg-slate-900 text-slate-400">
                <tr>
                  <th className="w-12 border-b border-slate-800 p-3 text-left">
                    Select
                  </th>
                  <th className="border-b border-slate-800 p-3 text-left">
                    Doc ID
                  </th>
                  <th className="border-b border-slate-800 p-3 text-left">
                    Action
                  </th>
                  <th className="border-b border-slate-800 p-3 text-left">
                    Export
                  </th>
                </tr>
              </thead>

              <tbody>
                {docIds.map((docId, index) => (
                  <tr
                    key={`${docId}-${index}`}
                    className="border-t border-slate-800"
                  >
                    <td className="p-3">
                      <input
                        type="checkbox"
                        checked={isSelected(docId)}
                        onChange={() => toggleDoc(docId)}
                        className="h-4 w-4"
                      />
                    </td>

                    <td className="p-3 font-mono text-slate-200">
                      {docId}
                    </td>

                    <td className="p-3">
                      <button
                        type="button"
                        onClick={() => openSingleDoc(docId)}
                        className="text-sky-400 underline hover:text-sky-300"
                      >
                        Open Single Doc
                      </button>
                    </td>

                    <td className="p-3 text-slate-500">
                      {isSelected(docId)
                        ? "Selected"
                        : "Not selected"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </ContentCard>
      </PageContainer>
    </AppShell>
  );
}