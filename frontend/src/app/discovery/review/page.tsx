"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams, useRouter } from "next/navigation";

import AppShell from "../../../components/AppShell";
import PageContainer from "../../../components/PageContainer";
import PageHeader from "../../../components/PageHeader";
import ContentCard from "../../../components/ContentCard";
import Button from "../../../components/Button";
import DataTable from "../../../components/DataTable";
import { apiGet } from "../../../lib/api";

type BatchFile = {
  doc_id: string;
  file_name: string;
  status: string;
};

function ReviewBatchLandingPageContent() {
  const searchParams = useSearchParams();
  const router = useRouter();

  const projectId = searchParams.get("project");
  const batchId = searchParams.get("batch");

  const [files, setFiles] = useState<BatchFile[]>([]);

  useEffect(() => {
    if (!projectId || !batchId) return;

    apiGet(`/api/batches/files?project=${projectId}&batch=${batchId}`)
      .then(setFiles)
      .catch(console.error);
  }, [projectId, batchId]);

  if (!projectId || !batchId) {
    return (
      <AppShell>
        <PageContainer>
          <PageHeader
            title="No Batch Selected"
            subtitle="Please select a batch before starting review."
          />
        </PageContainer>
      </AppShell>
    );
  }

  const columns = [
    { key: "doc_id", label: "Doc ID" },
    { key: "file_name", label: "File Name" },
    { key: "status", label: "Status" },
  ];

  return (
    <AppShell>
      <PageContainer>
        <div className="flex items-start justify-between mb-8">
          <PageHeader
            title={batchId.replaceAll("_", " ")}
            subtitle={`Documents available for ${projectId.replaceAll("_", " ")}.`}
          />

          <Button
            onClick={() =>
              router.push(
                `/discovery/review/doc?project=${projectId}&batch=${batchId}`
              )
            }
          >
            Review Docs
          </Button>
        </div>

        <ContentCard title="Batch Documents">
          {files.length === 0 ? (
            <p className="text-slate-500">
              No documents found for this batch.
            </p>
          ) : (
            <div className="max-h-[45vh] overflow-auto">
              <DataTable columns={columns} data={files} />
            </div>
          )}
        </ContentCard>
      </PageContainer>
    </AppShell>
  );
}
export default function ReviewBatchLandingPage() {
  return (
    <Suspense fallback={<div>Loading login...</div>}>
      <ReviewBatchLandingPageContent />
    </Suspense>
  );
}












