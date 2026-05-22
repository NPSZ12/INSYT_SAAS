"use client";

import { Worker, Viewer } from "@react-pdf-viewer/core";
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
  heightClassName = "h-full",
  onPageChange,
}: PdfDocumentViewerProps) {
  const defaultLayoutPluginInstance = defaultLayoutPlugin();

  if (!fileUrl) {
    return (
      <div className="h-full rounded-2xl border border-slate-800 bg-slate-900 p-6 text-slate-400">
        No PDF loaded.
      </div>
    );
  }

  return (
    <div className={`${heightClassName} rounded-2xl border border-slate-800 bg-slate-900 overflow-hidden`}>
      <Worker workerUrl="https://unpkg.com/pdfjs-dist@3.11.174/build/pdf.worker.min.js">
        <Viewer
          fileUrl={fileUrl}
          plugins={[defaultLayoutPluginInstance]}
          onPageChange={(event: PageChangeEvent) => {
            onPageChange?.(event.currentPage + 1);
          }}
        />
      </Worker>
    </div>
  );
}