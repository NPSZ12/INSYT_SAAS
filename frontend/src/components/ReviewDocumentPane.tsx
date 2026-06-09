"use client";

import { useEffect, useState } from "react";
import { usePathname, useSearchParams } from "next/navigation";
import dynamic from "next/dynamic";

import Button from "./Button";
import { apiGet } from "../lib/api";

const PdfDocumentViewer = dynamic(
  () => import("./PdfDocumentViewer"),
  {
    ssr: false,
  }
);

type ReviewDocumentPaneProps = {
  text: string;
  nativeUrl?: string;
  nativeBlob?: string;
  targetPage?: number | null;
};

type NativePreviewResponse = {
  file_name: string;
  extension: string;
  preview_type: "table" | "text" | "pdf" | "unsupported";
  sheets?: string[];
  active_sheet?: string;
  columns?: string[];
  rows?: Record<string, string>[];
  text?: string;
  message?: string;
  row_count_previewed?: number;
  total_columns?: number;
};

type ReviewPreviewResponse = {
  workspace: string;
  client: string;
  project: string;
  doc_id: string;
  file_name: string;
  extension: string;
  viewer_type:
    | "pdf"
    | "image"
    | "text"
    | "html"
    | "email"
    | "needs_preview_conversion"
    | "unsupported";
  preview_available: boolean;
  viewer_url: string;
  native_url: string;
  text_url: string;
  native_path: string;
  text_path: string;
  preview_pdf_path: string;
  preview_html_path: string;
  preview_pdf_url: string;
  preview_html_url: string;
};


function getExtension(
  nativeBlob?: string,
  nativeUrl?: string
) {
  const source = nativeBlob || nativeUrl || "";

  const clean = source
    .split("?")[0]
    .toLowerCase();

  const parts = clean.split(".");

  return parts.length > 1
    ? parts.pop() || ""
    : "";
}

function getDocIdFromBlob(nativeBlob?: string) {
  const fileName =
    String(nativeBlob || "")
      .split("/")
      .pop() || "";

  if (!fileName) return "";

  const parts = fileName.split(".");

  if (parts.length <= 1) return fileName;

  parts.pop();

  return parts.join(".");
}

function getWorkspaceFromPath(pathname: string) {
  if (pathname.startsWith("/summaries")) {
    return "summaries";
  }

  if (pathname.startsWith("/discovery")) {
    return "discovery";
  }

  return "capture";
}

function isBackendPreviewSupported(extension: string) {
  return [
    "csv",
    "tsv",
    "xlsx",
    "xls",
    "xlsm",
    "docx",
    "txt",
    "log",
    "json",
    "xml",
    "html",
    "htm",
  ].includes(extension);
}

function NativeTablePreview({
  preview,
  selectedSheet,
  onSheetChange,
}: {
  preview: NativePreviewResponse;
  selectedSheet: string;
  onSheetChange: (sheet: string) => void;
}) {
  const columns = preview.columns || [];
  const rows = preview.rows || [];
  const sheets = preview.sheets || [];

  return (
    <div className="h-full w-full overflow-hidden rounded-xl border border-slate-800 bg-slate-950 flex flex-col">
      <div className="shrink-0 border-b border-slate-800 bg-slate-900 px-4 py-3 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div>
          <p className="text-sm font-semibold text-slate-100">
            {preview.file_name}
          </p>

          <p className="text-xs text-slate-500 mt-1">
            Previewing {preview.row_count_previewed || rows.length} rows
            {preview.total_columns
              ? ` across ${preview.total_columns} columns`
              : ""}
          </p>
        </div>

        {sheets.length > 0 && (
          <select
            value={selectedSheet}
            onChange={(event) =>
              onSheetChange(event.target.value)
            }
            className="bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200"
          >
            {sheets.map((sheet) => (
              <option key={sheet} value={sheet}>
                {sheet}
              </option>
            ))}
          </select>
        )}
      </div>

      <div className="flex-1 min-h-0 overflow-auto">
        <table className="min-w-full border-collapse text-sm">
          <thead className="sticky top-0 z-10 bg-slate-900">
            <tr>
              {columns.map((column) => (
                <th
                  key={column}
                  className="border-b border-r border-slate-800 px-3 py-2 text-left text-xs font-semibold text-slate-300 whitespace-nowrap"
                >
                  {column}
                </th>
              ))}
            </tr>
          </thead>

          <tbody>
            {rows.map((row, rowIndex) => (
              <tr
                key={rowIndex}
                className={
                  rowIndex % 2 === 0
                    ? "bg-slate-950"
                    : "bg-slate-900/60"
                }
              >
                {columns.map((column) => (
                  <td
                    key={`${rowIndex}-${column}`}
                    className="border-b border-r border-slate-900 px-3 py-2 text-slate-300 align-top whitespace-nowrap max-w-[360px] overflow-hidden text-ellipsis"
                    title={row[column] || ""}
                  >
                    {row[column] || ""}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>

        {rows.length === 0 && (
          <div className="p-6 text-sm text-slate-500">
            No preview rows found.
          </div>
        )}
      </div>
    </div>
  );
}

function NativeTextPreview({
  preview,
}: {
  preview: NativePreviewResponse;
}) {
  return (
    <div className="h-full w-full overflow-hidden rounded-xl border border-slate-800 bg-slate-950">
      <div className="h-full w-full overflow-auto p-5">
        <pre className="m-0 whitespace-pre-wrap break-words text-sm leading-7 text-slate-300 font-sans">
          {preview.text || preview.message || "No preview text available."}
        </pre>
      </div>
    </div>
  );
}

export default function ReviewDocumentPane({
  text,
  nativeUrl,
  nativeBlob,
  targetPage,
}: ReviewDocumentPaneProps) {
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const [viewMode, setViewMode] =
    useState<"text" | "native">("native");

  const [reviewPreview, setReviewPreview] =
    useState<ReviewPreviewResponse | null>(null);

  const [reviewPreviewLoading, setReviewPreviewLoading] =
    useState(false);

  const [reviewPreviewError, setReviewPreviewError] =
    useState("");

  const [preview, setPreview] =
    useState<NativePreviewResponse | null>(null);

  const [previewLoading, setPreviewLoading] =
    useState(false);

  const [previewError, setPreviewError] =
    useState("");

  const [selectedSheet, setSelectedSheet] =
    useState("");

  const extension = getExtension(
    nativeBlob,
    nativeUrl
  );

  const workspace = getWorkspaceFromPath(pathname);

  const clientId =
    searchParams.get("client") ||
    searchParams.get("clientId") ||
    "";

  const projectId =
    searchParams.get("project") ||
    searchParams.get("project_id") ||
    "";

  const docId =
    searchParams.get("doc") ||
    getDocIdFromBlob(nativeBlob);

  const isPdf = extension === "pdf";

  const canUseBackendPreview =
    Boolean(nativeBlob) &&
    !isPdf &&
    isBackendPreviewSupported(extension);

  useEffect(() => {
    if (!clientId || !projectId || !docId) {
      setReviewPreview(null);
      return;
    }

    setReviewPreviewLoading(true);
    setReviewPreviewError("");

    const params = new URLSearchParams({
      client: clientId,
      project: projectId,
      doc: docId,
    });

    apiGet(`/api/${workspace}/review/preview?${params.toString()}`)
      .then((response: ReviewPreviewResponse) => {
        setReviewPreview(response);
      })
      .catch((error) => {
        console.error(error);
        setReviewPreviewError("Unable to load review preview metadata.");
        setReviewPreview(null);
      })
      .finally(() => {
        setReviewPreviewLoading(false);
      });
  }, [workspace, clientId, projectId, docId]);

  const effectiveViewerType =
    reviewPreview?.viewer_type ||
    (isPdf ? "pdf" : canUseBackendPreview ? "legacy_preview" : "unsupported");

  const effectiveViewerUrl =
    reviewPreview?.viewer_url ||
    nativeUrl ||
    "";

  const effectiveNativeUrl =
    reviewPreview?.native_url ||
    nativeUrl ||
    "";

  const effectiveExtension =
    reviewPreview?.extension?.replace(".", "") ||
    extension;

  useEffect(() => {
    if (
      viewMode !== "native" ||
      !canUseBackendPreview ||
      !nativeBlob
    ) {
      return;
    }

    const params = new URLSearchParams({
      blob_path: nativeBlob,
      limit: "100",
    });

    if (selectedSheet) {
      params.set("sheet_name", selectedSheet);
    }

    setPreviewLoading(true);
    setPreviewError("");

    apiGet(`/api/${workspace}/native-preview?${params.toString()}`)
      .then((response: NativePreviewResponse) => {
        setPreview(response);

        if (
          response.active_sheet &&
          response.active_sheet !== selectedSheet
        ) {
          setSelectedSheet(response.active_sheet);
        }
      })
      .catch((error) => {
        console.error(error);
        setPreviewError("Unable to load native preview.");
      })
      .finally(() => {
        setPreviewLoading(false);
      });
  }, [
    viewMode,
    workspace,
    nativeBlob,
    selectedSheet,
    canUseBackendPreview,
  ]);

  return (
    <div className="col-span-2 bg-slate-900 border border-slate-800 rounded-2xl p-6 h-[calc(100vh-24px)] min-h-[980px] max-h-[calc(100vh-24px)] flex flex-col overflow-hidden">
      <div className="shrink-0 flex items-center justify-between mb-4">
        <div>
          <h2 className="text-lg font-semibold">
            Document Viewer
          </h2>

          <p className="text-xs text-slate-500 mt-1">
            {viewMode === "text"
              ? "Extracted Text"
              : nativeBlob || "Native Document"}
          </p>
        </div>

        <div className="flex gap-3">
          <Button
            variant={
              viewMode === "text"
                ? "primary"
                : "secondary"
            }
            onClick={() => setViewMode("text")}
          >
            Text
          </Button>

          <Button
            variant={
              viewMode === "native"
                ? "primary"
                : "secondary"
            }
            onClick={() => setViewMode("native")}
          >
            Native
          </Button>
        </div>
      </div>

      <div className="flex-1 min-h-0 overflow-hidden">
        {viewMode === "text" && (
          <div className="h-full w-full overflow-hidden rounded-xl border border-slate-800 bg-slate-950">
            <div className="h-full w-full overflow-auto p-5">
              <pre className="m-0 whitespace-pre-wrap break-words text-sm leading-7 text-slate-300 font-sans">
                {text || "No extracted text available."}
              </pre>
            </div>
          </div>
        )}

        {viewMode === "native" && (
          <>
            {reviewPreviewLoading && (
              <div className="h-full w-full rounded-xl border border-slate-800 bg-slate-950 flex items-center justify-center text-slate-400">
                Loading document viewer...
              </div>
            )}

            {!reviewPreviewLoading && reviewPreviewError && (
              <div className="h-full w-full rounded-xl border border-slate-800 bg-slate-950 flex flex-col items-center justify-center p-8 text-center">
                <p className="text-rose-300 font-semibold mb-2">
                  Viewer metadata failed
                </p>

                <p className="text-slate-500">
                  {reviewPreviewError}
                </p>
              </div>
            )}

            {!reviewPreviewLoading &&
              !reviewPreviewError &&
              effectiveViewerType === "pdf" && (
                <div className="h-full w-full overflow-hidden rounded-xl border border-slate-800 bg-slate-950">
                  <PdfDocumentViewer
                    fileUrl={effectiveViewerUrl}
                    heightClassName="h-full"
                    targetPage={targetPage}
                  />
                </div>
              )}

            {!reviewPreviewLoading &&
              !reviewPreviewError &&
              effectiveViewerType === "image" && (
                <div className="h-full w-full overflow-auto rounded-xl border border-slate-800 bg-slate-950 p-4">
                  <img
                    src={effectiveViewerUrl}
                    alt={reviewPreview?.file_name || "Native image"}
                    className="mx-auto max-h-full max-w-full rounded-lg object-contain"
                  />
                </div>
              )}

            {!reviewPreviewLoading &&
              !reviewPreviewError &&
              effectiveViewerType === "html" && (
                <div className="h-full w-full overflow-hidden rounded-xl border border-slate-800 bg-slate-950">
                  <iframe
                    src={effectiveViewerUrl}
                    className="h-full w-full bg-white"
                    title={reviewPreview?.file_name || "HTML Preview"}
                  />
                </div>
              )}

            {!reviewPreviewLoading &&
              !reviewPreviewError &&
              effectiveViewerType === "text" && (
                <>
                  {text ? (
                    <div className="h-full w-full overflow-hidden rounded-xl border border-slate-800 bg-slate-950">
                      <div className="h-full w-full overflow-auto p-5">
                        <pre className="m-0 whitespace-pre-wrap break-words text-sm leading-7 text-slate-300 font-sans">
                          {text}
                        </pre>
                      </div>
                    </div>
                  ) : effectiveViewerUrl ? (
                    <div className="h-full w-full overflow-hidden rounded-xl border border-slate-800 bg-slate-950">
                      <iframe
                        src={effectiveViewerUrl}
                        className="h-full w-full bg-white"
                        title={reviewPreview?.file_name || "Text Preview"}
                      />
                    </div>
                  ) : (
                    <NativeTextPreview
                      preview={{
                        file_name: reviewPreview?.file_name || "Text Preview",
                        extension: effectiveExtension,
                        preview_type: "text",
                        text: "No extracted text available.",
                      }}
                    />
                  )}
                </>
              )}

            {!reviewPreviewLoading &&
              !reviewPreviewError &&
              effectiveViewerType === "email" && (
                <>
                  {text ? (
                    <NativeTextPreview
                      preview={{
                        file_name: reviewPreview?.file_name || "Email Preview",
                        extension: effectiveExtension,
                        preview_type: "text",
                        text,
                      }}
                    />
                  ) : effectiveViewerUrl ? (
                    <div className="h-full w-full overflow-hidden rounded-xl border border-slate-800 bg-slate-950">
                      <iframe
                        src={effectiveViewerUrl}
                        className="h-full w-full bg-white"
                        title={reviewPreview?.file_name || "Email Preview"}
                      />
                    </div>
                  ) : (
                    <div className="h-full w-full rounded-xl border border-slate-800 bg-slate-950 flex flex-col items-center justify-center p-8 text-center">
                      <h3 className="text-xl font-semibold text-white mb-3">
                        Email Preview Not Yet Converted
                      </h3>

                      <p className="text-slate-400 mb-6">
                        This email file has not yet been converted into a browser preview.
                      </p>

                      {effectiveNativeUrl ? (
                        <a
                          href={effectiveNativeUrl}
                          target="_blank"
                          rel="noreferrer"
                          className="inline-flex items-center justify-center rounded-xl bg-sky-600 hover:bg-sky-500 text-white px-5 py-3 transition"
                        >
                          Open / Download Native File
                        </a>
                      ) : null}
                    </div>
                  )}
                </>
              )}

            {!reviewPreviewLoading &&
              !reviewPreviewError &&
              effectiveViewerType === "needs_preview_conversion" &&
              canUseBackendPreview && (
                <>
                  {previewLoading && (
                    <div className="h-full w-full rounded-xl border border-slate-800 bg-slate-950 flex items-center justify-center text-slate-400">
                      Loading native preview...
                    </div>
                  )}

                  {!previewLoading && previewError && (
                    <div className="h-full w-full rounded-xl border border-slate-800 bg-slate-950 flex flex-col items-center justify-center p-8 text-center">
                      <p className="text-rose-300 font-semibold mb-2">
                        Preview failed
                      </p>

                      <p className="text-slate-500">
                        {previewError}
                      </p>
                    </div>
                  )}

                  {!previewLoading &&
                    !previewError &&
                    preview?.preview_type === "table" && (
                      <NativeTablePreview
                        preview={preview}
                        selectedSheet={
                          selectedSheet ||
                          preview.active_sheet ||
                          ""
                        }
                        onSheetChange={setSelectedSheet}
                      />
                    )}

                  {!previewLoading &&
                    !previewError &&
                    preview?.preview_type === "text" && (
                      <NativeTextPreview preview={preview} />
                    )}

                  {!previewLoading &&
                    !previewError &&
                    preview?.preview_type === "unsupported" && (
                      <div className="h-full w-full rounded-xl border border-slate-800 bg-slate-950 flex flex-col items-center justify-center p-8 text-center">
                        <div className="max-w-lg">
                          <h3 className="text-xl font-semibold text-white mb-3">
                            Native File Preview Not Yet Supported
                          </h3>

                          <p className="text-slate-400 mb-6">
                            {preview.message ||
                              "This file type cannot yet be rendered directly in-browser."}
                          </p>

                          {effectiveNativeUrl ? (
                            <a
                              href={effectiveNativeUrl}
                              target="_blank"
                              rel="noreferrer"
                              className="inline-flex items-center justify-center rounded-xl bg-sky-600 hover:bg-sky-500 text-white px-5 py-3 transition"
                            >
                              Open / Download Native File
                            </a>
                          ) : null}
                        </div>
                      </div>
                    )}
                </>
              )}

            {!reviewPreviewLoading &&
              !reviewPreviewError &&
              effectiveViewerType === "needs_preview_conversion" &&
              !canUseBackendPreview && (
                <div className="h-full w-full rounded-xl border border-slate-800 bg-slate-950 flex flex-col items-center justify-center p-8 text-center">
                  <div className="max-w-lg">
                    <h3 className="text-xl font-semibold text-white mb-3">
                      Preview Conversion Needed
                    </h3>

                    <p className="text-slate-400 mb-6">
                      This file type needs a generated PDF or HTML preview before it can be rendered directly in-browser.
                    </p>

                    <div className="bg-slate-900 border border-slate-800 rounded-xl px-4 py-3 text-sm text-slate-300 mb-6">
                      Extension:{" "}
                      <span className="text-sky-400 font-semibold">
                        {effectiveExtension || "Unknown"}
                      </span>
                    </div>

                    {effectiveNativeUrl ? (
                      <a
                        href={effectiveNativeUrl}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center justify-center rounded-xl bg-sky-600 hover:bg-sky-500 text-white px-5 py-3 transition"
                      >
                        Open / Download Native File
                      </a>
                    ) : null}
                  </div>
                </div>
              )}

            {!reviewPreviewLoading &&
              !reviewPreviewError &&
              effectiveViewerType === "unsupported" && (
                <div className="h-full w-full rounded-xl border border-slate-800 bg-slate-950 flex flex-col items-center justify-center p-8 text-center">
                  <div className="max-w-lg">
                    <h3 className="text-xl font-semibold text-white mb-3">
                      Native File Preview Not Yet Supported
                    </h3>

                    <p className="text-slate-400 mb-6">
                      This file type cannot yet be rendered directly in-browser.
                    </p>

                    <div className="bg-slate-900 border border-slate-800 rounded-xl px-4 py-3 text-sm text-slate-300 mb-6">
                      Extension:{" "}
                      <span className="text-sky-400 font-semibold">
                        {effectiveExtension || "Unknown"}
                      </span>
                    </div>

                    {effectiveNativeUrl ? (
                      <a
                        href={effectiveNativeUrl}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center justify-center rounded-xl bg-sky-600 hover:bg-sky-500 text-white px-5 py-3 transition"
                      >
                        Open / Download Native File
                      </a>
                    ) : (
                      <p className="text-slate-500">
                        Native file unavailable.
                      </p>
                    )}
                  </div>
                </div>
              )}
          </>
        )}
      </div>
    </div>
  );
}