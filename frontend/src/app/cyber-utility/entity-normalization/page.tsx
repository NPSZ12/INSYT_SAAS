"use client";

import { Suspense } from "react";

import CyberUtilityWorkflowPlaceholder from "../../../components/CyberUtilityWorkflowPlaceholder";

function EntityNormalizationPageContent() {
  return (
    <CyberUtilityWorkflowPlaceholder
      title="Entity Normalization"
      subtitle="Normalize entity values and variants across project datasets."
      description="This workflow will normalize names, addresses, email addresses, phone numbers, identifiers, and related variants while retaining links to the original source records."
    />
  );
}

export default function Page() {
  return (
    <Suspense fallback={<div>Loading...</div>}>
      <EntityNormalizationPageContent />
    </Suspense>
  );
}