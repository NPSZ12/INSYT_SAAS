"use client";

import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";

import AppShell from "./AppShell";
import PageContainer from "./PageContainer";
import PageHeader from "./PageHeader";
import ContentCard from "./ContentCard";
import Button from "./Button";
import { apiGet, apiPost } from "../lib/api";

type ProcessingCenterPageProps = {
  workspace: "capture" | "discovery" | "summaries";
  title?: string;
  subtitle?: string;
};

type ProcessingFile = {
  id?: string;
  doc_id?: string;
  file_name: string;
  extension?: string;
  status: string;
  viewer_type?: string;
  preview_available?: boolean;
  uploaded_at?: string;
  started_at?: string;
  processed_at?: string;
  failed_at?: string;
  upload_path?: string;
  in_progress_path?: string;
  processed_native_path?: string;
  processed_text_path?: string;
  final_native_path?: string;
  final_text_path?: string;
  preview_pdf_path?: string;
  preview_html_path?: string;
  text_length?: number;
  ocr_applied?: boolean;
  ocr_engine?: string;
  ocr_status?: string;
  ocr_page_count?: number;
  ocr_text_length?: number;
  ocr_confidence_score?: number | null;
  ocr_quality?: string;
  ocr_warning?: string;
  error?: string;
};

type ManifestResponse = {
  client: string;
  project_id: string;
  files: ProcessingFile[];
  updated_at: string;
};

function getWorkspaceLabel(workspace: string) {
  if (workspace === "capture") return "Capture";
  if (workspace === "discovery") return "Discovery";
  if (workspace === "summaries") return "Summaries";
  return "Workspace";
}

function getStatusBadgeClass(status: string) {
  const clean = String(status || "").toLowerCase();

  if (clean === "processed") {
    return "bg-emerald-500/15 text-emerald-300 border-emerald-500/30";
  }

  if (clean === "in progress") {
    return "bg-sky-500/15 text-sky-300 border-sky-500/30";
  }

  if (clean === "uploaded") {
    return "bg-amber-500/15 text-amber-300 border-amber-500/30";
  }

  if (clean === "error") {
    return "bg-red-500/15 text-red-300 border-red-500/30";
  }

  return "bg-slate-500/15 text-slate-300 border-slate-500/30";
}

function formatDate(value?: string) {
  if (!value) return "—";

  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
}

export default function ProcessingCenterPage({
  workspace,
  title,
  subtitle,
}: ProcessingCenterPageProps) {
  const searchParams = useSearchParams();

  const workspaceLabel = getWorkspaceLabel(workspace);

  const clientId =
    searchParams.get("client") ||
    searchParams.get("clientId") ||
    "";

  const projectId =
    searchParams.get("project") ||
    searchParams.get("project_id") ||
    "";

  const [manifest, setManifest] =
    useState<ManifestResponse | null>(null);

  const [selectedFile, setSelectedFile] =
    useState<File | null>(null);

  const [isLoading, setIsLoading] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [message, setMessage] = useState("");

  const files = manifest?.files || [];

  const counts = useMemo(() => {
    return files.reduce(
      (acc, file) => {
        const status = String(file.status || "Unknown");

        if (!acc[status]) {
          acc[status] = 0;
        }

        acc[status] += 1;

        return acc;
      },
      {} as Record<string, number>
    );
  }, [files]);

  async function loadManifest() {
    if (!clientId || !projectId) return;

    setIsLoading(true);
    setMessage("");

    try {
      const data = await apiGet(
        `/api/${workspace}/processing-center/manifest?client=${encodeURIComponent(
          clientId
        )}&project_id=${encodeURIComponent(projectId)}`
      );

      setManifest(data);
    } catch (error) {
      console.error(error);
      setMessage("Unable to load Processing Center manifest.");
    } finally {
      setIsLoading(false);
    }
  }

  async function uploadFile() {
    if (!clientId || !projectId || !selectedFile) return;

    setIsUploading(true);
    setMessage("");

    try {
      const formData = new FormData();
      formData.append("client", clientId);
      formData.append("project_id", projectId);
      formData.append("file", selectedFile);

      const apiBase =
        process.env.NEXT_PUBLIC_API_BASE_URL ||
        "http://127.0.0.1:8000";

      const response = await fetch(
        `${apiBase}/api/${workspace}/processing-center/upload`,
        {
          method: "POST",
          body: formData,
        }
      );

      if (!response.ok) {
        throw new Error("Upload failed");
      }

      setSelectedFile(null);
      setMessage(`File uploaded to ${workspaceLabel} Processing Center.`);
      await loadManifest();
    } catch (error) {
      console.error(error);
      setMessage("Unable to upload file.");
    } finally {
      setIsUploading(false);
    }
  }

  async function startProcessing() {
    if (!clientId || !projectId) return;

    setIsProcessing(true);
    setMessage("");

    try {
      await apiPost(`/api/${workspace}/processing-center/start`, {
        client: clientId,
        project_id: projectId,
      });

      setMessage("Processing complete.");
      await loadManifest();
    } catch (error) {
      console.error(error);
      setMessage("Unable to start processing.");
    } finally {
      setIsProcessing(false);
    }
  }

  useEffect(() => {
    loadManifest();
  }, [clientId, projectId, workspace]);

  return (
    <AppShell>
      <PageContainer>
        <PageHeader
          title={title || `${workspaceLabel} Processing Center`}
          subtitle={
            subtitle ||
            `Upload, normalize, process, and publish documents for ${workspaceLabel} review and search.`
          }
        />

        {!clientId || !projectId ? (
          <ContentCard>
            <div className="text-sm text-red-300">
              Missing client or project in the URL.
            </div>
          </ContentCard>
        ) : null}

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-4">
          <ContentCard>
            <div className="text-sm text-slate-400">Uploaded</div>
            <div className="mt-2 text-3xl font-semibold text-white">
              {counts.Uploaded || 0}
            </div>
          </ContentCard>

          <ContentCard>
            <div className="text-sm text-slate-400">In Progress</div>
            <div className="mt-2 text-3xl font-semibold text-white">
              {counts["In Progress"] || 0}
            </div>
          </ContentCard>

          <ContentCard>
            <div className="text-sm text-slate-400">Processed</div>
            <div className="mt-2 text-3xl font-semibold text-white">
              {counts.Processed || 0}
            </div>
          </ContentCard>

          <ContentCard>
            <div className="text-sm text-slate-400">Errors</div>
            <div className="mt-2 text-3xl font-semibold text-white">
              {counts.Error || 0}
            </div>
          </ContentCard>
        </div>

        <ContentCard>
          <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <div className="text-lg font-semibold text-white">
                Upload to Processing Center
              </div>
              <div className="mt-1 text-sm text-slate-400">
                Files upload first to processing_center/uploads before
                being processed into source/native and source/text.
              </div>
            </div>

            <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
              <input
                type="file"
                onChange={(event) =>
                  setSelectedFile(event.target.files?.[0] || null)
                }
                className="rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200"
              />

              <Button
                onClick={() => {
                  if (!selectedFile || isUploading) return;
                  uploadFile();
                }}
              >
                {isUploading ? "Uploading..." : "Upload"}
              </Button>

              <Button
                onClick={() => {
                  if (isProcessing) return;
                  startProcessing();
                }}
              >
                {isProcessing ? "Processing..." : "Start Processing"}
              </Button>
            </div>
          </div>

          {message ? (
            <div className="mt-4 rounded-xl border border-slate-700 bg-slate-950 px-4 py-3 text-sm text-slate-300">
              {message}
            </div>
          ) : null}
        </ContentCard>

        <ContentCard>
          <div className="mb-4 flex items-center justify-between">
            <div>
              <div className="text-lg font-semibold text-white">
                Processing Manifest
              </div>
              <div className="mt-1 text-sm text-slate-400">
                {clientId} / {projectId}
              </div>
            </div>

            <Button
              onClick={() => {
                if (isLoading) return;
                loadManifest();
              }}
            >
              {isLoading ? "Refreshing..." : "Refresh"}
            </Button>
          </div>

          <div className="max-w-full overflow-x-auto rounded-xl border border-slate-800">
            <table className="min-w-[1600px] divide-y divide-slate-800 text-sm">
              <thead>
                <tr className="text-left text-slate-400">
                  <th className="w-64 px-3 py-3 font-medium">File</th>
                  <th className="w-56 px-3 py-3 font-medium">Doc ID</th>
                  <th className="w-32 px-3 py-3 font-medium">Extension</th>
                  <th className="w-36 px-3 py-3 font-medium">Status</th>
                  <th className="w-48 px-3 py-3 font-medium">Viewer Type</th>
                  <th className="w-40 px-3 py-3 font-medium">Preview Available</th>
                  <th className="w-36 px-3 py-3 font-medium">OCR Applied</th>
                  <th className="w-72 px-3 py-3 font-medium">OCR Engine</th>
                  <th className="w-36 px-3 py-3 font-medium">OCR Status</th>
                  <th className="w-36 px-3 py-3 font-medium">OCR Pages</th>
                  <th className="w-40 px-3 py-3 font-medium">OCR Confidence</th>
                  <th className="w-36 px-3 py-3 font-medium">OCR Quality</th>
                  <th className="w-[320px] px-3 py-3 font-medium">OCR Warning</th>
                  <th className="w-32 px-3 py-3 font-medium">Text Length</th>
                  <th className="w-56 px-3 py-3 font-medium">Processed</th>
                  <th className="w-[320px] px-3 py-3 font-medium">Final Text Path</th>
                  <th className="w-[320px] px-3 py-3 font-medium">Preview PDF Path</th>
                  <th className="w-[320px] px-3 py-3 font-medium">Preview HTML Path</th>
                  <th className="w-[260px] px-3 py-3 font-medium">Error</th>
                </tr>
              </thead>

              <tbody className="divide-y divide-slate-800">
                {files.length === 0 ? (
                  <tr>
                    <td
                      colSpan={19}
                      className="px-3 py-8 text-center text-slate-400"
                    >
                      No files have been uploaded to the Processing Center yet.
                    </td>
                  </tr>
                ) : (
                  files.map((file) => (
                    <tr key={file.id || file.file_name}>
                      <td className="px-3 py-3 text-slate-200">
                        {file.file_name}
                      </td>

                      <td className="px-3 py-3 text-slate-300">
                        {file.doc_id || "—"}
                      </td>

                      <td className="px-3 py-3 text-slate-300">
                        {file.extension || "—"}
                      </td>

                      <td className="px-3 py-3">
                        <span
                          className={`inline-flex rounded-full border px-2.5 py-1 text-xs font-medium ${getStatusBadgeClass(
                            file.status
                          )}`}
                        >
                          {file.status || "Unknown"}
                        </span>
                      </td>

                      <td className="px-3 py-3 text-slate-300">
                        {file.viewer_type || "—"}
                      </td>

                      <td className="px-3 py-3 text-slate-300">
                        {file.preview_available ? "Yes" : "No"}
                      </td>

                      <td className="px-3 py-3 text-slate-300">
                        {file.ocr_applied ? "Yes" : "No"}
                      </td>

                      <td className="px-3 py-3 text-slate-300">
                        {file.ocr_engine || "—"}
                      </td>

                      <td className="px-3 py-3 text-slate-300">
                        {file.ocr_status || "—"}
                      </td>

                      <td className="px-3 py-3 text-slate-300">
                        {typeof file.ocr_page_count === "number"
                          ? file.ocr_page_count
                          : "—"}
                      </td>

                      <td className="px-3 py-3 text-slate-300">
                        {typeof file.ocr_confidence_score === "number"
                          ? `${file.ocr_confidence_score}%`
                          : "—"}
                      </td>

                      <td className="px-3 py-3 text-slate-300">
                        {file.ocr_quality || "—"}
                      </td>

                      <td className="max-w-[320px] truncate px-3 py-3 text-amber-300">
                        {file.ocr_warning || "—"}
                      </td>

                      <td className="px-3 py-3 text-slate-300">
                        {typeof file.text_length === "number"
                          ? file.text_length
                          : "—"}
                      </td>

                      <td className="px-3 py-3 text-slate-300">
                        {formatDate(file.processed_at)}
                      </td>

                      <td className="max-w-[320px] truncate px-3 py-3 text-slate-400">
                        {file.final_text_path || "—"}
                      </td>

                      <td className="max-w-[320px] truncate px-3 py-3 text-slate-400">
                        {file.preview_pdf_path || "—"}
                      </td>

                      <td className="max-w-[320px] truncate px-3 py-3 text-slate-400">
                        {file.preview_html_path || "—"}
                      </td>

                      <td className="max-w-[260px] truncate px-3 py-3 text-red-300">
                        {file.error || "—"}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </ContentCard>
      </PageContainer>
    </AppShell>
  );
}