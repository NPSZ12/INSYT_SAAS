"use client";

import { Worker, Viewer, SpecialZoomLevel } from "@react-pdf-viewer/core";
import { defaultLayoutPlugin } from "@react-pdf-viewer/default-layout";
import type { PageChangeEvent } from "@react-pdf-viewer/core";

import "@react-pdf-viewer/core/lib/styles/index.css";
import "@react-pdf-viewer/default-layout/lib/styles/index.css";

type PdfDocumentViewerProps = {
  fileUrl: string;
  heightClassName?: string;
  onPageChange?: (pageNumber: number) => void;
};

export default function PdfDocumentViewer({
  fileUrl,
  heightClassName = "h-[calc(100vh-220px)]",
  onPageChange,
}: PdfDocumentViewerProps) {
  const defaultLayoutPluginInstance = defaultLayoutPlugin();

  const cleanedFileUrl = fileUrl?.trim();

  if (!cleanedFileUrl) {
    return (
      <div className="h-full rounded-2xl border border-slate-800 bg-slate-900 p-6 text-slate-400">
        No PDF loaded.
      </div>
    );
  }

  return (
    <div
      className={`${heightClassName} min-h-[500px] rounded-2xl border border-slate-800 bg-slate-900 overflow-hidden`}
    >
      <Worker workerUrl="/pdf.worker.min.js">
        <Viewer
          fileUrl={cleanedFileUrl}
          plugins={[defaultLayoutPluginInstance]}
          defaultScale={SpecialZoomLevel.PageWidth}
          enableSmoothScroll
          onPageChange={(event: PageChangeEvent) => {
            onPageChange?.(event.currentPage + 1);
          }}
          renderError={(error) => (
            <div className="h-full overflow-auto p-6 text-sm text-red-300">
              <div className="mb-2 font-semibold">Failed to load PDF.</div>
              <div className="break-all text-slate-300">
                URL: {cleanedFileUrl}
              </div>
              <div className="mt-3 text-slate-400">{error.message}</div>
            </div>
          )}
        />
      </Worker>

      <style jsx global>{`
        .rpv-core__viewer {
          height: 100% !important;
        }

        .rpv-core__inner-container {
          height: 100% !important;
        }

        .rpv-core__annotation-layer {
          pointer-events: auto !important;
          z-index: 20 !important;
        }

        .rpv-core__annotation-layer a {
          pointer-events: auto !important;
          cursor: pointer !important;
          z-index: 30 !important;
        }

        .rpv-core__page-layer {
          position: relative !important;
        }

        .rpv-core__text-layer {
          z-index: 10 !important;
          pointer-events: none !important;
        }

        .rpv-core__canvas-layer {
          z-index: 1 !important;
        }
      `}</style>
    </div>
  );
}