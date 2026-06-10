"use client";

import { Suspense } from "react";

import FinalEntitySourceViewer from "../../../../components/FinalEntitySourceViewer";

export default function CaptureFinalEntityViewerPage() {
  return (
    <Suspense fallback={<div>Loading Final source viewer...</div>}>
      <FinalEntitySourceViewer workspace="capture" />
    </Suspense>
  );
}