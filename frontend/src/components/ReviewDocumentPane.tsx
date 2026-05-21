"use client";

import { useState } from "react";
import Button from "./Button";

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
  const [viewMode, setViewMode] = useState<"text" | "native">("text");

  return (
    <div className="col-span-2 bg-slate-900 border border-slate-800 rounded-2xl p-6">
      <div className="flex items-center justify-between mb-4">
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

      {viewMode === "text" && (
        <div className="bg-slate-950 rounded-xl p-5 h-[75vh] overflow-y-auto text-slate-300 leading-7 whitespace-pre-wrap">
          {text}
        </div>
      )}

      {viewMode === "native" && (
        <div className="bg-slate-950 rounded-xl h-[75vh] overflow-hidden border border-slate-800">
          {nativeUrl ? (
            <iframe
              src={nativeUrl}
              className="w-full h-full"
              title="Native PDF Viewer"
            />
          ) : (
            <div className="h-full flex items-center justify-center text-slate-400 p-6 text-center">
              No matching native PDF found for this extracted text file.
            </div>
          )}
        </div>
      )}
    </div>
  );
}








