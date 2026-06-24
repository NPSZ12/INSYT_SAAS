"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  Worker,
  Viewer,
  SpecialZoomLevel,
} from "@react-pdf-viewer/core";
import { defaultLayoutPlugin } from "@react-pdf-viewer/default-layout";
import { pageNavigationPlugin } from "@react-pdf-viewer/page-navigation";
import type {
  DocumentLoadEvent,
  PageChangeEvent,
} from "@react-pdf-viewer/core";

import "@react-pdf-viewer/core/lib/styles/index.css";
import "@react-pdf-viewer/default-layout/lib/styles/index.css";
import "@react-pdf-viewer/page-navigation/lib/styles/index.css";

type PdfViewerApi = {
  jumpToPage: (pageIndex: number) => void;
};

type PdfDocumentViewerProps = {
  fileUrl: string;
  heightClassName?: string;
  targetPage?: number | null;
  onPageChange?: (pageNumber: number) => void;
  onViewerReady?: (api: PdfViewerApi) => void;
};

function toPositivePage(value: unknown) {
  const page = Number(value);

  if (Number.isFinite(page) && page > 0) {
    return page;
  }

  return null;
}

export default function PdfDocumentViewer({
  fileUrl,
  heightClassName = "h-[calc(100vh-180px)]",
  targetPage,
  onPageChange,
  onViewerReady,
}: PdfDocumentViewerProps) {
  const cleanedFileUrl = fileUrl?.trim();

  const defaultLayoutPluginInstance = useMemo(
    () => defaultLayoutPlugin(),
    []
  );

  const pageNavigationPluginInstance = useMemo(
    () => pageNavigationPlugin(),
    []
  );

  const { jumpToPage } = pageNavigationPluginInstance;

  const [isDocumentLoaded, setIsDocumentLoaded] = useState(false);

  const lastJumpKeyRef = useRef("");
  const pendingTargetPageRef = useRef<number | null>(null);

  function jumpToViewerPage(pageNumber: number | null) {
    if (!pageNumber) return;

    const pageIndex = Math.max(pageNumber - 1, 0);
    const jumpKey = `${cleanedFileUrl || ""}::${pageNumber}`;

    if (lastJumpKeyRef.current === jumpKey) {
      return;
    }

    lastJumpKeyRef.current = jumpKey;

    // Delay one tick so the viewer/page layers are ready after load or URL change.
    window.requestAnimationFrame(() => {
      jumpToPage(pageIndex);
    });
  }

  useEffect(() => {
    setIsDocumentLoaded(false);
    lastJumpKeyRef.current = "";
    pendingTargetPageRef.current = toPositivePage(targetPage);
  }, [cleanedFileUrl]);

  useEffect(() => {
    const pageNumber = toPositivePage(targetPage);

    pendingTargetPageRef.current = pageNumber;

    if (!pageNumber || !isDocumentLoaded) {
      return;
    }

    jumpToViewerPage(pageNumber);
  }, [targetPage, isDocumentLoaded, cleanedFileUrl, jumpToPage]);

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
      className="h-full max-h-full min-h-0 w-full rounded-2xl border border-slate-800 bg-slate-900 overflow-hidden"
    >
      <div className="h-full max-h-full min-h-0 w-full overflow-hidden">
        <Worker workerUrl="/pdf.worker.min.js">
          <Viewer
            fileUrl={cleanedFileUrl}
            plugins={[
              defaultLayoutPluginInstance,
              pageNavigationPluginInstance,
            ]}
            defaultScale={SpecialZoomLevel.PageWidth}
            enableSmoothScroll
            onDocumentLoad={(_event: DocumentLoadEvent) => {
              setIsDocumentLoaded(true);

              const pageNumber = pendingTargetPageRef.current;

              if (pageNumber) {
                jumpToViewerPage(pageNumber);
              }
            }}
            onPageChange={(event: PageChangeEvent) => {
              onPageChange?.(event.currentPage + 1);
            }}
            renderError={(error) => (
              <div className="h-full overflow-auto p-6 text-sm text-red-300">
                <div className="mb-2 font-semibold">
                  Failed to load PDF.
                </div>

                <div className="break-all text-slate-300">
                  URL: {cleanedFileUrl}
                </div>

                <div className="mt-3 text-slate-400">
                  {error.message}
                </div>
              </div>
            )}
          />
        </Worker>
      </div>

      <style jsx global>{`
        .rpv-core__viewer {
          height: 100% !important;
          max-height: 100% !important;
          overflow: hidden !important;
        }

        .rpv-core__inner-container {
          height: 100% !important;
          max-height: 100% !important;
          overflow: hidden !important;
        }

        .rpv-core__viewer-container {
          height: 100% !important;
          max-height: 100% !important;
          overflow: hidden !important;
        }

        .rpv-core__inner-pages {
          height: 100% !important;
          max-height: 100% !important;
          overflow-y: auto !important;
          overflow-x: hidden !important;
          contain: strict !important;
        }

        .rpv-core__inner-page-container {
          height: auto !important;
          max-height: none !important;
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