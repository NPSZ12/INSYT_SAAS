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

type StoredUser = {
  username: string;
  display_name: string;
  role: string;
};

function ReviewBatchLandingPageContent() {
  const searchParams = useSearchParams();
  const router = useRouter();

  const clientId = searchParams.get("client") || "";
  const projectId = searchParams.get("project") || "";
  const batchId = searchParams.get("batch") || "";
  const docId = searchParams.get("doc") || "";

  const [files, setFiles] = useState<BatchFile[]>([]);
  const [message, setMessage] = useState("");

  const [user, setUser] = useState<StoredUser | null>(null);
  const [resolvedBatchId, setResolvedBatchId] = useState(batchId);

  useEffect(() => {
    if (!clientId || !projectId || !docId) {
      return;
    }

    const params = new URLSearchParams();

    params.set("client", clientId);
    params.set("project", projectId);
    params.set("doc", docId);

    if (batchId) {
      params.set("batch", batchId);
    }

    router.replace(`/summaries/review/doc?${params.toString()}`);
  }, [router, clientId, projectId, batchId, docId]);

  function openReview(docIdOverride?: string) {
    const firstDocId = docIdOverride || files[0]?.doc_id || "";

    if (!firstDocId) {
      setMessage("No document selected for review.");
      return;
    }

    const params = new URLSearchParams();

    params.set("client", clientId);
    params.set("project", projectId);
    params.set("doc", firstDocId);

    if (resolvedBatchId) {
      params.set("batch", resolvedBatchId);
    }

    router.push(`/summaries/review/doc?${params.toString()}`);
  }

  useEffect(() => {
    const storedUser = localStorage.getItem("insyt_user");

    if (storedUser) {
      setUser(JSON.parse(storedUser));
    }
  }, []);

  useEffect(() => {
    if (!clientId || !projectId || !user) return;

    apiGet(
      `/api/summaries/projects/${encodeURIComponent(
        projectId
      )}/batches?client=${encodeURIComponent(clientId)}`
    )
      .then((response) => {
        const batches = response.batches || [];

        const selectedBatchId =
          batchId ||
          batches.find((batch: any) => {
            const status = String(batch.status || "")
              .toLowerCase()
              .replaceAll("_", " ");

            return (
              status === "checked out" &&
              batch.checked_out_by?.toLowerCase() ===
                user.username?.toLowerCase()
            );
          })?.batch_name ||
          "";

        setResolvedBatchId(selectedBatchId);

        if (!selectedBatchId) {
          setFiles([]);
          return;
        }

        const selectedBatch = batches.find(
          (batch: any) =>
            batch.batch_name === selectedBatchId ||
            batch.batch_id === selectedBatchId ||
            batch.name === selectedBatchId
        );

        const docIds = selectedBatch?.doc_ids || [];

        setFiles(
          docIds.map((docId: string) => ({
            doc_id: docId,
            file_name: docId,
            status: selectedBatch?.status || "Ready",
          }))
        );
      })
      .catch((error) => {
        console.error(error);
        setMessage("Failed to load checked-out batch.");
        setFiles([]);
      });
  }, [clientId, projectId, batchId, user]);

  if (!clientId || !projectId) {
    return (
      <AppShell>
        <PageContainer>
          <PageHeader
            title="No Project Selected"
            subtitle="Please select a Summaries project before starting review."
          />
        </PageContainer>
      </AppShell>
    );
  }

  if (docId) {
    return (
      <AppShell>
        <PageContainer>
          <PageHeader
            title="Opening Review"
            subtitle="Preparing the Summaries review workspace..."
          />
        </PageContainer>
      </AppShell>
    );
  }

  if (!resolvedBatchId) {
    return (
      <AppShell>
        <PageContainer>
          <PageHeader
            title="No Review Target Selected"
            subtitle="Please select a batch or open a document directly from Files."
          />
        </PageContainer>
      </AppShell>
    );
  }

  const tableRows = files.map((file) => ({
    doc_id: file.doc_id,
    file_name: file.file_name || file.doc_id,
    status: file.status || "Ready",
    action: (
      <Button
        variant="secondary"
        onClick={() => openReview(file.doc_id)}
      >
        Open
      </Button>
    ),
  }));

  const columns = [
    { key: "doc_id", label: "Doc ID" },
    { key: "file_name", label: "File Name" },
    { key: "status", label: "Status" },
    { key: "action", label: "Open" },
  ];

  return (
    <AppShell>
      <PageContainer>
        <div className="flex items-start justify-between mb-8">
          <PageHeader
            title={resolvedBatchId.replaceAll("_", " ")}
            subtitle={`Documents available for ${projectId.replaceAll(
              "_",
              " "
            )}.`}
          />

          <Button onClick={() => openReview()}>
            Open Review
          </Button>
        </div>

        {message && (
          <p className="mb-4 text-sm text-sky-400">
            {message}
          </p>
        )}

        <ContentCard title="Batch Documents">
          {files.length === 0 ? (
            <p className="text-slate-500">
              No documents found for this batch.
            </p>
          ) : (
            <div className="max-h-[55vh] overflow-auto">
              <DataTable columns={columns} data={tableRows} />
            </div>
          )}
        </ContentCard>
      </PageContainer>
    </AppShell>
  );
}

export default function ReviewBatchLandingPage() {
  return (
    <Suspense fallback={<div>Loading review batch...</div>}>
      <ReviewBatchLandingPageContent />
    </Suspense>
  );
}