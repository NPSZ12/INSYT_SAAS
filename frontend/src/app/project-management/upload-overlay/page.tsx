"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";

import AppShell from "../../../components/AppShell";
import PageContainer from "../../../components/PageContainer";
import PageHeader from "../../../components/PageHeader";
import ContentCard from "../../../components/ContentCard";
import Button from "../../../components/Button";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000";

type Workspace = "capture" | "discovery" | "summaries";
type OverlayView = "raw" | "final";

const WORKSPACES: { value: Workspace; label: string }[] = [
  { value: "capture", label: "Capture" },
  { value: "discovery", label: "Discovery" },
  { value: "summaries", label: "Summaries" },
];

function getOverlayViewLabel(overlayView: OverlayView) {
  if (overlayView === "final") {
    return "Final Deliverable";
  }

  return "Raw Capture Overlay";
}

function toNameList(data: any): string[] {
  const rows =
    data?.clients ||
    data?.projects ||
    data?.items ||
    data ||
    [];

  if (!Array.isArray(rows)) {
    return [];
  }

  return rows
    .map((item) => {
      if (typeof item === "string") return item;

      return (
        item.client_name ||
        item.project_name ||
        item.project_id ||
        item.name ||
        ""
      );
    })
    .filter(Boolean);
}

function UploadOverlayPageContent() {
  const searchParams = useSearchParams();

  const initialWorkspace =
    (searchParams.get("workspace") as Workspace | null) || "capture";

  const [workspace, setWorkspace] =
    useState<Workspace>(initialWorkspace);

  const [clientId, setClientId] =
    useState(searchParams.get("client") || "");

  const [projectId, setProjectId] =
    useState(searchParams.get("project") || "");

  const [overlayView, setOverlayView] =
    useState<OverlayView>("raw");

  const [clients, setClients] = useState<string[]>([]);
  const [projects, setProjects] = useState<string[]>([]);

  const [selectedFile, setSelectedFile] =
    useState<File | null>(null);

  const [previewData, setPreviewData] = useState<any>(null);
  const [overlayHistory, setOverlayHistory] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function loadClients() {
    try {
      const response = await fetch(
        `${API_BASE_URL}/api/${workspace}/clients`
      );

      const data = await response.json();

      if (response.ok) {
        setClients(toNameList(data));
      }
    } catch {
      setClients([]);
    }
  }

  async function loadProjects() {
    if (!clientId) {
      setProjects([]);
      return;
    }

    try {
      const response = await fetch(
        `${API_BASE_URL}/api/${workspace}/clients/${encodeURIComponent(
          clientId
        )}/projects`
      );

      const data = await response.json();

      if (response.ok) {
        setProjects(toNameList(data));
      }
    } catch {
      setProjects([]);
    }
  }

  async function previewOverlay() {
    if (!selectedFile) {
      setError("Please select a DAT, CSV, or JSON file.");
      return;
    }

    if (!workspace || !clientId || !projectId) {
      setError("Select workspace, client, and project first.");
      return;
    }

    setLoading(true);
    setError("");
    setPreviewData(null);

    try {
      const formData = new FormData();

      formData.append("workspace", workspace);
      formData.append("client", clientId);
      formData.append("project_id", projectId);
      formData.append("overlay_view", overlayView);
      formData.append("file", selectedFile);

      const response = await fetch(
        `${API_BASE_URL}/api/document-overlays/preview`,
        {
          method: "POST",
          body: formData,
        }
      );

      const data = await response.json();

      if (!response.ok) {
        throw new Error(
          typeof data.detail === "string"
            ? data.detail
            : data.detail?.message || "Preview failed."
        );
      }

      setPreviewData(data);
    } catch (err: any) {
      setError(err.message || "Preview failed.");
    } finally {
      setLoading(false);
    }
  }

  async function commitOverlay() {
    if (!selectedFile) {
      setError("Please select a DAT, CSV, or JSON overlay file.");
      return;
    }

    if (!workspace || !clientId || !projectId) {
      setError("Select workspace, client, and project first.");
      return;
    }

    if (
      previewData &&
      previewData.headers_match_exactly === false
    ) {
      const missing = (
        previewData.missing_protocol_headers || []
      ).join("\n");

      const extra = (
        previewData.extra_upload_headers || []
      ).join("\n");

      const approved = window.confirm(
        [
          "Overlay headers do not exactly match the saved protocol.",
          "",
          "Missing protocol headers / not provided by upload:",
          missing || "None",
          "",
          "Extra upload headers that will be ignored:",
          extra || "None",
          "",
          "Proceed with Commit using only exact matching protocol headers?",
        ].join("\n")
      );

      if (!approved) {
        setError("Overlay commit cancelled.");
        return;
      }
    }

    setLoading(true);
    setError("");

    try {
      const formData = new FormData();

      formData.append("workspace", workspace);
      formData.append("client", clientId);
      formData.append("project_id", projectId);
      formData.append("overlay_view", overlayView);
      formData.append("file", selectedFile);

      const response = await fetch(
        `${API_BASE_URL}/api/document-overlays/commit`,
        {
          method: "POST",
          body: formData,
        }
      );

      const data = await response.json();

      if (!response.ok) {
        throw new Error(
          typeof data.detail === "string"
            ? data.detail
            : data.detail?.message || "Commit failed."
        );
      }

      if (overlayView === "final") {
        alert(
          [
            "Final deliverable imported successfully.",
            "",
            `${data.final_entity_count || data.committed_record_count} final entities imported.`,
            `${data.expanded_doc_id_count || 0} source Doc ID references detected.`,
            `${data.unique_expanded_doc_id_count || 0} unique source Doc IDs detected.`,
          ].join("\n")
        );
      } else {
        alert(
          `Raw overlay imported successfully.\n\n${data.committed_record_count} records imported.`
        );
      }

      loadOverlayHistory();
    } catch (err: any) {
      setError(err.message || "Commit failed.");
    } finally {
      setLoading(false);
    }
  }

  async function loadOverlayHistory() {
    if (!workspace || !clientId || !projectId) {
      setOverlayHistory([]);
      return;
    }

    try {
      const response = await fetch(
        `${API_BASE_URL}/api/document-overlays/${encodeURIComponent(
          projectId
        )}/list?workspace=${encodeURIComponent(
          workspace
        )}&client=${encodeURIComponent(
          clientId
        )}&overlay_view=${encodeURIComponent(overlayView)}`
      );

      const data = await response.json();

      if (response.ok) {
        setOverlayHistory(data.overlays || []);
      }
    } catch {
      setOverlayHistory([]);
    }
  }

  useEffect(() => {
    loadClients();
    setPreviewData(null);
    setOverlayHistory([]);
  }, [workspace]);

  useEffect(() => {
    loadProjects();
    setPreviewData(null);
    setOverlayHistory([]);
  }, [workspace, clientId]);

  useEffect(() => {
    loadOverlayHistory();
  }, [workspace, clientId, projectId, overlayView]);

  return (
    <AppShell>
      <PageContainer>
        <PageHeader
          title="Document Overlays"
          subtitle="Upload Raw overlays or Final deliverables for a selected workspace, client, and project."
        />

        <ContentCard title="Overlay Target">
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div>
              <p className="text-sm text-slate-600 mb-2">
                Workspace
              </p>

              <select
                value={workspace}
                onChange={(event) => {
                  setWorkspace(event.target.value as Workspace);
                  setClientId("");
                  setProjectId("");
                }}
                className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100"
              >
                {WORKSPACES.map((item) => (
                  <option key={item.value} value={item.value}>
                    {item.label}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <p className="text-sm text-slate-600 mb-2">
                Client
              </p>

              <select
                value={clientId}
                onChange={(event) => {
                  setClientId(event.target.value);
                  setProjectId("");
                }}
                className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100"
              >
                <option value="">Select client...</option>

                {clients.map((client) => (
                  <option key={client} value={client}>
                    {client}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <p className="text-sm text-slate-600 mb-2">
                Project
              </p>

              <select
                value={projectId}
                onChange={(event) => setProjectId(event.target.value)}
                className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100"
              >
                <option value="">Select project...</option>

                {projects.map((project) => (
                  <option key={project} value={project}>
                    {project}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <p className="text-sm text-slate-600 mb-2">
                Overlay Target
              </p>

              <select
                value={overlayView}
                onChange={(event) => {
                  setOverlayView(event.target.value as OverlayView);
                  setPreviewData(null);
                  setError("");
                }}
                className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100"
              >
                <option value="raw">Raw Capture Overlay</option>
                <option value="final">Final Deliverable</option>
              </select>
            </div>
          </div>
        </ContentCard>

        <ContentCard title="Upload Overlay">
          <div className="space-y-4">
            <p className="text-sm text-slate-600">
              Selected upload type:{" "}
              <span className="font-semibold text-slate-800">
                {getOverlayViewLabel(overlayView)}
              </span>
            </p>

            <p className="text-sm text-slate-600">
              Selected path:{" "}
              {clientId && projectId
                ? `${clientId} / ${projectId} / overlays / ${overlayView}`
                : "Select workspace, client, and project"}
            </p>

            <div>
              <input
                id="overlay-file-input"
                type="file"
                accept=".csv,.dat,.json"
                className="hidden"
                onChange={(event) => {
                  const file = event.target.files?.[0] || null;
                  setSelectedFile(file);
                  setPreviewData(null);
                  setError("");
                }}
              />

              <label
                htmlFor="overlay-file-input"
                className="inline-flex cursor-pointer items-center justify-center rounded-xl bg-slate-700 px-4 py-3 text-sm font-semibold text-white transition hover:bg-slate-600"
              >
                Select File
              </label>
            </div>

            {selectedFile && (
              <p className="text-sm text-slate-600">
                Selected file: {selectedFile.name}
              </p>
            )}

            {error && (
              <p className="text-sm font-medium text-red-600">
                {error}
              </p>
            )}

            <div className="flex gap-2">
              <Button onClick={previewOverlay}>
                {loading
                  ? "Working..."
                  : overlayView === "final"
                    ? "Preview Final Deliverable"
                    : "Preview Raw Overlay"}
              </Button>

              {previewData && (
                <Button onClick={() => commitOverlay()}>
                  {overlayView === "final"
                    ? "Commit Final Deliverable"
                    : previewData?.headers_match_exactly === false
                      ? "Proceed with Commit"
                      : "Commit Raw Overlay"}
                </Button>
              )}
            </div>
          </div>
        </ContentCard>

        {previewData && (
          <ContentCard title={`${getOverlayViewLabel(overlayView)} Summary`}>
            <div className="grid grid-cols-1 gap-3 text-sm text-slate-700 md:grid-cols-2">
              <p>Filename: {previewData.filename}</p>
              <p>Rows: {previewData.row_count}</p>
              <p>Doc ID Field: {previewData.detected_doc_id_field}</p>

              {overlayView === "final" ? (
                <>
                  <p>Final Entities: {previewData.final_entity_count}</p>
                  <p>
                    Source Doc ID References:{" "}
                    {previewData.expanded_doc_id_count}
                  </p>
                  <p>
                    Unique Source Doc IDs:{" "}
                    {previewData.unique_expanded_doc_id_count}
                  </p>
                  <p>
                    Repeated Source Doc IDs:{" "}
                    {previewData.repeated_final_source_doc_id_count || 0}
                  </p>
                  <p>Matched Source Docs: {previewData.matched_doc_id_count}</p>
                  <p>
                    Unmatched Source Docs:{" "}
                    {previewData.unmatched_overlay_doc_id_count}
                  </p>
                </>
              ) : (
                <>
                  <p>Duplicate Doc IDs: {previewData.duplicate_doc_id_count}</p>
                  <p>Protocol Headers: {previewData.protocol_header_count}</p>
                  <p>
                    Headers Match:{" "}
                    {previewData.headers_match_exactly ? "Yes" : "No"}
                  </p>
                  <p>Matched Doc IDs: {previewData.matched_doc_id_count}</p>
                  <p>
                    Unmatched Overlay Doc IDs:{" "}
                    {previewData.unmatched_overlay_doc_id_count}
                  </p>
                </>
              )}
            </div>

            {overlayView === "final" && previewData.final_header_validation_note && (
              <p className="mt-4 rounded-xl border border-cyan-800 bg-cyan-950/40 p-3 text-sm text-cyan-100">
                {previewData.final_header_validation_note}
              </p>
            )}

            {overlayView === "final" &&
              previewData.expanded_doc_ids_sample?.length > 0 && (
                <div className="mt-4 text-sm">
                  <p className="mb-2 font-semibold text-slate-700">
                    Sample Source Doc IDs
                  </p>

                  <pre className="max-h-40 overflow-auto whitespace-pre-wrap rounded-xl border border-slate-800 bg-slate-950 p-3 text-xs text-slate-100">
                    {previewData.expanded_doc_ids_sample.join("\n")}
                  </pre>
                </div>
              )}

            {overlayView !== "final" && !previewData.headers_match_exactly && (
              <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
                <div>
                  <p className="font-semibold text-red-600 mb-2">
                    Missing Protocol Headers
                  </p>
                  <pre className="whitespace-pre-wrap text-slate-600">
                    {(previewData.missing_protocol_headers || []).join("\n") ||
                      "None"}
                  </pre>
                </div>

                <div>
                  <p className="font-semibold text-red-600 mb-2">
                    Extra Upload Headers
                  </p>
                  <pre className="whitespace-pre-wrap text-slate-600">
                    {(previewData.extra_upload_headers || []).join("\n") ||
                      "None"}
                  </pre>
                </div>
              </div>
            )}
          </ContentCard>
        )}

        {previewData?.preview_rows?.length > 0 && (
          <ContentCard title="Preview Data">
            <div className="overflow-auto">
              <table className="min-w-full text-sm">
                <thead>
                  <tr>
                    {previewData.headers
                      .slice(0, 10)
                      .map((header: string) => (
                        <th
                          key={header}
                          className="border-b p-2 text-left"
                        >
                          {header}
                        </th>
                      ))}
                  </tr>
                </thead>

                <tbody>
                  {previewData.preview_rows.map(
                    (row: any, index: number) => (
                      <tr key={index}>
                        {previewData.headers
                          .slice(0, 10)
                          .map((header: string) => (
                            <td
                              key={header}
                              className="border-b p-2"
                            >
                              {String(row.metadata?.[header] ?? "")}
                            </td>
                          ))}
                      </tr>
                    )
                  )}
                </tbody>
              </table>
            </div>
          </ContentCard>
        )}

        <ContentCard title={`${getOverlayViewLabel(overlayView)} History`}>
          {overlayHistory.length === 0 ? (
            <p className="text-sm text-slate-600">
              No files loaded yet for this upload type.
            </p>
          ) : (
            <div className="overflow-auto">
              <table className="min-w-full text-sm">
                <thead>
                  <tr>
                    <th className="border-b p-2 text-left">
                      Overlay File
                    </th>
                    <th className="border-b p-2 text-left">
                      Size
                    </th>
                    <th className="border-b p-2 text-left">
                      Last Modified
                    </th>
                  </tr>
                </thead>

                <tbody>
                  {overlayHistory.map((overlay: any) => (
                    <tr key={overlay.name}>
                      <td className="border-b p-2">
                        {overlay.name}
                      </td>
                      <td className="border-b p-2">
                        {overlay.size}
                      </td>
                      <td className="border-b p-2">
                        {overlay.last_modified}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </ContentCard>
      </PageContainer>
    </AppShell>
  );
}

export default function UploadOverlayPage() {
  return (
    <Suspense fallback={null}>
      <UploadOverlayPageContent />
    </Suspense>
  );
}