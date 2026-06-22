"use client";

import { Suspense } from "react";

import ProcessingCenterPage from "../../../components/ProcessingCenterPage";

function SummariesProcessingCenterContent() {
  return (
    <ProcessingCenterPage
      workspace="summaries"
      title="INSYT Summaries Processing Center"
      subtitle="Upload source PDFs, run Summaries processing, prepare review-ready text, and build the foundation for PDF outline and summary-level batching."
    />
  );
}

export default function SummariesProcessingCenterRoute() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen bg-slate-950 p-8 text-slate-300">
          Loading Summaries Processing Center...
        </div>
      }
    >
      <SummariesProcessingCenterContent />
    </Suspense>
  );
}