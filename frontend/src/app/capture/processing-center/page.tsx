"use client";

import { Suspense } from "react";

import ProcessingCenterPage from "../../../components/ProcessingCenterPage";

function CaptureProcessingCenterContent() {
  return <ProcessingCenterPage workspace="capture" />;
}

export default function CaptureProcessingCenterRoute() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen bg-slate-950 p-8 text-slate-300">
          Loading Processing Center...
        </div>
      }
    >
      <CaptureProcessingCenterContent />
    </Suspense>
  );
}