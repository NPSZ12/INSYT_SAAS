"use client";

import { Suspense } from "react";

import CyberUtilityWorkflowPlaceholder from "../../../components/CyberUtilityWorkflowPlaceholder";

function SchemaMappingPageContent() {
  return (
    <CyberUtilityWorkflowPlaceholder
      title="Header & Schema Mapping"
      subtitle="Inspect and normalize structured-data schemas for the active project."
      description="This workflow will identify source headers, compare them with project protocol fields, apply aliases and mapping recommendations, and create normalized working datasets."
    />
  );
}

export default function Page() {
  return (
    <Suspense fallback={<div>Loading...</div>}>
      <SchemaMappingPageContent />
    </Suspense>
  );
}