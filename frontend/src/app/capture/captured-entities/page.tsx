"use client";

import { Suspense } from "react";

import CapturedEntitiesTable from "../../../components/CapturedEntitiesTable";

export default function CapturedEntitiesPage() {
  return (
    <Suspense fallback={<div>Loading captured entities...</div>}>
      <CapturedEntitiesTable
        workspace="capture"
        title="Captured Entities"
        subtitlePrefix="Protocol-aligned captured entities"
      />
    </Suspense>
  );
}