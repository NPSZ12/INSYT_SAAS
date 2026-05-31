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
  targetPage?: number | null;
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

export default function ReviewDocumentPane({
  text,
  nativeUrl,
  nativeBlob,
  targetPage,
}: ReviewDocumentPaneProps) {
  const [viewMode, setViewMode] =
    useState<"text" | "native">("native");

  const extension = getExtension(
    nativeBlob,
    nativeUrl
  );

  const isPdf = extension === "pdf";

  const isTextFriendly = [
    "txt",
    "csv",
    "json",
    "xml",
    "log",
    "html",
    "htm",
  ].includes(extension);

  return (
    <div className="col-span-2 bg-slate-900 border border-slate-800 rounded-2xl p-6 h-[calc(100vh-7.5rem)] min-h-[760px] flex flex-col overflow-hidden">
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
          <div className="h-full w-full overflow-y-auto rounded-xl border border-slate-800 bg-slate-950 p-5 text-slate-300 leading-7 whitespace-pre-wrap">
            {text || "No extracted text available."}
          </div>
        )}

        {viewMode === "native" && (
          <>
            {isPdf ? (
              <div className="h-full w-full overflow-hidden rounded-xl border border-slate-800 bg-slate-950">
                <PdfDocumentViewer
                  fileUrl={nativeUrl || ""}
                  heightClassName="h-full"
                  targetPage={targetPage}
                />
              </div>
            ) : isTextFriendly ? (
              <div className="h-full w-full overflow-y-auto rounded-xl border border-slate-800 bg-slate-950 p-5 text-slate-300 leading-7 whitespace-pre-wrap">
                {text || "No extracted text available."}
              </div>
            ) : (
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
                      {extension || "Unknown"}
                    </span>
                  </div>

                  {nativeUrl ? (
                    <a
                      href={nativeUrl}
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