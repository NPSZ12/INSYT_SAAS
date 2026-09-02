"use client";

import { Suspense } from "react";

import CyberUtilityWorkflowPlaceholder from "../../../components/CyberUtilityWorkflowPlaceholder";

function ExportsPageContent() {
  return (
    <CyberUtilityWorkflowPlaceholder
      title="Exports & Deliverables"
      subtitle="Generate defensible Cyber² project outputs and deliverables."
      description="This workflow will generate final CSV and XLSX datasets, population exports, processing statistics, audit manifests, and other structured-data project deliverables."
    />
  );
}

export default function Page() {
  return (
    <Suspense fallback={<div>Loading...</div>}>
      <ExportsPageContent />
    </Suspense>
  );
}