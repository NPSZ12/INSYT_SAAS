"use client";

import { Suspense } from "react";

import CyberUtilityWorkflowPlaceholder from "../../../components/CyberUtilityWorkflowPlaceholder";

function MergeDedupePageContent() {
  return (
    <CyberUtilityWorkflowPlaceholder
      title="Merge & Dedupe"
      subtitle="Combine compatible datasets while preserving source lineage."
      description="This workflow will merge normalized datasets, select deduplication fields, identify duplicate records, preserve source-row lineage, and generate master working populations."
    />
  );
}

export default function Page() {
  return (
    <Suspense fallback={<div>Loading...</div>}>
      <MergeDedupePageContent />
    </Suspense>
  );
}