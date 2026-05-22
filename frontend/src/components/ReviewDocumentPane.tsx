"use client";

import { useState } from "react";

import Button from "./Button";
import dynamic from "next/dynamic";

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
};

export default function ReviewDocumentPane({
  text,
  nativeUrl,
  nativeBlob,
}: ReviewDocumentPaneProps) {
  const [viewMode, setViewMode] = useState<"text" | "native">("native");

  return (
    <div className="col-span-2 bg-slate-900 border border-slate-800 rounded-2xl p-6 h-full flex flex-col overflow-hidden">
      <div className="shrink-0 flex items-center justify-between mb-4">
        <div>
          <h2 className="text-lg font-semibold">
            Document Viewer
          </h2>

          <p className="text-xs text-slate-500 mt-1">
            {viewMode === "text"
              ? "Extracted Text"
              : nativeBlob || "Native PDF"}
          </p>
        </div>

        <div className="flex gap-3">
          <Button
            variant={viewMode === "text" ? "primary" : "secondary"}
            onClick={() => setViewMode("text")}
          >
            Text
          </Button>

          <Button
            variant={viewMode === "native" ? "primary" : "secondary"}
            onClick={() => setViewMode("native")}
          >
            Native PDF
          </Button>
        </div>
      </div>

      <div className="flex-1 min-h-0">
        {viewMode === "text" && (
          <div className="bg-slate-950 rounded-xl p-5 h-full overflow-y-auto text-slate-300 leading-7 whitespace-pre-wrap">
            {text}
          </div>
        )}

        {viewMode === "native" && (
          <PdfDocumentViewer
            fileUrl={nativeUrl || ""}
            heightClassName="h-full"
          />
        )}
      </div>
    </div>
  );
}