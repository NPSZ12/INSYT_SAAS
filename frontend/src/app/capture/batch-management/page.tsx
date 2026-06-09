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

  const clientId = searchParams.get("client") || "";
  const projectId = searchParams.get("project");

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
  const [selectedQcSourceBatchId, setSelectedQcSourceBatchId] =
    useState("");

  const [qcSampleMode, setQcSampleMode] =
    useState("10");

  const [customQcPercent, setCustomQcPercent] =
    useState("");
  const [message, setMessage] = useState("");
  const [checkoutWarning, setCheckoutWarning] = useState<{
    title: string;
    message: string;
  } | null>(null);

  const [docResponse, setDocResponse] = useState("Responsive");
  const [confidencePreset, setConfidencePreset] = useState("95_5");
  const [statFormat, setStatFormat] = useState("Random Generator");
  const [statOtherFormat, setStatOtherFormat] = useState("");
  const [expandedBatchGroups, setExpandedBatchGroups] = useState<Record<string, boolean>>({});

  

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
    if (!projectId) return;

    apiGet(
      `/api/capture/projects/${encodeURIComponent(
        projectId
      )}/batches?client=${encodeURIComponent(clientId)}`
    )
      .then((response) => {
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
    if (!projectId) return;

    apiGet(
      `/api/capture/files?client=${encodeURIComponent(
        clientId
      )}&project=${encodeURIComponent(
        projectId
      )}&folder=${encodeURIComponent("source/native")}`
    )
      .then((response: any) => {
        const incomingFiles = Array.isArray(response)
          ? response
          : response?.files || [];

        setFiles(incomingFiles);
      })
      .catch(console.error);
  }

  function loadSearchFolders() {
    if (!projectId) return;

    apiGet(`/api/search-folders/?project=${projectId}`)
      .then(setSearchFolders)
      .catch(console.error);
  }

  useEffect(() => {
    loadBatches();
    loadFiles();
    loadSearchFolders();
  }, [clientId, projectId]);

  function createStatisticalQCBatches() {
    if (!projectId) return;

    apiPost(`/api/capture/projects/${encodeURIComponent(projectId)}/batches/create?client=${encodeURIComponent(clientId)}`, {
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
  
  function getCheckoutErrorMessage(error: any) {
    const rawMessage = String(error?.message || "");

    try {
      const jsonStart = rawMessage.indexOf("{");

      if (jsonStart >= 0) {
        const parsed = JSON.parse(rawMessage.slice(jsonStart));
        const detail = parsed?.detail;

        if (detail?.code === "ACTIVE_BATCH_ALREADY_CHECKED_OUT") {
          return (
            detail.message ||
            "You already have a batch checked out. Complete or release your current batch before checking out another batch."
          );
        }

        if (typeof detail === "string") {
          return detail;
        }
      }
    } catch {
      // Continue to fallback checks.
    }

    if (
      rawMessage.includes("ACTIVE_BATCH_ALREADY_CHECKED_OUT") ||
      rawMessage.includes("already have a batch checked out") ||
      rawMessage.includes("409")
    ) {
      return (
        "You already have a batch checked out. Complete or release your current batch before checking out another batch."
      );
    }

    return rawMessage || "Unable to check out batch.";
  }
  
  function checkoutBatch(batchId: string) {
    if (!projectId || !user) return;

    setMessage("");
    setCheckoutWarning(null);

    apiPost(
      `/api/capture/projects/${encodeURIComponent(
        projectId
      )}/batches/checkout?client=${encodeURIComponent(clientId)}`,
      {
        batch_name: batchId,
        username: user.username,
        role: user.role,
      }
    )
      .then((response) => {
        setMessage(response.message || "Batch checked out.");
        setCheckoutWarning(null);
        loadBatches();
      })
      .catch((error) => {
        console.error("Checkout failed:", error);

        const warningMessage = getCheckoutErrorMessage(error);

        setCheckoutWarning({
          title: "Batch Already Checked Out",
          message: warningMessage,
        });

        setMessage("");
      });
  }

  function openBatchReview(batch: Batch) {
    const firstDocId = batch.doc_ids?.[0] || "";

    if (!firstDocId) {
      alert("This batch has no assigned documents.");
      return;
    }

    router.push(
      `/capture/review/doc?client=${encodeURIComponent(
        clientId
      )}&project=${encodeURIComponent(
        projectId || ""
      )}&batch=${encodeURIComponent(
        batch.batch_id
      )}&doc=${encodeURIComponent(firstDocId)}`
    );
  }

  function removeBatchDocs(
    batchId: string,
    preserveData: boolean
  ) {
    if (!projectId) return;

    const confirmed = window.confirm(
      preserveData
        ? "Remove these documents from the batch while preserving all saved document coding and linked entity data?"
        : "Remove these documents from the batch only? Already-saved document-level data will not be deleted."
    );

    if (!confirmed) return;

    apiPost(
      `/api/capture/projects/${encodeURIComponent(
        projectId
      )}/batches/remove-docs?client=${encodeURIComponent(clientId)}`,
      {
        batch_name: batchId,
        preserve_data: preserveData,
        username: user?.username || "",
      }
    )
      .then((response) => {
        setMessage(
          response.message ||
            (preserveData
              ? "Documents removed from batch and saved data preserved."
              : "Documents removed from batch.")
        );

        loadBatches();
        loadFiles();
      })
      .catch((error) => {
        console.error(error);
        setMessage("Failed to remove documents from batch.");
      });
  }

  function createReviewBatches() {
    if (!projectId) return;

    apiPost(`/api/capture/projects/${encodeURIComponent(projectId)}/batches/create?client=${encodeURIComponent(clientId)}`, {
      batch_size:
        docsPerBatch === "Custom"
          ? Number(customDocsPerBatch)
          : Number(docsPerBatch),
      level: "1L",
      workflow_type: "standard",
      created_by: user?.username || "admin",
      search_folder_doc_ids: null,
      options: {
        batch_name: batchName || "Batch",
      },
    })
      .then((response) => {
        setMessage(response.message || "Review batch created.");
        setBatchName("");
        loadBatches();
        loadFiles();
      })
      .catch(() => setMessage("Review batch creation failed."));
  }

  function getQcBatchNamePrefix() {
    if (!selectedQcSourceBatchId) {
      return batchName || "QC";
    }

    return `QC_${selectedQcSourceBatchId}`;
  }

  function createQCBatches() {
    if (!projectId || !selectedQcSourceBatchId) {
      setMessage("Select a 1L batch for QC sampling first.");
      return;
    }

    const qcPercent =
      qcSampleMode === "custom"
        ? Number(customQcPercent)
        : Number(qcSampleMode);

    if (!qcPercent || qcPercent <= 0 || qcPercent > 100) {
      setMessage("Enter a QC sample percentage between 1 and 100.");
      return;
    }

    apiPost(
      `/api/capture/projects/${encodeURIComponent(
        projectId
      )}/batches/create?client=${encodeURIComponent(clientId)}`,
      {
        batch_size: 1,
        level: "QC",
        workflow_type: "qc_sample",
        created_by: user?.username || "admin",
        search_folder_doc_ids: null,
        options: {
          batch_name: getQcBatchNamePrefix(),
          source_batch_id: selectedQcSourceBatchId,
          qc_sampling: true,
          qc_sample_percentage: qcPercent,
        },
      }
    )
      .then((response) => {
        setMessage(response.message || "QC sample batch created.");
        setBatchName("");
        setSelectedQcSourceBatchId("");
        setQcSampleMode("10");
        setCustomQcPercent("");
        loadBatches();
      })
      .catch((error) => {
        console.error(error);
        setMessage("QC sample batch creation failed.");
      });
  }

  function createAltBatch() {
    if (!projectId || !selectedFolderId) return;

    apiPost(`/api/capture/projects/${encodeURIComponent(projectId)}/batches/create?client=${encodeURIComponent(clientId)}`, {
      batch_size:
        docsPerBatch === "Custom"
          ? Number(customDocsPerBatch)
          : Number(docsPerBatch),
      level: "ALT Workflow",
      workflow_type: "alt_workflow",
      created_by: user?.username || "admin",
      search_folder_doc_ids: [`folder:${selectedFolderId}`],
      options: {
        batch_name: batchName || "Alt",
      },
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
        clientId={clientId}
        projectId={projectId}
        batches={batches}
        message={message}
        checkoutBatch={checkoutBatch}
        openBatchReview={openBatchReview}
        user={user}
        checkoutWarning={checkoutWarning}
        setCheckoutWarning={setCheckoutWarning}
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

  function getBatchGroupKey(batchName: string) {
    const clean = String(batchName || "").trim();

    const match = clean.match(/^(.*?_)\d+$/);

    if (match) {
      return match[1];
    }

    return clean || "Ungrouped";
  }

  function getBatchStatusBucket(status: string) {
    const clean = String(status || "").toLowerCase();

    if (clean === "available") return "available";
    if (clean === "checked out" || clean === "in progress") return "inProgress";
    if (clean === "completed") return "completed";

    return "other";
  }

  function buildBatchGroups(groupBatches: Batch[]) {
    const grouped: Record<string, Batch[]> = {};

    groupBatches.forEach((batch) => {
      const groupKey = getBatchGroupKey(
        batch.batch_id || batch.name || ""
      );

      if (!grouped[groupKey]) {
        grouped[groupKey] = [];
      }

      grouped[groupKey].push(batch);
    });

    return Object.entries(grouped)
      .map(([groupKey, groupItems]) => {
        const sortedItems = [...groupItems].sort(
          (a, b) =>
            getBatchNumber(a.batch_id) -
            getBatchNumber(b.batch_id)
        );

        return {
          groupKey,
          batches: sortedItems,
          total: sortedItems.length,
          available: sortedItems.filter(
            (batch) =>
              getBatchStatusBucket(batch.status) === "available"
          ).length,
          inProgress: sortedItems.filter(
            (batch) =>
              getBatchStatusBucket(batch.status) === "inProgress"
          ).length,
          completed: sortedItems.filter(
            (batch) =>
              getBatchStatusBucket(batch.status) === "completed"
          ).length,
        };
      })
      .sort((a, b) =>
        a.groupKey.localeCompare(b.groupKey, undefined, {
          numeric: true,
        })
      );
  }

  const filteredBatches = [...batches]
    .filter((batch) => {
      if (mode === "review") return batch.level === "1L";
      if (mode === "qc") return batch.level === "QC";
      if (mode === "alt") return batch.level === "ALT Workflow";
      return true;
    })
    .sort((a, b) => {
      const statusDiff =
        getStatusRank(a.status) - getStatusRank(b.status);

      if (statusDiff !== 0) return statusDiff;

      return getBatchNumber(a.batch_id) - getBatchNumber(b.batch_id);
    });

  const eligibleQcSourceBatches = batches.filter((batch) => {
    const status = String(batch.status || "")
      .toLowerCase()
      .replaceAll("_", " ");

    return (
      batch.level === "1L" &&
      (
        status === "checked out" ||
        status === "in progress" ||
        status === "completed"
      ) &&
      (batch.doc_ids || []).length > 0
    );
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

  const batchGroups = buildBatchGroups(filteredBatches);

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

                <BatchGroupDirectory
                  batchGroups={batchGroups}
                  expandedBatchGroups={expandedBatchGroups}
                  setExpandedBatchGroups={setExpandedBatchGroups}
                  checkoutBatch={checkoutBatch}
                  openBatchReview={openBatchReview}
                  removeBatchDocs={removeBatchDocs}
                  showDocumentList
                  user={user}
                />
              </div>
            </div>
          </ContentCard>
        )}

        {mode === "qc" && (
          <ContentCard title="Create QC Batch from 1L Batch">
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4 items-end">
              <div>
                <FormLabel>Batch Name Prefix</FormLabel>
                <div className="rounded-xl border border-slate-800 bg-slate-950 px-4 py-3 text-sm text-slate-200 min-h-[46px] flex items-center">
                  {getQcBatchNamePrefix()}
                </div>
              </div>

              <div>
                <FormLabel>1L Batch</FormLabel>
                <Select
                  value={selectedQcSourceBatchId}
                  onChange={setSelectedQcSourceBatchId}
                >
                  <option value="">Select 1L Batch</option>

                  {eligibleQcSourceBatches.map((batch) => (
                    <option key={batch.batch_id} value={batch.batch_id}>
                      {batch.batch_id} - {batch.status} ({batch.doc_ids?.length || 0} docs)
                    </option>
                  ))}
                </Select>
              </div>

              <div>
                <FormLabel>QC Sample</FormLabel>
                <Select
                  value={qcSampleMode}
                  onChange={setQcSampleMode}
                >
                  <option value="10">Random 10%</option>
                  <option value="15">Random 15%</option>
                  <option value="20">Random 20%</option>
                  <option value="custom">Random Custom</option>
                </Select>
              </div>

              {qcSampleMode === "custom" && (
                <div>
                  <FormLabel>Custom Percentage</FormLabel>
                  <Input
                    value={customQcPercent}
                    onChange={setCustomQcPercent}
                    placeholder="Example: 25"
                  />
                </div>
              )}

              <Button fullWidth onClick={createQCBatches}>
                Create QC Batch
              </Button>
            </div>

            <div className="mt-8">
              <h3 className="text-lg font-semibold mb-4">
                QC Batch Status
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

        {checkoutWarning && (
          <div className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/70 p-6">
            <div className="w-full max-w-md rounded-2xl border border-amber-500 bg-slate-950 p-6 shadow-2xl">
              <h2 className="text-xl font-semibold text-white">
                {checkoutWarning.title}
              </h2>

              <p className="mt-3 text-sm leading-6 text-slate-300">
                {checkoutWarning.message}
              </p>

              <div className="mt-6 flex justify-end">
                <Button onClick={() => setCheckoutWarning(null)}>
                  OK
                </Button>
              </div>
            </div>
          </div>
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

function BatchGroupDirectory({
  batchGroups,
  expandedBatchGroups,
  setExpandedBatchGroups,
  checkoutBatch,
  openBatchReview,
  removeBatchDocs,
  showDocumentList = false,
  user,
}: {
  batchGroups: {
    groupKey: string;
    batches: Batch[];
    total: number;
    available: number;
    inProgress: number;
    completed: number;
  }[];
  expandedBatchGroups: Record<string, boolean>;
  setExpandedBatchGroups: React.Dispatch<
    React.SetStateAction<Record<string, boolean>>
  >;
  checkoutBatch: (batchId: string) => void;
  openBatchReview: (batch: Batch) => void;
  removeBatchDocs?: (batchId: string, preserveData: boolean) => void;
  showDocumentList?: boolean;
  user?: StoredUser | null;
}) {
  const qcAndUpRoles = [
    "QC",
    "TL",
    "RM",
    "CDS Admin",
    "INSYT Admin",
  ];

  function canOpenAnyBatch(role?: string) {
    return qcAndUpRoles.includes(role || "");
  }

  return (
    <div className="space-y-3 max-h-[60vh] overflow-auto">
      {batchGroups.map((group) => {
        const isExpanded =
          expandedBatchGroups[group.groupKey] || false;

        return (
          <div
            key={group.groupKey}
            className="border border-slate-800 bg-slate-950 rounded-xl overflow-hidden"
          >
            <button
              type="button"
              onClick={() =>
                setExpandedBatchGroups((current) => ({
                  ...current,
                  [group.groupKey]: !isExpanded,
                }))
              }
              className="w-full px-4 py-3 bg-slate-900 hover:bg-slate-800 text-left"
            >
              <div className="flex flex-wrap items-center gap-4 text-sm">
                <span className="text-white font-semibold">
                  {isExpanded ? "▾" : "▸"} {group.groupKey}
                </span>

                <span className="text-slate-300">
                  Total Batches: {group.total}
                </span>

                <span className="text-emerald-300">
                  Available: {group.available}
                </span>

                <span className="text-sky-300">
                  In Progress: {group.inProgress}
                </span>

                <span className="text-lime-300">
                  Completed: {group.completed}
                </span>
              </div>
            </button>

            {isExpanded && (
              <div className="border-t border-slate-800">
                <div
                  className="overflow-x-scroll border-b border-slate-800 bg-slate-950 h-4"
                  onScroll={(event) => {
                    const tableScroller =
                      event.currentTarget.nextElementSibling as HTMLDivElement | null;

                    if (tableScroller) {
                      tableScroller.scrollLeft =
                        event.currentTarget.scrollLeft;
                    }
                  }}
                >
                  <div className="min-w-[1200px] h-1" />
                </div>

                <div
                  className="max-h-[56vh] overflow-auto"
                  onScroll={(event) => {
                    const topScroller =
                      event.currentTarget.previousElementSibling as HTMLDivElement | null;

                    if (topScroller) {
                      topScroller.scrollLeft =
                        event.currentTarget.scrollLeft;
                    }
                  }}
                >
                  <table className="min-w-[1200px] w-full text-xs">
                    <thead className="bg-slate-900/70 text-slate-400">
                      <tr>
                        <th className="p-2 text-left">Name</th>
                        <th className="p-2 text-left">Level</th>
                        <th className="p-2 text-left">Status</th>
                        <th className="p-2 text-left">Docs</th>
                        <th className="p-2 text-left">Reviewed</th>
                        <th className="p-2 text-left">Pending</th>

                        {showDocumentList && (
                          <th className="p-2 text-left">Documents</th>
                        )}

                        <th className="p-2 text-left">Checked Out By</th>
                        <th className="p-2 text-left">Actions</th>
                      </tr>
                    </thead>

                    <tbody>
                      {group.batches.map((batch) => {
                        const totalDocs =
                          batch.document_count ||
                          Number(batch.documents || 0);

                        const reviewed =
                          batch.completed_count || 0;

                        const pending = Math.max(
                          totalDocs - reviewed,
                          0
                        );

                        return (
                          <tr
                            key={batch.batch_id}
                            className="border-t border-slate-800 hover:bg-slate-900/60"
                          >
                            <td className="p-2 text-white whitespace-nowrap">
                              {batch.batch_id}
                            </td>

                            <td className="p-2 text-slate-300 whitespace-nowrap">
                              {batch.level || "1L"}
                            </td>

                            <td className="p-2 text-slate-300 whitespace-nowrap">
                              <StatusBadge>{batch.status}</StatusBadge>
                            </td>

                            <td className="p-2 text-slate-300 whitespace-nowrap">
                              {totalDocs}
                            </td>

                            <td className="p-2 text-slate-300 whitespace-nowrap">
                              {reviewed}
                            </td>

                            <td className="p-2 text-slate-300 whitespace-nowrap">
                              {pending}
                            </td>

                            {showDocumentList && (
                              <td className="p-2 text-slate-300 max-w-[260px]">
                                <div className="max-h-20 overflow-auto rounded border border-slate-800 bg-slate-900 p-2 text-[11px] leading-5">
                                  {(batch.doc_ids || []).join(", ")}
                                </div>
                              </td>
                            )}

                            <td className="p-2 text-slate-300 whitespace-nowrap">
                              {batch.checked_out_by || "—"}
                            </td>

                            <td className="p-2 align-top min-w-[220px]">
                              <div className="flex flex-col gap-2">
                                {batch.status === "Available" && (
                                  <button
                                    type="button"
                                    onClick={() =>
                                      checkoutBatch(batch.batch_id)
                                    }
                                    className="rounded-lg border border-sky-500/50 bg-sky-500/10 px-3 py-1.5 text-xs font-semibold text-sky-300 hover:bg-sky-500/20 hover:text-sky-200 transition"
                                  >
                                    Check Out
                                  </button>
                                )}

                                {(
                                  canOpenAnyBatch(user?.role) ||
                                  (
                                    batch.status === "Checked Out" &&
                                    batch.checked_out_by === user?.username
                                  )
                                ) && (
                                  <Button
                                    variant="secondary"
                                    onClick={() =>
                                      openBatchReview(batch)
                                    }
                                  >
                                    Open Review
                                  </Button>
                                )}

                                {batch.status === "Completed" && (
                                  <Button variant="secondary">
                                    Completed
                                  </Button>
                                )}

                                {removeBatchDocs && (
                                  <>
                                    <button
                                      type="button"
                                      onClick={() =>
                                        removeBatchDocs(batch.batch_id, true)
                                      }
                                      className="rounded-lg border border-orange-500/50 bg-orange-500/10 px-3 py-1.5 text-xs font-semibold text-orange-300 hover:bg-orange-500/20 hover:text-orange-200 transition"
                                    >
                                      Remove Docs + Save Data
                                    </button>

                                    <button
                                      type="button"
                                      onClick={() =>
                                        removeBatchDocs(batch.batch_id, false)
                                      }
                                      className="rounded-lg border border-red-500/50 bg-red-500/10 px-3 py-1.5 text-xs font-semibold text-red-300 hover:bg-red-500/20 hover:text-red-200 transition"
                                    >
                                      Remove Docs Without Saving
                                    </button>
                                  </>
                                )}
                              </div>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

function ReviewerBatches({
  clientId,
  projectId,
  batches,
  message,
  checkoutBatch,
  openBatchReview,
  user,
  checkoutWarning,
  setCheckoutWarning,
}: {
  clientId: string;
  projectId: string;
  batches: Batch[];
  message: string;
  checkoutBatch: (batchId: string) => void;
  openBatchReview: (batch: Batch) => void;
  user: StoredUser | null;
  checkoutWarning: {
    title: string;
    message: string;
  } | null;
  setCheckoutWarning: React.Dispatch<
    React.SetStateAction<{
      title: string;
      message: string;
    } | null>
  >;
}) {
  
  const [expandedBatchGroups, setExpandedBatchGroups] =
  useState<Record<string, boolean>>({});

  function getBatchGroupKey(batchName: string) {
    const clean = String(batchName || "").trim();
    const match = clean.match(/^(.*?_)\d+$/);

    if (match) {
      return match[1];
    }

    return clean || "Ungrouped";
  }

  function getBatchNumber(batchName: string) {
    const match = String(batchName || "").match(/(\d+)/);
    return match ? Number(match[1]) : 999999;
  }

  function getBatchStatusBucket(status: string) {
    const clean = String(status || "").toLowerCase();

    if (clean === "available") return "available";
    if (clean === "checked out" || clean === "in progress") return "inProgress";
    if (clean === "completed") return "completed";

    return "other";
  }

  const batchGroups = Object.entries(
    batches.reduce<Record<string, Batch[]>>((groups, batch) => {
      const groupKey = getBatchGroupKey(
        batch.batch_id || batch.name || ""
      );

      if (!groups[groupKey]) {
        groups[groupKey] = [];
      }

      groups[groupKey].push(batch);
      return groups;
    }, {})
  )
    .map(([groupKey, groupItems]) => {
      const sortedItems = [...groupItems].sort(
        (a, b) =>
          getBatchNumber(a.batch_id) -
          getBatchNumber(b.batch_id)
      );

      return {
        groupKey,
        batches: sortedItems,
        total: sortedItems.length,
        available: sortedItems.filter(
          (batch) =>
            getBatchStatusBucket(batch.status) === "available"
        ).length,
        inProgress: sortedItems.filter(
          (batch) =>
            getBatchStatusBucket(batch.status) === "inProgress"
        ).length,
        completed: sortedItems.filter(
          (batch) =>
            getBatchStatusBucket(batch.status) === "completed"
        ).length,
      };
    })
    .sort((a, b) =>
      a.groupKey.localeCompare(b.groupKey, undefined, {
        numeric: true,
      })
    );
  
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

        <BatchGroupDirectory
          batchGroups={batchGroups}
          expandedBatchGroups={expandedBatchGroups}
          setExpandedBatchGroups={setExpandedBatchGroups}
          checkoutBatch={checkoutBatch}
          openBatchReview={openBatchReview}
          user={user}
        />

        {checkoutWarning && (
          <div className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/80 p-6">
            <div className="w-full max-w-lg rounded-3xl border-2 border-amber-500 bg-slate-950 p-8 shadow-2xl">
              <div className="mb-5 flex items-center gap-3">
                <div className="flex h-12 w-12 items-center justify-center rounded-full bg-amber-500 text-2xl font-bold text-slate-950">
                  !
                </div>

                <div>
                  <h2 className="text-2xl font-bold text-white">
                    {checkoutWarning.title}
                  </h2>

                  <p className="text-sm text-slate-400">
                    Checkout restriction
                  </p>
                </div>
              </div>

              <div className="mb-6 rounded-2xl border border-slate-800 bg-slate-900 p-5">
                <p className="whitespace-pre-wrap text-base leading-7 text-slate-100">
                  {checkoutWarning.message}
                </p>
              </div>

              <div className="flex justify-end">
                <Button onClick={() => setCheckoutWarning(null)}>
                  OK
                </Button>
              </div>
            </div>
          </div>
        )}

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