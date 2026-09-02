"use client";

import { Suspense } from "react";

import CyberUtilityWorkflowPlaceholder from "../../../components/CyberUtilityWorkflowPlaceholder";

function PopulationAnalysisPageContent() {
  return (
    <CyberUtilityWorkflowPlaceholder
      title="Population Analysis"
      subtitle="Analyze structured-data populations for the active project."
      description="This workflow will calculate unique individuals and entities, analyze relationships and source records, measure reportable populations, and support project-specific population analysis."
    />
  );
}

export default function Page() {
  return (
    <Suspense fallback={<div>Loading...</div>}>
      <PopulationAnalysisPageContent />
    </Suspense>
  );
}