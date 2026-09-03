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

type DetectionHit = {
  entity_type: string;
  entity_subtype?: string;
  detected_value?: string;
  confidence?: number;
  start_offset: number;
  end_offset: number;
  protocol?: string;
  detector?: string;
  reportability?: string;
};

type ReviewDocumentPaneProps = {
  text: string;
  nativeUrl?: string;
  nativeBlob?: string;
  targetPage?: number | null;
  detectionHits?: DetectionHit[];
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
    <div className="flex h-full w-full flex-col overflow-hidden rounded-xl border border-[var(--insyt-border)] bg-[var(--insyt-surface-1)]">
      <div className="flex shrink-0 flex-col gap-3 border-b border-[var(--insyt-border)] bg-[var(--insyt-surface-2)] px-4 py-3 md:flex-row md:items-center md:justify-between">
        <div>
          <p className="text-sm font-semibold text-[var(--insyt-text-primary)]">
            {preview.file_name}
          </p>

          <p className="mt-1 text-xs text-[var(--insyt-text-muted)]">
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
            className="insyt-control rounded-lg px-3 py-2 text-sm"
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
          <thead className="sticky top-0 z-10 bg-[var(--insyt-surface-2)]">
            <tr>
              {columns.map((column) => (
                <th
                  key={column}
                  className="whitespace-nowrap border-b border-r border-[var(--insyt-border)] px-3 py-2 text-left text-xs font-semibold text-[var(--insyt-text-secondary)]"
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
                    ? "bg-[var(--insyt-surface-1)]"
                    : "bg-[var(--insyt-surface-2)]"
                }
              >
                {columns.map((column) => (
                  <td
                    key={`${rowIndex}-${column}`}
                    className="max-w-[360px] whitespace-nowrap border-b border-r border-[var(--insyt-border)] px-3 py-2 align-top text-[var(--insyt-text-secondary)] overflow-hidden text-ellipsis"
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
          <div className="p-6 text-sm text-[var(--insyt-text-muted)]">
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
    <div className="h-full w-full overflow-hidden rounded-xl border border-[var(--insyt-border)] bg-[var(--insyt-surface-1)]">
      <div className="h-full w-full overflow-auto p-5">
        <pre className="m-0 whitespace-pre-wrap break-words font-sans text-sm leading-7 text-[var(--insyt-text-secondary)]">
          {preview.text || preview.message || "No preview text available."}
        </pre>
      </div>
    </div>
  );
}

function renderHighlightedText(
  text: string,
  hits: DetectionHit[]
) {
  if (!text || !hits.length) {
    return text;
  }

  const normalizeComparable = (
    value: string
  ) =>
    String(value || "")
      .replace(/\r\n/g, "\n")
      .replace(/\r/g, "\n");

  const resolveHitOffsets = (
    hit: DetectionHit
  ) => {
    let start = Number(
      hit.start_offset
    );

    let end = Number(
      hit.end_offset
    );

    if (
      !Number.isFinite(start) ||
      !Number.isFinite(end) ||
      start < 0 ||
      end <= start
    ) {
      return null;
    }

    start = Math.max(
      0,
      Math.min(
        text.length,
        start
      )
    );

    end = Math.max(
      start,
      Math.min(
        text.length,
        end
      )
    );

    const detectedValue =
      String(
        hit.detected_value ||
          ""
      );

    if (!detectedValue) {
      return {
        ...hit,
        start_offset: start,
        end_offset: end,
      };
    }

    const expectedSlice =
      text.slice(
        start,
        end
      );

    /*
     * Fast path:
     * stored offsets already point to the exact detected value.
     */
    if (
      normalizeComparable(
        expectedSlice
      ) ===
      normalizeComparable(
        detectedValue
      )
    ) {
      return {
        ...hit,
        start_offset: start,
        end_offset: end,
      };
    }

    /*
     * The viewer text can differ slightly from the Detection text
     * because of OCR/newline/text normalization.
     *
     * Search only near the expected location so that a repeated
     * value elsewhere in the document is not accidentally used.
     */
    const SEARCH_RADIUS = 120;

    const windowStart =
      Math.max(
        0,
        start - SEARCH_RADIUS
      );

    const windowEnd =
      Math.min(
        text.length,
        Math.max(
          end,
          start +
            detectedValue.length
        ) +
          SEARCH_RADIUS
      );

    const searchWindow =
      text.slice(
        windowStart,
        windowEnd
      );

    /*
     * First try an exact case-sensitive match.
     */
    let localIndex =
      searchWindow.indexOf(
        detectedValue
      );

    /*
     * OCR output can occasionally differ in case only.
     */
    if (localIndex < 0) {
      localIndex =
        searchWindow
          .toLocaleLowerCase()
          .indexOf(
            detectedValue
              .toLocaleLowerCase()
          );
    }

    if (localIndex >= 0) {
      const correctedStart =
        windowStart +
        localIndex;

      const correctedEnd =
        correctedStart +
        detectedValue.length;

      return {
        ...hit,
        start_offset:
          correctedStart,
        end_offset:
          correctedEnd,
      };
    }

    /*
     * If the value cannot safely be relocated, retain the original
     * offsets rather than guessing.
     */
    return {
      ...hit,
      start_offset: start,
      end_offset: end,
    };
  };

  const validHits = hits
    .map(resolveHitOffsets)
    .filter(
      (
        hit
      ): hit is DetectionHit =>
        Boolean(hit)
    )
    .filter((hit) => {
      const start =
        Number(
          hit.start_offset
        );

      const end =
        Number(
          hit.end_offset
        );

      return (
        Number.isFinite(start) &&
        Number.isFinite(end) &&
        start >= 0 &&
        end > start &&
        start < text.length
      );
    })
    .map((hit) => ({
      ...hit,
      start_offset:
        Math.max(
          0,
          Number(
            hit.start_offset
          )
        ),
      end_offset:
        Math.min(
          text.length,
          Number(
            hit.end_offset
          )
        ),
    }))
    .sort((a, b) => {
      if (
        a.start_offset !==
        b.start_offset
      ) {
        return (
          a.start_offset -
          b.start_offset
        );
      }

      return (
        b.end_offset -
        a.end_offset
      );
    });

  if (!validHits.length) {
    return text;
  }

  const parts:
    React.ReactNode[] = [];

  let cursor = 0;

  validHits.forEach(
    (hit, index) => {
      /*
       * Skip a hit that is fully inside an already-rendered hit.
       */
      if (
        hit.start_offset <
        cursor
      ) {
        return;
      }

      if (
        hit.start_offset >
        cursor
      ) {
        parts.push(
          <span
            key={`plain-${index}`}
          >
            {text.slice(
              cursor,
              hit.start_offset
            )}
          </span>
        );
      }

      const highlightedText =
        text.slice(
          hit.start_offset,
          hit.end_offset
        );

      const confidence =
        typeof hit.confidence ===
        "number"
          ? `${Math.round(
              hit.confidence *
                100
            )}%`
          : "";

      const tooltip = [
        hit.entity_type,
        hit.entity_subtype,
        confidence
          ? `Confidence ${confidence}`
          : "",
        hit.protocol,
      ]
        .filter(Boolean)
        .join(" · ");

      parts.push(
        <mark
          key={`hit-${index}`}
          title={tooltip}
          className="rounded-sm bg-amber-300 px-0.5 text-slate-950 ring-1 ring-amber-400/70"
        >
          {highlightedText}
        </mark>
      );

      cursor =
        hit.end_offset;
    }
  );

  if (
    cursor <
    text.length
  ) {
    parts.push(
      <span key="plain-final">
        {text.slice(cursor)}
      </span>
    );
  }

  return parts;
}

export default function ReviewDocumentPane({
  text,
  nativeUrl,
  nativeBlob,
  targetPage,
  detectionHits = [],
}: ReviewDocumentPaneProps) {
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const [viewMode, setViewMode] =
    useState<"text" | "native">("native");

  const [showDetectionHighlights, setShowDetectionHighlights] =
  useState(true);

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
    <div className="insyt-panel col-span-2 flex h-[calc(100vh-24px)] min-h-[980px] max-h-[calc(100vh-24px)] flex-col overflow-hidden p-6">
      <div className="shrink-0 flex items-center justify-between mb-4">
        <div>
          <h2 className="insyt-section-title text-lg text-[var(--insyt-text-primary)]">
            Document Viewer
          </h2>

          <p className="mt-1 text-xs text-[var(--insyt-text-muted)]">
            {viewMode === "text"
              ? "Extracted Text"
              : nativeBlob || "Native Document"}
          </p>
        </div>

        <div className="flex items-center gap-3">
          {viewMode === "text" && detectionHits.length > 0 && (
            <button
              type="button"
              onClick={() =>
                setShowDetectionHighlights((current) => !current)
              }
              className={
                showDetectionHighlights
                  ? "rounded-lg border border-amber-400/60 bg-amber-400/10 px-3 py-2 text-xs font-semibold text-amber-200"
                  : "rounded-lg border border-[var(--insyt-border-strong)] bg-[var(--insyt-surface-2)] px-3 py-2 text-xs font-semibold text-[var(--insyt-text-secondary)]"
              }
            >
              Highlights {showDetectionHighlights ? "On" : "Off"}
            </button>
          )}
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
          <div className="h-full w-full overflow-hidden rounded-xl border border-[var(--insyt-border)] bg-[var(--insyt-surface-1)]">
            <div className="h-full w-full overflow-auto p-5">
              <pre className="m-0 whitespace-pre-wrap break-words font-sans text-sm leading-7 text-[var(--insyt-text-secondary)]">
                {text
                  ? showDetectionHighlights
                    ? renderHighlightedText(text, detectionHits)
                    : text
                  : "No extracted text available."}
              </pre>
            </div>
          </div>
        )}

        {viewMode === "native" && (
          <>
            {reviewPreviewLoading && (
              <div className="h-full w-full rounded-xl border border-[var(--insyt-border)] bg-[var(--insyt-surface-1)] flex items-center justify-center text-[var(--insyt-text-muted)]">
                Loading document viewer...
              </div>
            )}

            {!reviewPreviewLoading && reviewPreviewError && (
              <div className="h-full w-full rounded-xl border border-[var(--insyt-border)] bg-[var(--insyt-surface-1)] flex flex-col items-center justify-center p-8 text-center">
                <p className="text-rose-300 font-semibold mb-2">
                  Viewer metadata failed
                </p>

                <p className="text-[var(--insyt-text-muted)]">
                  {reviewPreviewError}
                </p>
              </div>
            )}

            {!reviewPreviewLoading &&
              !reviewPreviewError &&
              effectiveViewerType === "pdf" && (
                <div className="h-full w-full overflow-hidden rounded-xl border border-[var(--insyt-border)] bg-[var(--insyt-surface-1)]">
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
                <div className="h-full w-full overflow-auto rounded-xl border border-[var(--insyt-border)] bg-[var(--insyt-surface-1)] p-4">
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
                <div className="h-full w-full overflow-hidden rounded-xl border border-[var(--insyt-border)] bg-[var(--insyt-surface-1)]">
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
                    <div className="h-full w-full overflow-hidden rounded-xl border border-[var(--insyt-border)] bg-[var(--insyt-surface-1)]">
                      <div className="h-full w-full overflow-auto p-5">
                        <pre className="m-0 whitespace-pre-wrap break-words font-sans text-sm leading-7 text-[var(--insyt-text-secondary)]">
                          {text}
                        </pre>
                      </div>
                    </div>
                  ) : effectiveViewerUrl ? (
                    <div className="h-full w-full overflow-hidden rounded-xl border border-[var(--insyt-border)] bg-[var(--insyt-surface-1)]">
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
                    <div className="h-full w-full overflow-hidden rounded-xl border border-[var(--insyt-border)] bg-[var(--insyt-surface-1)]">
                      <iframe
                        src={effectiveViewerUrl}
                        className="h-full w-full bg-white"
                        title={reviewPreview?.file_name || "Email Preview"}
                      />
                    </div>
                  ) : (
                    <div className="h-full w-full rounded-xl border border-[var(--insyt-border)] bg-[var(--insyt-surface-1)] flex flex-col items-center justify-center p-8 text-center">
                      <h3 className="mb-3 text-xl font-semibold text-[var(--insyt-text-primary)]">
                        Email Preview Not Yet Converted
                      </h3>

                      <p className="text-[var(--insyt-text-muted)] mb-6">
                        This email file has not yet been converted into a browser preview.
                      </p>

                      {effectiveNativeUrl ? (
                        <a
                          href={effectiveNativeUrl}
                          target="_blank"
                          rel="noreferrer"
                          className="inline-flex min-h-10 items-center justify-center rounded-xl border border-sky-500 bg-sky-500 px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition-colors hover:border-sky-400 hover:bg-sky-400"
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
                    <div className="h-full w-full rounded-xl border border-[var(--insyt-border)] bg-[var(--insyt-surface-1)] flex items-center justify-center text-[var(--insyt-text-muted)]">
                      Loading native preview...
                    </div>
                  )}

                  {!previewLoading && previewError && (
                    <div className="h-full w-full rounded-xl border border-[var(--insyt-border)] bg-[var(--insyt-surface-1)] flex flex-col items-center justify-center p-8 text-center">
                      <p className="text-rose-300 font-semibold mb-2">
                        Preview failed
                      </p>

                      <p className="text-[var(--insyt-text-muted)]">
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
                      <div className="h-full w-full rounded-xl border border-[var(--insyt-border)] bg-[var(--insyt-surface-1)] flex flex-col items-center justify-center p-8 text-center">
                        <div className="max-w-lg">
                          <h3 className="mb-3 text-xl font-semibold text-[var(--insyt-text-primary)]">
                            Native File Preview Not Yet Supported
                          </h3>

                          <p className="text-[var(--insyt-text-muted)] mb-6">
                            {preview.message ||
                              "This file type cannot yet be rendered directly in-browser."}
                          </p>

                          {effectiveNativeUrl ? (
                            <a
                              href={effectiveNativeUrl}
                              target="_blank"
                              rel="noreferrer"
                              className="inline-flex min-h-10 items-center justify-center rounded-xl border border-sky-500 bg-sky-500 px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition-colors hover:border-sky-400 hover:bg-sky-400"
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
                <div className="h-full w-full rounded-xl border border-[var(--insyt-border)] bg-[var(--insyt-surface-1)] flex flex-col items-center justify-center p-8 text-center">
                  <div className="max-w-lg">
                    <h3 className="mb-3 text-xl font-semibold text-[var(--insyt-text-primary)]">
                      Preview Conversion Needed
                    </h3>

                    <p className="text-[var(--insyt-text-muted)] mb-6">
                      This file type needs a generated PDF or HTML preview before it can be rendered directly in-browser.
                    </p>

                    <div className="mb-6 rounded-xl border border-[var(--insyt-border)] bg-[var(--insyt-surface-2)] px-4 py-3 text-sm text-[var(--insyt-text-secondary)]">
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
                        className="inline-flex min-h-10 items-center justify-center rounded-xl border border-sky-500 bg-sky-500 px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition-colors hover:border-sky-400 hover:bg-sky-400"
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
                <div className="h-full w-full rounded-xl border border-[var(--insyt-border)] bg-[var(--insyt-surface-1)] flex flex-col items-center justify-center p-8 text-center">
                  <div className="max-w-lg">
                    <h3 className="mb-3 text-xl font-semibold text-[var(--insyt-text-primary)]">
                      Native File Preview Not Yet Supported
                    </h3>

                    <p className="text-[var(--insyt-text-muted)] mb-6">
                      This file type cannot yet be rendered directly in-browser.
                    </p>

                    <div className="mb-6 rounded-xl border border-[var(--insyt-border)] bg-[var(--insyt-surface-2)] px-4 py-3 text-sm text-[var(--insyt-text-secondary)]">
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
                        className="inline-flex min-h-10 items-center justify-center rounded-xl border border-sky-500 bg-sky-500 px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition-colors hover:border-sky-400 hover:bg-sky-400"
                      >
                        Open / Download Native File
                      </a>
                    ) : (
                      <p className="text-[var(--insyt-text-muted)]">
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