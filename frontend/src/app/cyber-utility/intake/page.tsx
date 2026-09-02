"use client";

import { Suspense } from "react";

import CyberUtilityWorkflowPlaceholder from "../../../components/CyberUtilityWorkflowPlaceholder";

function IntakePageContent() {
  return (
    <CyberUtilityWorkflowPlaceholder
      title="Cyber² Intake & Preparation"
      subtitle="Review structured-data files promoted into Cyber² for the active project."
      description="This workflow will receive responsive worksheet and CSV populations from INSYT Promotion, preserve source lineage, and prepare selected datasets for structured-data processing."
    />
  );
}

export default function Page() {
  return (
    <Suspense fallback={<div>Loading...</div>}>
      <IntakePageContent />
    </Suspense>
  );
}