"use client";

import { Suspense } from "react";
import { useRouter } from "next/navigation";
import AppShell from "../../components/AppShell";
import Button from "../../components/Button";

function SummariesPageContent() {
  const router = useRouter();

  return (
    <AppShell>
      <main className="p-8 text-white">
        <h1 className="text-3xl font-bold mb-2">INSYT Summaries</h1>

        <p className="text-slate-400 mb-8">
          Summary QC, linked entries, outlines, batching, and project review workflows.
        </p>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 max-w-5xl">
          <Button onClick={() => router.push("/summaries/review")}>
            Review
          </Button>

          <Button onClick={() => router.push("/summaries/batches")}>
            Batches
          </Button>

          <Button onClick={() => router.push("/summaries/protocol")}>
            Protocol
          </Button>

          <Button onClick={() => router.push("/summaries/project-hours")}>
            Project Hours
          </Button>

          <Button onClick={() => router.push("/summaries/original-records-outline")}>
            Original Records Outline
          </Button>

          <Button onClick={() => router.push("/summaries/updated-records-outline")}>
            Updated Records Outline
          </Button>

          <Button onClick={() => router.push("/summaries/data-management")}>
            Data Management
          </Button>

          <Button onClick={() => router.push("/summaries/batch-management")}>
            Batch Management
          </Button>

          <Button onClick={() => router.push("/summaries/review-team")}>
            Review Team
          </Button>
        </div>
      </main>
    </AppShell>
  );
}

export default function SummariesPage() {
  return (
    <Suspense fallback={<div>Loading...</div>}>
      <SummariesPageContent />
    </Suspense>
  );
}






