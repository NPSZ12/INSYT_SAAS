"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams, useRouter } from "next/navigation";

import AppShell from "../../../components/AppShell";
import PageContainer from "../../../components/PageContainer";
import PageHeader from "../../../components/PageHeader";
import ContentCard from "../../../components/ContentCard";
import Button from "../../../components/Button";
import Input from "../../../components/Input";
import Select from "../../../components/Select";
import FormLabel from "../../../components/FormLabel";
import StatusBadge from "../../../components/StatusBadge";
import DataTable from "../../../components/DataTable";
import { apiGet, apiPost } from "../../../lib/api";

type Batch = {
  project_id: string;

  batch_id: string;
  batch_name?: string;

  name: string;
  status: string;

  documents: string;
  document_count?: number;
  completed_count?: number;
  doc_ids?: string[];

  checked_out_by: string | null;

  level?: string;
  workflow_type?: string;
  batch_size?: number;
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
  const clientId = searchParams.get("client") || "";

  const [user, setUser] = useState<StoredUser | null>(null);
  const [mode, setMode] =
    useState<"review" | "qc" | "alt" | "statqc">("review");

  const [batches, setBatches] = useState<Batch[]>([]);
  const [files, setFiles] = useState<ProjectFile[]>([]);
  const [searchFolders, setSearchFolders] = useState<SearchFolder[]>([]);

  const [batchName, setBatchName] = useState("");
  const [docsPerBatch, setDocsPerBatch] = useState("20");
  const [customDocsPerBatch, setCustomDocsPerBatch] = useState("");
  const [level, setLevel] = useState("1L");
  const [selectedFolderId, setSelectedFolderId] = useState("");
  const [message, setMessage] = useState("");
  const [docResponse, setDocResponse] = useState("Responsive");
  const [confidencePreset, setConfidencePreset] = useState("95_5");
  const [statFormat, setStatFormat] = useState("Random Generator");
  const [statOtherFormat, setStatOtherFormat] = useState("");

  

  useEffect(() => {
    const storedUser = localStorage.getItem("insyt_user");

    if (storedUser) {
      setUser(JSON.parse(storedUser));
    }
  }, []);

  const isAdmin =
    user?.role === "INSYT Admin" ||
    user?.role === "RM" ||
    user?.role === "TL" ||
    user?.role === "QC";

  function loadBatches() {
    if (!clientId || !projectId) return;

    console.log("LOAD BATCHES", {
      clientId,
      projectId,
    });

    apiGet(
      `/api/summaries/projects/${encodeURIComponent(
        projectId
      )}/batches?client=${encodeURIComponent(clientId)}`
    )
      .then((response) => {
        console.log("BATCH RESPONSE", response);
        console.log(
          "BATCHES RAW JSON",
          JSON.stringify(response.batches, null, 2)
        );
        const normalizedBatches = (response.batches || []).map((batch: any) => {
          const batchName = batch.batch_name || batch.batch_id || batch.name;

          return {
            project_id: batch.project_id,
            batch_id: batchName,
            batch_name: batchName,
            name: batchName,
            status: batch.status || "Available",
            documents: String(batch.document_count || batch.documents || 0),
            document_count:
              batch.document_count ||
              batch.doc_ids?.length ||
              Number(batch.documents || 0),
            completed_count: batch.completed_count || 0,
            checked_out_by: batch.checked_out_by || "",
            level: batch.level || "1L",
            workflow_type: batch.workflow_type || "standard",
            batch_size: batch.batch_size || batch.doc_ids?.length || 0,
            doc_ids: batch.doc_ids || [],
          };
        });

        setBatches(normalizedBatches);
      })
      .catch((error) => {
        console.error(error);
        setBatches([]);
      });
  }

  function loadFiles() {
    if (!clientId || !projectId) return;

    apiGet(
      `/api/summaries/files?client=${encodeURIComponent(
        clientId
      )}&project=${encodeURIComponent(
        projectId
      )}&folder=${encodeURIComponent("source/native")}`
    )
      .then(setFiles)
      .catch(console.error);
  }

  function loadSearchFolders() {
    if (!clientId || !projectId) return;

    apiGet(
      `/api/search-folders/?client=${encodeURIComponent(
        clientId
      )}&project=${encodeURIComponent(projectId)}`
    )
      .then(setSearchFolders)
      .catch(console.error);
  }

  useEffect(() => {
    loadBatches();
    loadFiles();
    loadSearchFolders();
  }, [clientId, projectId]);

  function createStatisticalQCBatches() {
    if (!clientId || !projectId) return;

    apiPost(
      `/api/summaries/projects/${encodeURIComponent(
        projectId
      )}/batches/create?client=${encodeURIComponent(clientId)}`,
      {
      batch_size:
        docsPerBatch === "Custom"
          ? Number(customDocsPerBatch)
          : Number(docsPerBatch),

      level: "Statistical QC",
      workflow_type: "statistical_qc",
      created_by: user?.username || "admin",
      search_folder_doc_ids: null,

      options: {
        batch_name: batchName || "Statistical_QC",
        doc_response: docResponse,
        confidence_preset: confidencePreset,
        statistical_sampling: true,
        format: statFormat,
        other_format: statOtherFormat,
      },
    })
      .then((response) => {
        setMessage(
          response.message || "Statistical QC batch created."
        );

        setBatchName("");
        loadBatches();
      })
      .catch((error) => {
        console.error(error);
        setMessage("Statistical QC batch creation failed.");
      });
  }
  
  
  function checkoutBatch(batchId: string) {
    if (!clientId || !projectId || !user) return;

    apiPost(
      `/api/summaries/projects/${encodeURIComponent(
        projectId
      )}/batches/checkout?client=${encodeURIComponent(clientId)}`,
      {
        batch_name: batchId,
        username: user.username,
      }
    )
      .then((response) => {
        setMessage(response.message || "Batch checked out.");
        loadBatches();
      })
      .catch((error) => {
        console.error(error);
        setMessage("Batch checkout failed.");
      });
  }

  function createReviewBatches() {
    if (!clientId || !projectId) return;

    apiPost(
      `/api/summaries/projects/${encodeURIComponent(
        projectId
      )}/batches/create?client=${encodeURIComponent(clientId)}`,
      {
      batch_size:
        docsPerBatch === "Custom"
          ? Number(customDocsPerBatch)
          : Number(docsPerBatch),
      level: "1L",
      workflow_type: "standard",
      created_by: user?.username || "admin",
      search_folder_doc_ids: null,
    })
      .then((response) => {
        setMessage(response.message || "Review batch created.");
        setBatchName("");
        loadBatches();
        loadFiles();
      })
      .catch(() => setMessage("Review batch creation failed."));
  }

  function createQCBatches() {
    if (!clientId || !projectId) return;

    apiPost(
      `/api/summaries/projects/${encodeURIComponent(
        projectId
      )}/batches/create?client=${encodeURIComponent(clientId)}`,
      {
      batch_size:
        docsPerBatch === "Custom"
          ? Number(customDocsPerBatch)
          : Number(docsPerBatch),
      level: "QC",
      workflow_type: "standard",
      created_by: user?.username || "admin",
      search_folder_doc_ids: null,
    })
      .then((response) => {
        setMessage(response.message || "QC batch created.");
        setBatchName("");
        loadBatches();
      })
      .catch(() => setMessage("QC batch creation failed."));
  }

  function createAltBatch() {
    if (!clientId || !projectId || !selectedFolderId) return;

    apiPost(
      `/api/summaries/projects/${encodeURIComponent(
        projectId
      )}/batches/create?client=${encodeURIComponent(clientId)}`,
      {
      batch_size:
        docsPerBatch === "Custom"
          ? Number(customDocsPerBatch)
          : Number(docsPerBatch),
      level: "ALT Workflow",
      workflow_type: "alt_workflow",
      created_by: user?.username || "admin",
      search_folder_doc_ids: [`folder:${selectedFolderId}`],
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
        clientId={clientId}
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
    { key: "batch_id", label: "Name" },
    { key: "level", label: "Level" },
    { key: "status", label: "Status" },
    { key: "documents", label: "Docs" },
    { key: "reviewed", label: "Reviewed" },
    { key: "pending", label: "Pending" },
    { key: "workflow_type", label: "Workflow" },
    { key: "checked_out_by", label: "Checked Out By" },
  ];

  const filteredBatches = batches.filter((batch) => {
    if (mode === "review") {
      return batch.level === "1L";
    }

    if (mode === "qc") {
      return batch.level === "QC";
    }

    if (mode === "alt") {
      return batch.level === "ALT Workflow";
    }

    return true;
  });

  const batchRows = filteredBatches.map((batch) => {
    const totalDocs =
      batch.document_count || 0;

    const reviewedCount =
      batch.completed_count || 0;

    return {
      batch_id: batch.batch_id,
      level: batch.level || "1L",
      status: batch.status,

      documents: totalDocs,
      reviewed: reviewedCount,
      pending: Math.max(
        totalDocs - reviewedCount,
        0
      ),

      workflow_type:
        batch.workflow_type || "standard",

      checked_out_by:
        batch.checked_out_by || "—",
    };
  });

  return (
    <AppShell>
      <PageContainer>
        <PageHeader
          title="Batch Management"
          subtitle={`Create and manage batches for ${projectId.replaceAll("_", " ")}.`}
        />

        <div className="grid grid-cols-4 gap-6 mb-6">
          <button
            type="button"
            onClick={() => setMode("review")}
            className={
              mode === "review"
                ? "bg-lime-50 text-slate-700 rounded-2xl p-5 text-left"
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
                ? "bg-lime-50 text-slate-700 rounded-2xl p-5 text-left"
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
                ? "bg-lime-50 text-slate-700 rounded-2xl p-5 text-left"
                : "bg-slate-900 border border-slate-800 text-slate-300 rounded-2xl p-5 text-left hover:bg-slate-800"
            }
          >
            <h2 className="text-xl font-semibold">Alt Batches</h2>
            <p className="text-sm mt-2 opacity-80">
              Create supplemental batches from Search Folders.
            </p>
          </button>
          <button
            type="button"
            onClick={() => setMode("statqc")}
            className={
              mode === "statqc"
                ? "bg-lime-50 text-slate-700 rounded-2xl p-5 text-left"
                : "bg-slate-900 border border-slate-800 text-slate-300 rounded-2xl p-5 text-left hover:bg-slate-800"
            }
          >
            <h2 className="insyt-workspace text-xl font-semibold">
              Statistical QC
            </h2>

            <p className="text-sm mt-2 opacity-80">
              Random QC sampling using confidence interval and margin of error.
            </p>
          </button>
        </div>

        {message && (
          <p className="text-sm text-sky-400 mb-6">
            {message}
          </p>
        )}

        {mode === "review" && (
          <ContentCard title="Create Review Batches">
            <BatchCreateControls
              batchName={batchName}
              setBatchName={setBatchName}
              docsPerBatch={docsPerBatch}
              customDocsPerBatch={customDocsPerBatch}
              setCustomDocsPerBatch={setCustomDocsPerBatch}
              level={level}
              setLevel={setLevel}
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

            <div className="mt-8">
              <h3 className="text-lg font-semibold mb-4">
                Batch Document Management
              </h3>

              <div className="bg-slate-950 border border-slate-800 rounded-xl overflow-auto max-h-[50vh]">
                <table className="w-full text-xs table-auto">
                  <thead className="bg-slate-900 text-slate-400 sticky top-0 z-20">
                    <tr>
                      <th className="p-3 text-left">Batch</th>
                      <th className="p-3 text-left">Level</th>
                      <th className="p-3 text-left">Status</th>
                      <th className="p-3 text-left">Documents</th>
                      <th className="p-3 text-left">Actions</th>
                    </tr>
                  </thead>

                  <tbody>
                    {filteredBatches.map((batch) => (
                      <tr
                        key={batch.batch_id}
                        className="border-t border-slate-800 align-top"
                      >
                        <td className="p-3 text-white">
                          {batch.batch_id}
                        </td>

                        <td className="p-3 text-slate-300">
                          {batch.level || "1L"}
                        </td>

                        <td className="p-3 text-slate-300">
                          {batch.status}
                        </td>

                        <td className="p-3 text-slate-300 max-w-[400px] break-words">
                          {(batch.doc_ids || []).join(", ")}
                        </td>

                        <td className="p-3">
                          <div className="flex flex-col gap-2">
                            <Button
                              variant="secondary"
                              onClick={() => {
                                console.log(
                                  "TODO: Remove docs and preserve summariesd data",
                                  batch.batch_id
                                );
                              }}
                            >
                              Remove Docs + Save Data
                            </Button>

                            <Button
                              variant="danger"
                              onClick={() => {
                                console.log(
                                  "TODO: Remove docs without preserving data",
                                  batch.batch_id
                                );
                              }}
                            >
                              Remove Docs Without Saving
                            </Button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
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
              customDocsPerBatch={customDocsPerBatch}
              setCustomDocsPerBatch={setCustomDocsPerBatch}
              level={level}
              setLevel={setLevel}
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
              customDocsPerBatch={customDocsPerBatch}
              setCustomDocsPerBatch={setCustomDocsPerBatch}
              level={level}
              setLevel={setLevel}
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

        {mode === "statqc" && (
          <ContentCard title="Create Statistical QC Batch">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 items-end">
              <div>
                <FormLabel>Batch Name</FormLabel>
                <Input
                  value={batchName}
                  onChange={setBatchName}
                  placeholder="Example: Statistical_QC"
                />
              </div>

              <div>
                <FormLabel>Docs / Batch</FormLabel>
                <Select value={docsPerBatch} onChange={setDocsPerBatch}>
                  <option value="1">1</option>
                  <option value="5">5</option>
                  <option value="10">10</option>
                  <option value="20">20</option>
                  <option value="50">50</option>
                  <option value="Custom">Custom</option>
                </Select>
              </div>

              <div>
                <FormLabel>Doc Response</FormLabel>
                <Select value={docResponse} onChange={setDocResponse}>
                  <option value="Responsive">Responsive</option>
                  <option value="Not Responsive">Not Responsive</option>
                  <option value="Tech Issue">Tech Issue</option>
                  <option value="Foreign Language">Foreign Language</option>
                  <option value="Password Protected">Password Protected</option>
                  <option value="Needs Further Review">Needs Further Review</option>
                </Select>
              </div>

              <div>
                <FormLabel>Confidence</FormLabel>
                <Select value={confidencePreset} onChange={setConfidencePreset}>
                  <option value="90_10">90% Confidence / 10% Margin</option>
                  <option value="90_5">90% Confidence / 5% Margin</option>
                  <option value="95_10">95% Confidence / 10% Margin</option>
                  <option value="95_5">95% Confidence / 5% Margin</option>
                  <option value="99_5">99% Confidence / 5% Margin</option>
                  <option value="custom">Custom</option>
                </Select>
              </div>

              <div>
                <FormLabel>Format</FormLabel>
                <Select value={statFormat} onChange={setStatFormat}>
                  <option value="Random Generator">Random Generator</option>
                  <option value="Other">Other</option>
                </Select>
              </div>

              {statFormat === "Other" && (
                <div>
                  <FormLabel>Other Format</FormLabel>
                  <Input
                    value={statOtherFormat}
                    onChange={setStatOtherFormat}
                    placeholder="Describe format"
                  />
                </div>
              )}

              <Button onClick={createStatisticalQCBatches}>
                Create Statistical QC Batch
              </Button>
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
  customDocsPerBatch,
  setCustomDocsPerBatch,
  level,
  setLevel,
  onCreate,
  buttonLabel,
}: {
  batchName: string;
  setBatchName: (value: string) => void;

  docsPerBatch: string;
  setDocsPerBatch: (value: string) => void;

  customDocsPerBatch: string;
  setCustomDocsPerBatch: (value: string) => void;

  level: string;
  setLevel: (value: string) => void;

  onCreate: () => void;
  buttonLabel: string;
}) {
  return (
    <div className="grid grid-cols-4 gap-4 items-end">

      <div>
        <FormLabel>Batch Name Prefix</FormLabel>

        <Input
          value={batchName}
          onChange={setBatchName}
          placeholder="Example: Review"
        />
      </div>

      <div>
        <FormLabel>Docs / Batch</FormLabel>

        <Select
          value={docsPerBatch}
          onChange={setDocsPerBatch}
        >
          <option value="1">1</option>
          <option value="5">5</option>
          <option value="10">10</option>
          <option value="20">20</option>
          <option value="50">50</option>
          <option value="Custom">Custom</option>
        </Select>
      </div>

      {docsPerBatch === "Custom" && (
        <div>
          <FormLabel>Custom Count</FormLabel>

          <Input
            value={customDocsPerBatch}
            onChange={setCustomDocsPerBatch}
            placeholder="Enter custom count"
          />
        </div>
      )}

      <div>
        <FormLabel>Level</FormLabel>

        <Select
          value={level}
          onChange={setLevel}
        >
          <option value="1L">1L</option>
          <option value="QC">QC</option>
          <option value="ALT Workflow">
            ALT Workflow
          </option>
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
  clientId,
  batches,
  message,
  checkoutBatch,
  router,
}: {
  projectId: string;
  clientId: string;
  batches: Batch[];
  message: string;
  checkoutBatch: (batchId: string) => void;
  router: ReturnType<typeof useRouter>;
}) {
  function getBatchNumber(batchName: string) {
    const match = String(batchName || "").match(/(\d+)/);
    return match ? Number(match[1]) : 999999;
  }

  function getStatusRank(status: string) {
    const clean = String(status || "").toLowerCase();

    if (clean === "available") return 1;
    if (clean === "checked out") return 2;
    if (clean === "completed") return 3;

    return 4;
  }

  const sortedBatches = [...batches].sort((a, b) => {
    const statusDiff =
      getStatusRank(a.status) - getStatusRank(b.status);

    if (statusDiff !== 0) return statusDiff;

    return getBatchNumber(a.batch_id) - getBatchNumber(b.batch_id);
  });

  return (
    <AppShell>
      <PageContainer>
        <PageHeader
          title="Batches"
          subtitle={`Batch status for ${projectId.replaceAll("_", " ")}.`}
        />

        {message && (
          <p className="text-sm text-sky-400 mb-6">
            {message}
          </p>
        )}

        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {sortedBatches.map((batch) => {
            const totalDocs = batch.document_count || 0;
            const reviewed = batch.completed_count || 0;
            const pending = Math.max(totalDocs - reviewed, 0);

            return (
              <div
                key={batch.batch_id}
                className="bg-slate-950 border border-slate-800 rounded-xl p-4 min-h-[190px]"
              >
                <div className="flex items-start justify-between gap-3 mb-4">
                  <div>
                    <h3 className="text-white font-bold text-lg">
                      {batch.name}
                    </h3>

                    <p className="text-xs text-slate-400">
                      {batch.level || "1L"} •{" "}
                      {batch.workflow_type || "standard"}
                    </p>
                  </div>

                  <StatusBadge>{batch.status}</StatusBadge>
                </div>

                <div className="grid grid-cols-3 gap-2 text-center mb-4">
                  <div className="bg-slate-900 border border-slate-800 rounded-lg p-2">
                    <p className="text-[10px] text-slate-500 uppercase">
                      Docs
                    </p>
                    <p className="text-white font-semibold">
                      {totalDocs}
                    </p>
                  </div>

                  <div className="bg-slate-900 border border-slate-800 rounded-lg p-2">
                    <p className="text-[10px] text-slate-500 uppercase">
                      Reviewed
                    </p>
                    <p className="text-white font-semibold">
                      {reviewed}
                    </p>
                  </div>

                  <div className="bg-slate-900 border border-slate-800 rounded-lg p-2">
                    <p className="text-[10px] text-slate-500 uppercase">
                      Pending
                    </p>
                    <p className="text-white font-semibold">
                      {pending}
                    </p>
                  </div>
                </div>

                <div className="text-xs text-slate-400 mb-4 space-y-1">
                  <p>
                    Checked Out By:{" "}
                    <span className="text-slate-200">
                      {batch.checked_out_by || "—"}
                    </span>
                  </p>
                </div>

                <div>
                  {batch.status === "Available" && (
                    <Button
                      fullWidth
                      onClick={() => checkoutBatch(batch.batch_id)}
                    >
                      Check Out Batch
                    </Button>
                  )}

                  {batch.status === "Checked Out" && (
                    <Button
                      fullWidth
                      variant="secondary"
                      onClick={() =>
                        router.push(
                          `/summaries/review?client=${encodeURIComponent(
                            clientId
                          )}&project=${encodeURIComponent(
                            projectId
                          )}&batch=${encodeURIComponent(batch.batch_id)}`
                        )
                      }
                    >
                      Open Review
                    </Button>
                  )}

                  {batch.status === "Completed" && (
                    <Button fullWidth variant="secondary">
                      Completed
                    </Button>
                  )}
                </div>
              </div>
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











