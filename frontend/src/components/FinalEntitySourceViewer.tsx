"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import AppShell from "./AppShell";
import PageContainer from "./PageContainer";
import PageHeader from "./PageHeader";
import ContentCard from "./ContentCard";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000";

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
  const entityUid = searchParams.get("entityUid") || "";
  const rawDocIds = searchParams.get("docIds") || "";
  const isC2 = searchParams.get("source") === "c2";
  const c2HeaderSetId = searchParams.get("headerSetId") || "";
  const c2RecordId = searchParams.get("recordId") || "";
  const c2StartDoc = searchParams.get("startDoc") || "";

  const [c2DocIds, setC2DocIds] = useState<string[]>([]);
  const [c2Error, setC2Error] = useState("");
  const [c2Loading, setC2Loading] = useState(false);

  const docIds = useMemo(() => {
    return isC2 ? c2DocIds : splitDocIds(rawDocIds);
  }, [isC2, c2DocIds, rawDocIds]);

  const [selectedDocIds, setSelectedDocIds] =
    useState<string[]>(docIds);

  const [isExporting, setIsExporting] = useState(false);

  useEffect(() => {
    if (!isC2) return;

    let cancelled = false;

    setC2DocIds([]);
    setSelectedDocIds([]);
    setC2Error("");

    if (
      !clientId ||
      !projectId ||
      !c2HeaderSetId ||
      !c2RecordId ||
      !c2StartDoc
    ) {
      setC2Error("C2 source identities are incomplete.");
      return;
    }

    const params = new URLSearchParams({
      client: clientId,
      project: projectId,
      header_set_id: c2HeaderSetId,
      record_id: c2RecordId,
      doc_id: c2StartDoc,
    });

    const token =
      typeof window !== "undefined"
        ? localStorage.getItem("insyt_token")
        : "";

    setC2Loading(true);

    fetch(
      `${API_BASE_URL}/api/${workspace}/cyber2/c2/record-source?${params.toString()}`,
      {
        method: "GET",
        cache: "no-store",
        headers: token
          ? { Authorization: `Bearer ${token}` }
          : {},
      }
    )
      .then(async (response) => {
        if (!response.ok) {
          throw new Error(
            `C2 source lookup failed (HTTP ${response.status}).`
          );
        }
        return response.json();
      })
      .then((result) => {
        if (cancelled) return;

        if (
          result?.status !== "ok" ||
          result?.header_set_id !== c2HeaderSetId ||
          result?.record_id !== c2RecordId ||
          result?.doc_id !== c2StartDoc ||
          !Array.isArray(result?.doc_ids) ||
          result.doc_ids.length === 0 ||
          !result.doc_ids.every(
            (id: unknown) => typeof id === "string" && !!id
          ) ||
          !result.doc_ids.includes(c2StartDoc)
        ) {
          throw new Error("Invalid verified C2 source membership.");
        }

        const ids = result.doc_ids as string[];
        setC2DocIds(ids);
        setSelectedDocIds(ids);
      })
      .catch((error) => {
        if (cancelled) return;
        setC2Error(
          error instanceof Error
            ? error.message
            : "Unable to load C2 source documents."
        );
      })
      .finally(() => {
        if (!cancelled) setC2Loading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [
    isC2,
    workspace,
    clientId,
    projectId,
    c2HeaderSetId,
    c2RecordId,
    c2StartDoc,
  ]);

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
    if (entityUid) params.set("entityUid", entityUid);

    params.set("doc", cleanDocIds[0]);

    if (isC2) {
      params.set("source", "c2");
      params.set("headerSetId", c2HeaderSetId);
      params.set("recordId", c2RecordId);
    } else {
      params.set("docSet", cleanDocIds.join(";"));
      params.set("source", "final");
    }

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

  async function exportSelectedDocs() {
    if (isC2) {
      alert("C2 source export is not available from the FINAL export handler.");
      return;
    }

    const cleanDocIds = selectedDocIds
      .map((item) => String(item || "").trim())
      .filter(Boolean);

    if (cleanDocIds.length === 0) {
      alert("Select at least one source document to export.");
      return;
    }

    const approved = window.confirm(
      [
        "Confirm Export",
        "",
        `Captured Entity: ${capturedEntity || "Unknown Entity"}`,
        `Project: ${projectId}`,
        `Selected Source Docs: ${cleanDocIds.length}`,
        "",
        "This will export the selected source documents into a ZIP package.",
        "",
        "Continue?",
      ].join("\n")
    );

    if (!approved) {
      return;
    }

    setIsExporting(true);

    try {
      const token =
        typeof window !== "undefined"
          ? localStorage.getItem("insyt_token")
          : "";

      const response = await fetch(
        `${API_BASE_URL}/api/entities/export-source-docs`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          body: JSON.stringify({
            workspace,
            client: clientId,
            project: projectId,
            entity: capturedEntity,
            entity_uid: entityUid,
            doc_ids: cleanDocIds,
            include_native: true,
            include_text: true,
          }),
        }
      );

      if (!response.ok) {
        const message = await response.text();
        throw new Error(message || "Export failed.");
      }

      const blob = await response.blob();

      const safeExportId =
        (entityUid || "final_entity")
          .replace(/[^a-z0-9_\- ]/gi, "")
          .trim()
          .replaceAll(" ", "_") || "final_entity";

      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");

      link.href = url;
      link.download = `${safeExportId}_source_docs.zip`;

      document.body.appendChild(link);
      link.click();
      link.remove();

      window.URL.revokeObjectURL(url);
    } catch (error: any) {
      console.error(error);
      alert(error?.message || "Export failed.");
    } finally {
      setIsExporting(false);
    }
  }

  if (!projectId || docIds.length === 0) {
    return (
      <AppShell>
        <PageContainer>
          <PageHeader
            title={isC2 ? "C2 Source Documents" : "Final Entity Source Documents"}
            subtitle={
              isC2
                ? c2Loading
                  ? "Loading verified C2 source documents..."
                  : c2Error || "No verified C2 source documents available."
                : "No grouped source documents were provided."
            }
          />

          <ContentCard title="Missing Source Documents">
            <p className="text-sm text-[var(--insyt-text-muted)]">
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
          title={isC2 ? "C2 Source Documents" : "Final Entity Source Documents"}
          subtitle={`Source documents associated with the selected Final entity for ${projectId.replaceAll(
            "_",
            " "
          )}.`}
        />

        <ContentCard title="Source Document Set">
          <div className="mb-4 grid grid-cols-1 gap-3 text-sm text-[var(--insyt-text-muted)] md:grid-cols-4">
            <p>
              Captured Entity:{" "}
              <span className="font-semibold text-[var(--insyt-text-primary)]">
                {capturedEntity || "Unknown Entity"}
              </span>
            </p>

            <p>
              INSYT UID:{" "}
              <span className="font-semibold text-[var(--insyt-text-primary)]">
                {entityUid || "Not available"}
              </span>
            </p>

            <p>
              Project:{" "}
              <span className="font-semibold text-[var(--insyt-text-primary)]">
                {projectId}
              </span>
            </p>

            <p>
              Source Docs:{" "}
              <span className="font-semibold text-[var(--insyt-text-primary)]">
                {docIds.length}
              </span>
            </p>
          </div>

          <div className="mb-4 rounded-xl border border-[var(--insyt-border)] bg-[var(--insyt-surface-1)] p-3">
            <p className="mb-2 text-xs uppercase tracking-wide text-[var(--insyt-text-muted)]">
              {isC2 ? "Grouped C2 Doc IDs" : "Grouped Final Doc IDs"}
            </p>

            <p className="whitespace-pre-wrap text-sm text-[var(--insyt-text-secondary)]">
              {docIds.join("; ")}
            </p>
          </div>

          <div className="mb-4 flex flex-wrap gap-2">
            <button
              type="button"
              onClick={selectAll}
              className="rounded-xl border border-[var(--insyt-border-strong)] bg-[var(--insyt-surface-2)] px-4 py-2 text-sm font-semibold text-[var(--insyt-text-secondary)] hover:bg-[var(--insyt-surface-hover)]"
            >
              Select All
            </button>

            <button
              type="button"
              onClick={clearSelection}
              className="rounded-xl border border-[var(--insyt-border-strong)] bg-[var(--insyt-surface-2)] px-4 py-2 text-sm font-semibold text-[var(--insyt-text-secondary)] hover:bg-[var(--insyt-surface-hover)]"
            >
              Clear Selection
            </button>

            <button
              type="button"
              onClick={openSelectedDocs}
              className="inline-flex h-10 min-w-[190px] items-center justify-center whitespace-nowrap rounded-full border border-sky-400/60 bg-sky-500/15 px-5 text-sm font-semibold text-sky-200 shadow-sm transition hover:-translate-y-0.5 hover:border-sky-300 hover:bg-sky-500/25 hover:text-white"
            >
              Open Review for Selected
            </button>

            <button
              type="button"
              onClick={openAllDocs}
              className="inline-flex min-h-10 items-center justify-center rounded-xl border border-emerald-600 bg-emerald-600 px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition-colors hover:border-emerald-500 hover:bg-emerald-500"
            >
              Open Review for All
            </button>

            {!isC2 && (
              <button
              type="button"
              onClick={exportSelectedDocs}
              disabled={isExporting || selectedDocIds.length === 0}
              className="inline-flex min-h-10 items-center justify-center rounded-xl border border-blue-600 bg-blue-600 px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition-colors hover:border-blue-500 hover:bg-blue-500 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {isExporting ? "Exporting..." : "Export Selected"}
              </button>
            )}
          </div>

          <p className="mb-4 text-xs text-[var(--insyt-text-muted)]">
            Selected for review/export:{" "}
            {selectedDocIds.length === 0
              ? "None"
              : selectedDocIds.join("; ")}
          </p>

          <div className="overflow-auto rounded-xl border border-[var(--insyt-border)]">
            <table className="min-w-full text-sm">
              <thead className="bg-[var(--insyt-surface-2)] text-[var(--insyt-text-muted)]">
                <tr>
                  <th className="w-12 border-b border-[var(--insyt-border)] p-3 text-left">
                    Select
                  </th>
                  <th className="border-b border-[var(--insyt-border)] p-3 text-left">
                    Doc ID
                  </th>
                  <th className="border-b border-[var(--insyt-border)] p-3 text-left">
                    Action
                  </th>
                  <th className="border-b border-[var(--insyt-border)] p-3 text-left">
                    Export
                  </th>
                </tr>
              </thead>

              <tbody>
                {docIds.map((docId, index) => (
                  <tr
                    key={`${docId}-${index}`}
                    className="border-t border-[var(--insyt-border)]"
                  >
                    <td className="p-3">
                      <input
                        type="checkbox"
                        checked={isSelected(docId)}
                        onChange={() => toggleDoc(docId)}
                        className="h-4 w-4"
                      />
                    </td>

                    <td className="p-3 font-mono text-[var(--insyt-text-secondary)]">
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

                    <td className="p-3 text-[var(--insyt-text-muted)]">
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