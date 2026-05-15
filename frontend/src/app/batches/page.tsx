"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams, useRouter } from "next/navigation";

import AppShell from "../../components/AppShell";
import PageContainer from "../../components/PageContainer";
import PageHeader from "../../components/PageHeader";
import ContentCard from "../../components/ContentCard";
import Button from "../../components/Button";
import Input from "../../components/Input";
import Select from "../../components/Select";
import FormLabel from "../../components/FormLabel";
import StatusBadge from "../../components/StatusBadge";
import DataTable from "../../components/DataTable";
import { apiGet, apiPost } from "../../lib/api";

type Batch = {
  project_id: string;
  batch_id: string;
  name: string;
  status: string;
  documents: string;
  checked_out_by: string;
};

type ProjectFile = {
  doc_id: string;
  file_name: string;
  status: string;
};

type SearchFolder = {
  folder_id: string;
  folder_name: string;
  search_type: string;
  document_count: number;
  hit_count: number;
};

type StoredUser = {
  username: string;
  display_name: string;
  role: string;
};

function BatchesPageContent() {
  const searchParams = useSearchParams();
  const router = useRouter();

  const projectId = searchParams.get("project");

  const [user, setUser] = useState<StoredUser | null>(null);
  const [mode, setMode] = useState<"review" | "qc" | "alt">("review");

  const [batches, setBatches] = useState<Batch[]>([]);
  const [files, setFiles] = useState<ProjectFile[]>([]);
  const [searchFolders, setSearchFolders] = useState<SearchFolder[]>([]);

  const [batchName, setBatchName] = useState("");
  const [docsPerBatch, setDocsPerBatch] = useState("20");
  const [selectedFolderId, setSelectedFolderId] = useState("");
  const [message, setMessage] = useState("");

  

  useEffect(() => {
    const storedUser = localStorage.getItem("insyt_user");

    if (storedUser) {
      setUser(JSON.parse(storedUser));
    }
  }, []);

  const isAdmin =
    user?.role === "CDS Admin" ||
    user?.role === "RM" ||
    user?.role === "TL" ||
    user?.role === "QC";

  function loadBatches() {
    if (!projectId) return;

    apiGet(`/api/batches?project=${projectId}`)
      .then(setBatches)
      .catch(console.error);
  }

  function loadFiles() {
    if (!projectId) return;

    apiGet(`/api/batches/files?project=${projectId}&batch=all`)
      .then(setFiles)
      .catch(console.error);
  }

  function loadSearchFolders() {
    if (!projectId) return;

    apiGet(`/api/search-folders?project=${projectId}`)
      .then(setSearchFolders)
      .catch(console.error);
  }

  useEffect(() => {
    loadBatches();
    loadFiles();
    loadSearchFolders();
  }, [projectId]);

  function checkoutBatch(batchId: string) {
    if (!projectId) return;

    apiPost("/api/batches/checkout", {
      project_id: projectId,
      batch_id: batchId,
    })
      .then((response) => {
        setMessage(response.message || "Batch updated.");
        loadBatches();
      })
      .catch(() => setMessage("Batch checkout failed."));
  }

  function createReviewBatches() {
    if (!projectId) return;

    apiPost("/api/batches/create-review", {
      project_id: projectId,
      batch_name: batchName,
      docs_per_batch: Number(docsPerBatch),
    })
      .then((response) => {
        setMessage(response.message || "Review batches created.");
        setBatchName("");
        loadBatches();
        loadFiles();
      })
      .catch(() => setMessage("Review batch creation failed."));
  }

  function createQCBatches() {
    if (!projectId) return;

    apiPost("/api/batches/create-qc", {
      project_id: projectId,
      batch_name: batchName,
      docs_per_batch: Number(docsPerBatch),
    })
      .then((response) => {
        setMessage(response.message || "QC batches created.");
        setBatchName("");
        loadBatches();
      })
      .catch(() => setMessage("QC batch creation failed."));
  }

  function createAltBatch() {
    if (!projectId || !selectedFolderId) return;

    apiPost("/api/batches/create-alt", {
      project_id: projectId,
      folder_id: selectedFolderId,
      batch_name: batchName,
      docs_per_batch: Number(docsPerBatch),
    })
      .then((response) => {
        setMessage(response.message || "Alt batch created.");
        setBatchName("");
        setSelectedFolderId("");
        loadBatches();
      })
      .catch(() => setMessage("Alt batch creation failed."));
  }

  if (!projectId) {
    return (
      <AppShell>
        <PageContainer>
          <PageHeader
            title="No Project Selected"
            subtitle="Return to Projects and select a project first."
          />
        </PageContainer>
      </AppShell>
    );
  }

  if (!isAdmin) {
    return (
      <ReviewerBatches
        projectId={projectId}
        batches={batches}
        message={message}
        checkoutBatch={checkoutBatch}
        router={router}
      />
    );
  }

  const fileColumns = [
    { key: "doc_id", label: "Doc ID" },
    { key: "file_name", label: "File Name" },
    { key: "status", label: "Batch Status" },
  ];

  const batchColumns = [
    { key: "batch_id", label: "Batch ID" },
    { key: "name", label: "Name" },
    { key: "status", label: "Status" },
    { key: "documents", label: "Documents" },
    { key: "checked_out_by", label: "Checked Out By" },
  ];

  const filteredBatches = batches.filter((batch) => {
    if (mode === "review") {
      return batch.batch_id.toLowerCase().includes("review");
    }

    if (mode === "qc") {
      return batch.batch_id.toLowerCase().includes("qc");
    }

    if (mode === "alt") {
      return (
        !batch.batch_id.toLowerCase().includes("review") &&
        !batch.batch_id.toLowerCase().includes("qc")
      );
    }

    return true;
  });

  const batchRows = filteredBatches.map((batch) => ({
    batch_id: batch.batch_id,
    name: batch.name,
    status: batch.status,
    documents: batch.documents,
    checked_out_by: batch.checked_out_by || "—",
  }));

  return (
    <AppShell>
      <PageContainer>
        <PageHeader
          title="Batch Management"
          subtitle={`Create and manage batches for ${projectId.replaceAll("_", " ")}.`}
        />

        <div className="grid grid-cols-3 gap-6 mb-6">
          <button
            type="button"
            onClick={() => setMode("review")}
            className={
              mode === "review"
                ? "bg-teal-600 text-white rounded-2xl p-5 text-left"
                : "bg-slate-900 border border-slate-800 text-slate-300 rounded-2xl p-5 text-left hover:bg-slate-800"
            }
          >
            <h2 className="text-xl font-semibold">Review Batches</h2>
            <p className="text-sm mt-2 opacity-80">
              Batch unbatched documents for first-pass review.
            </p>
          </button>

          <button
            type="button"
            onClick={() => setMode("qc")}
            className={
              mode === "qc"
                ? "bg-teal-600 text-white rounded-2xl p-5 text-left"
                : "bg-slate-900 border border-slate-800 text-slate-300 rounded-2xl p-5 text-left hover:bg-slate-800"
            }
          >
            <h2 className="text-xl font-semibold">QC Batches</h2>
            <p className="text-sm mt-2 opacity-80">
              Create QC batches from reviewed batches.
            </p>
          </button>

          <button
            type="button"
            onClick={() => setMode("alt")}
            className={
              mode === "alt"
                ? "bg-teal-600 text-white rounded-2xl p-5 text-left"
                : "bg-slate-900 border border-slate-800 text-slate-300 rounded-2xl p-5 text-left hover:bg-slate-800"
            }
          >
            <h2 className="text-xl font-semibold">Alt Batches</h2>
            <p className="text-sm mt-2 opacity-80">
              Create supplemental batches from Search Folders.
            </p>
          </button>
        </div>

        {message && (
          <p className="text-sm text-teal-400 mb-6">
            {message}
          </p>
        )}

        {mode === "review" && (
          <ContentCard title="Create Review Batches">
            <BatchCreateControls
              batchName={batchName}
              setBatchName={setBatchName}
              docsPerBatch={docsPerBatch}
              setDocsPerBatch={setDocsPerBatch}
              onCreate={createReviewBatches}
              buttonLabel="Create Review Batches"
            />

            <div className="grid grid-cols-2 gap-6 mt-8">
              <div>
                <h3 className="text-lg font-semibold mb-4">
                  Project Files / Unbatched Documents
                </h3>

                <div className="max-h-[60vh] overflow-auto">
                  <DataTable columns={fileColumns} data={files} />
                </div>
              </div>

              <div>
                <h3 className="text-lg font-semibold mb-4">
                  Review Batch Status
                </h3>

                <div className="max-h-[60vh] overflow-auto">
                  <DataTable columns={batchColumns} data={batchRows} />
                </div>
              </div>
            </div>
          </ContentCard>
        )}

        {mode === "qc" && (
          <ContentCard title="Create QC Batches">
            <BatchCreateControls
              batchName={batchName}
              setBatchName={setBatchName}
              docsPerBatch={docsPerBatch}
              setDocsPerBatch={setDocsPerBatch}
              onCreate={createQCBatches}
              buttonLabel="Create QC Batches"
            />

            <div className="mt-8">
              <h3 className="text-lg font-semibold mb-4">
                Reviewed Batches Available for QC
              </h3>
              <DataTable columns={batchColumns} data={batchRows} />
            </div>
          </ContentCard>
        )}

        {mode === "alt" && (
          <ContentCard title="Create Alt Batch from Search Folder">
            <FormLabel>Search Folder</FormLabel>
            <div className="mb-4">
              <Select
                value={selectedFolderId}
                onChange={setSelectedFolderId}
              >
                <option value="">Select Search Folder</option>
                {searchFolders.map((folder) => (
                  <option key={folder.folder_id} value={folder.folder_id}>
                    {folder.folder_name} ({folder.document_count} docs)
                  </option>
                ))}
              </Select>
            </div>

            <BatchCreateControls
              batchName={batchName}
              setBatchName={setBatchName}
              docsPerBatch={docsPerBatch}
              setDocsPerBatch={setDocsPerBatch}
              onCreate={createAltBatch}
              buttonLabel="Create Alt Batch"
            />
            <div className="mt-8">
              <h3 className="text-lg font-semibold mb-4">
                Alt Batch Status
              </h3>

              <DataTable columns={batchColumns} data={batchRows} />
            </div>
          </ContentCard>
        )}
      </PageContainer>
    </AppShell>
  );
}

function BatchCreateControls({
  batchName,
  setBatchName,
  docsPerBatch,
  setDocsPerBatch,
  onCreate,
  buttonLabel,
}: {
  batchName: string;
  setBatchName: (value: string) => void;
  docsPerBatch: string;
  setDocsPerBatch: (value: string) => void;
  onCreate: () => void;
  buttonLabel: string;
}) {
  return (
    <div className="grid grid-cols-3 gap-4 items-end">
      <div>
        <FormLabel>Batch Name Prefix</FormLabel>
        <Input
          value={batchName}
          onChange={setBatchName}
          placeholder="Example: Review"
        />
      </div>

      <div>
        <FormLabel>Docs Per Batch</FormLabel>
        <Select
          value={docsPerBatch}
          onChange={setDocsPerBatch}
        >
          <option value="1">1</option>
          <option value="5">5</option>
          <option value="10">10</option>
          <option value="20">20</option>
          <option value="50">50</option>
        </Select>
      </div>

      <Button fullWidth onClick={onCreate}>
        {buttonLabel}
      </Button>
    </div>
  );
}

function ReviewerBatches({
  projectId,
  batches,
  message,
  checkoutBatch,
  router,
}: {
  projectId: string;
  batches: Batch[];
  message: string;
  checkoutBatch: (batchId: string) => void;
  router: ReturnType<typeof useRouter>;
}) {
  return (
    <AppShell>
      <PageContainer>
        <PageHeader
          title="Batches"
          subtitle={`Batch status for ${projectId.replaceAll("_", " ")}.`}
        />

        {message && (
          <p className="text-sm text-teal-400 mb-6">
            {message}
          </p>
        )}

        <div className="grid grid-cols-3 gap-6">
          {batches.map((batch) => {
            const isAvailable = batch.status === "Available";
            const isCheckedOut = batch.status === "Checked Out";
            const isCompleted = batch.status === "Completed";

            return (
              <ContentCard key={batch.batch_id} title={batch.name}>
                <div className="mb-4">
                  <StatusBadge>{batch.status}</StatusBadge>
                </div>

                <div className="space-y-2 text-slate-300 mb-6">
                  <p>Documents: {batch.documents}</p>

                  <p>
                    Checked out by:{" "}
                    <span className="text-white">
                      {batch.checked_out_by || "—"}
                    </span>
                  </p>
                </div>

                {isAvailable && (
                  <Button
                    fullWidth
                    onClick={() => checkoutBatch(batch.batch_id)}
                  >
                    Check Out Batch
                  </Button>
                )}

                {isCheckedOut && (
                  <Button
                    fullWidth
                    variant="secondary"
                    onClick={() =>
                      router.push(
                        `/review?project=${projectId}&batch=${batch.batch_id}`
                      )
                    }
                  >
                    Open Review
                  </Button>
                )}

                {isCompleted && (
                  <Button fullWidth variant="secondary">
                    Completed
                  </Button>
                )}
              </ContentCard>
            );
          })}
        </div>
      </PageContainer>
    </AppShell>
  );
}

export default function BatchesPage() {
  return (
    <Suspense fallback={<div>Loading batches...</div>}>
      <BatchesPageContent />
    </Suspense>
  );
}