"use client";

import { Suspense } from "react";

import SummariesProcessingCenterPage from "../../../components/SummariesProcessingCenterPage";

function SummariesProcessingCenterContent() {
  return <SummariesProcessingCenterPage />;
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