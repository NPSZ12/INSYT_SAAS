"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";

import AppShell from "../../../../components/AppShell";
import PageContainer from "../../../../components/PageContainer";
import PageHeader from "../../../../components/PageHeader";
import ContentCard from "../../../../components/ContentCard";
import Button from "../../../../components/Button";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000";

function UploadOverlayPageContent() {
  const searchParams = useSearchParams();
  const projectId = searchParams.get("project") || "";

  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [previewData, setPreviewData] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [overlayHistory, setOverlayHistory] = useState<any[]>([]);

  async function previewOverlay() {
    if (!selectedFile) {
      setError("Please select a DAT, CSV, or JSON overlay file.");
      return;
    }

    if (!projectId) {
      setError("No project selected. Please select a project first.");
      return;
    }

    setLoading(true);
    setError("");
    setPreviewData(null);

    try {
      const formData = new FormData();
      formData.append("project_id", projectId);
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

    if (!projectId) {
      setError("No project selected. Please select a project first.");
      return;
    }

    setLoading(true);
    setError("");

    try {
      const formData = new FormData();
      formData.append("project_id", projectId);
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

      alert(
        `Overlay imported successfully.\n\n${data.committed_record_count} records imported.`
      );

      loadOverlayHistory();
    } catch (err: any) {
      setError(err.message || "Commit failed.");
    } finally {
      setLoading(false);
    }
  }

  async function loadOverlayHistory() {
    if (!projectId) {
      return;
    }

    try {
      const response = await fetch(
        `${API_BASE_URL}/api/document-overlays/${encodeURIComponent(
          projectId
        )}/list`
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
    loadOverlayHistory();
  }, [projectId]);

  return (
    <AppShell>
      <PageContainer>
        <PageHeader
          title="Document Overlays"
          subtitle="Upload DAT, CSV, or JSON overlay files and link records by Doc ID."
        />

        <ContentCard title="Upload Overlay">
          <div className="space-y-4">
            <p className="text-sm text-slate-600">
              Project: {projectId || "No project selected"}
            </p>

            <input
              type="file"
              accept=".csv,.dat,.json"
              onChange={(event) => {
                const file = event.target.files?.[0] || null;
                setSelectedFile(file);
                setPreviewData(null);
                setError("");
              }}
            />

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
                {loading ? "Working..." : "Preview Overlay"}
              </Button>

              {previewData && (
                <Button onClick={commitOverlay}>
                  Commit Overlay
                </Button>
              )}
            </div>
          </div>
        </ContentCard>

        {previewData && (
          <ContentCard title="Overlay Summary">
            <div className="grid grid-cols-1 gap-3 text-sm text-slate-700 md:grid-cols-2">
              <p>Filename: {previewData.filename}</p>
              <p>Rows: {previewData.row_count}</p>
              <p>Doc ID Field: {previewData.detected_doc_id_field}</p>
              <p>Duplicate Doc IDs: {previewData.duplicate_doc_id_count}</p>
            </div>
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

        <ContentCard title="Overlay History">
          {overlayHistory.length === 0 ? (
            <p className="text-sm text-slate-600">
              No overlays loaded yet.
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