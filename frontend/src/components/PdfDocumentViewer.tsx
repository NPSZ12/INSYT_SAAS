"use client";

import { useEffect } from "react";
import { Worker, Viewer, SpecialZoomLevel } from "@react-pdf-viewer/core";
import { defaultLayoutPlugin } from "@react-pdf-viewer/default-layout";
import { pageNavigationPlugin } from "@react-pdf-viewer/page-navigation";
import type { PageChangeEvent } from "@react-pdf-viewer/core";

import "@react-pdf-viewer/core/lib/styles/index.css";
import "@react-pdf-viewer/default-layout/lib/styles/index.css";
import "@react-pdf-viewer/page-navigation/lib/styles/index.css";

type PdfViewerApi = {
  jumpToPage: (pageIndex: number) => void;
};

type PdfDocumentViewerProps = {
  fileUrl: string;
  heightClassName?: string;
  onPageChange?: (pageNumber: number) => void;
  onViewerReady?: (api: PdfViewerApi) => void;
};

export default function PdfDocumentViewer({
  fileUrl,
  heightClassName = "h-[calc(100vh-180px)]",
  onPageChange,
  onViewerReady,
}: PdfDocumentViewerProps) {
  const defaultLayoutPluginInstance = defaultLayoutPlugin();
  const pageNavigationPluginInstance = pageNavigationPlugin();

  const { jumpToPage } = pageNavigationPluginInstance;

  const cleanedFileUrl = fileUrl?.trim();

  useEffect(() => {
    onViewerReady?.({
      jumpToPage,
    });
  }, [jumpToPage, onViewerReady]);

  if (!cleanedFileUrl) {
    return (
      <div className="h-full rounded-2xl border border-slate-800 bg-slate-900 p-6 text-slate-400">
        No PDF loaded.
      </div>
    );
  }

  return (
    <div
      className={`${heightClassName} max-h-[calc(100vh-220px)] min-h-[500px] rounded-2xl border border-slate-800 bg-slate-900 overflow-hidden`}
    >
      <Worker workerUrl="/pdf.worker.min.js">
        <Viewer
          fileUrl={cleanedFileUrl}
          plugins={[
            defaultLayoutPluginInstance,
            pageNavigationPluginInstance,
          ]}
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
        .rpv-core__viewer,
        .rpv-core__inner-container,
        .rpv-core__viewer-container {
          height: 100% !important;
          max-height: 100% !important;
          overflow: hidden !important;
        }

        .rpv-core__inner-pages {
          height: 100% !important;
          max-height: 100% !important;
          overflow-y: auto !important;
        }
      `}</style>
    </div>
  );
}