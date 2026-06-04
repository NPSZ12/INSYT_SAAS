"use client";

import { Suspense } from "react";

import CapturedEntitiesTable from "../../../components/CapturedEntitiesTable";

export default function DiscoveryEntitiesPage() {
  return (
    <Suspense fallback={<div>Loading Discovery entities...</div>}>
      <CapturedEntitiesTable
        workspace="discovery"
        title="Captured Coding"
        subtitlePrefix="Protocol-aligned captured coding"
      />
    </Suspense>
  );
}