"use client";

import { Suspense } from "react";

import ProcessingCenterPage from "../../../components/ProcessingCenterPage";

function DiscoveryProcessingCenterContent() {
  return <ProcessingCenterPage workspace="discovery" />;
}

export default function DiscoveryProcessingCenterRoute() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen bg-slate-950 p-8 text-slate-300">
          Loading Processing Center...
        </div>
      }
    >
      <DiscoveryProcessingCenterContent />
    </Suspense>
  );
}