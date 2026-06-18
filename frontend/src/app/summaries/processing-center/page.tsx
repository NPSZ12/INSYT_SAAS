"use client";

import { Suspense } from "react";

import ProcessingCenterPage from "../../../components/ProcessingCenterPage";

function SummariesProcessingCenterContent() {
  return <ProcessingCenterPage workspace="summaries" />;
}

export default function SummariesProcessingCenterRoute() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen bg-slate-950 p-8 text-slate-300">
          Loading Processing Center...
        </div>
      }
    >
      <SummariesProcessingCenterContent />
    </Suspense>
  );
}