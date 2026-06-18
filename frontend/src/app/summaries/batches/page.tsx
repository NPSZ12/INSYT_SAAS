"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import AppShell from "../../../components/AppShell";
import PageContainer from "../../../components/PageContainer";
import PageHeader from "../../../components/PageHeader";
import ContentCard from "../../../components/ContentCard";
import Button from "../../../components/Button";
import StatusBadge from "../../../components/StatusBadge";
import { apiGet, apiPost } from "../../../lib/api";

type Batch = {
  project_id: string;
  batch_id: string;
  name: string;
  status: string;
  document_count: number;
  completed_count?: number;
  checked_out_by: string | null;
  checked_out_at?: string;
  completed_at?: string;
  level: string;
  workflow_type: string;
  doc_ids: string[];
};

type StoredUser = {
  username: string;
  display_name: string;
  role: string;
};

function BatchesPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const clientId = searchParams.get("client") || "";
  const projectId = searchParams.get("project") || "";

  const [user, setUser] = useState<StoredUser | null>(null);
  const [batches, setBatches] = useState<Batch[]>([]);
  const [mode, setMode] =
    useState<"review" | "qc" | "alt" | "statqc">("review");

  const [checkoutWarning, setCheckoutWarning] = useState<{
    title: string;
    message: string;
  } | null>(null);

  const [message, setMessage] = useState("");
  const [expandedBatchGroups, setExpandedBatchGroups] =
    useState<Record<string, boolean>>({});

  const [expandedStatusGroups, setExpandedStatusGroups] =
    useState<Record<string, boolean>>({});

  useEffect(() => {
    const storedUser = localStorage.getItem("insyt_user");

    if (storedUser) {
      setUser(JSON.parse(storedUser));
    }
  }, []);

  function loadBatches() {
    if (!clientId || !projectId) {
      setBatches([]);
      return;
    }

    apiGet(
      `/api/summaries/projects/${encodeURIComponent(
        projectId
      )}/batches?client=${encodeURIComponent(clientId)}`
    )
      .then((response) => {
        const normalized = (response.batches || []).map((batch: any) => {
          const batchName =
            batch.batch_name ||
            batch.batch_id ||
            batch.name;

          return {
            project_id: batch.project_id,
            batch_id: batchName,
            name: batchName,
            status: batch.status || "Available",

            document_count:
              batch.document_count ||
              batch.doc_ids?.length ||
              Number(batch.documents || 0),

            completed_count:
              batch.completed_count || 0,

            checked_out_by:
              batch.checked_out_by || null,

            checked_out_at:
              batch.checked_out_at || "",

            completed_at:
              batch.completed_at || "",

            level: batch.level || "1L",

            workflow_type:
              batch.workflow_type || "standard",

            doc_ids: batch.doc_ids || [],
          };
        });

        setBatches(normalized);
      })
      .catch((error) => {
        console.error(error);
        setMessage("Failed to load Summaries batches.");
      });
  }

  useEffect(() => {
    loadBatches();
  }, [clientId, projectId]);

  useEffect(() => {
    if (!canViewAdvancedBatchModes() && mode !== "review") {
      setMode("review");
    }
  }, [user, mode]);

  const selectedLevel =
    mode === "review"
      ? "1L"
      : mode === "qc"
        ? "QC"
        : mode === "alt"
          ? "ALT Workflow"
          : "Statistical QC";

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

  const modeBatches = [...batches]
    .filter((batch) => batch.level === selectedLevel)
    .sort((a, b) => {
      const statusDiff =
        getStatusRank(a.status) - getStatusRank(b.status);

      if (statusDiff !== 0) return statusDiff;

      return getBatchNumber(a.name) - getBatchNumber(b.name);
    });

  const availableCount = modeBatches.filter(
    (batch) =>
      String(batch.status || "").toLowerCase() === "available"
  ).length;

  const checkedOutCount = modeBatches.filter((batch) => {
    const status = String(batch.status || "")
      .toLowerCase()
      .replaceAll("_", " ");

    return status === "checked out";
  }).length;

  const completedCount = modeBatches.filter(
    (batch) =>
      String(batch.status || "").toLowerCase() === "completed"
  ).length;

  const totalBatchCount = modeBatches.length;

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
    if (clean === "checked out" || clean === "in progress") {
      return "inProgress";
    }
    if (clean === "completed") return "completed";

    return "other";
  }

  function getStatusSectionKey(
    groupKey: string,
    sectionKey: string
  ) {
    return `${groupKey}::${sectionKey}`;
  }

  const batchGroups = Object.entries(
    modeBatches.reduce<Record<string, Batch[]>>((groups, batch) => {
      const groupKey = getBatchGroupKey(batch.name || batch.batch_id);

      if (!groups[groupKey]) {
        groups[groupKey] = [];
      }

      groups[groupKey].push(batch);
      return groups;
    }, {})
  )
    .map(([groupKey, groupItems]) => {
      const sortedItems = [...groupItems].sort(
        (a, b) => getBatchNumber(a.name) - getBatchNumber(b.name)
      );

      return {
        groupKey,
        batches: sortedItems,
        total: sortedItems.length,
        available: sortedItems.filter(
          (batch) => getBatchStatusBucket(batch.status) === "available"
        ).length,
        inProgress: sortedItems.filter(
          (batch) => getBatchStatusBucket(batch.status) === "inProgress"
        ).length,
        completed: sortedItems.filter(
          (batch) => getBatchStatusBucket(batch.status) === "completed"
        ).length,
      };
    })
    .sort((a, b) =>
      a.groupKey.localeCompare(b.groupKey, undefined, {
        numeric: true,
      })
    );

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
        console.error("Checkout failed:", error);

        const rawMessage = String(error?.message || "");

        let warningMessage =
          "You already have a batch checked out. Complete or release your current batch before checking out another batch.";

        try {
          const jsonStart = rawMessage.indexOf("{");

          if (jsonStart >= 0) {
            const parsed = JSON.parse(rawMessage.slice(jsonStart));
            const detail = parsed?.detail;

            if (detail?.message) {
              warningMessage = detail.message;
            }
          }
        } catch {
          // Use default warning message.
        }

        setCheckoutWarning({
          title: "Batch Already Checked Out",
          message: warningMessage,
        });

        setMessage("");
      });
  }

  function completeBatch(batchId: string) {
    if (!clientId || !projectId || !user) return;

    apiPost(
      `/api/summaries/projects/${encodeURIComponent(
        projectId
      )}/batches/complete?client=${encodeURIComponent(clientId)}`,
      {
        batch_name: batchId,
        username: user.username,
      }
    )
      .then((response) => {
        setMessage(response.message || "Batch marked completed.");
        loadBatches();
      })
      .catch((error) => {
        console.error(error);
        setMessage("Failed to complete batch.");
      });
  }

  function markBatchAvailable(batchId: string) {
    if (!clientId || !projectId || !user) return;

    apiPost(
      `/api/summaries/projects/${encodeURIComponent(
        projectId
      )}/batches/release?client=${encodeURIComponent(clientId)}`,
      {
        batch_name: batchId,
        username: user.username,
        role: user.role,
      }
    )
      .then((response) => {
        setMessage(response.message || "Batch marked available.");
        loadBatches();
      })
      .catch((error) => {
        console.error(error);
        setMessage("Failed to mark batch available.");
      });
  }

  function canOpenAnyBatch() {
    const role = user?.role || "";

    return [
      "QC",
      "TL",
      "RM",
      "Admin",
      "INSYT Admin",
      "CDS Admin",
    ].includes(role);
  }

  function canViewAdvancedBatchModes() {
    const role = user?.role || "";

    return [
      "QC",
      "TL",
      "RM",
      "Admin",
      "INSYT Admin",
      "CDS Admin",
    ].includes(role);
  }

  function canReassignBatch() {
    const role = user?.role || "";

    return [
      "RM",
      "Admin",
      "INSYT Admin",
      "CDS Admin",
    ].includes(role);
  }

  function canOpenBatch(batch: Batch) {
    if (batch.status !== "Checked Out") return false;

    return (
      batch.checked_out_by === user?.username ||
      canOpenAnyBatch()
    );
  }

  function openBatchReview(batchId: string) {
    const params = new URLSearchParams();

    params.set("client", clientId);
    params.set("project", projectId);
    params.set("batch", batchId);

    router.push(`/summaries/review/doc?${params.toString()}`);
  }

  if (!clientId || !projectId) {
    return (
      <AppShell>
        <PageContainer>
          <PageHeader
            title="Batches"
            subtitle="Select a Summaries project first."
          />
        </PageContainer>
      </AppShell>
    );
  }

  return (
    <AppShell>
      <PageContainer>
        <PageHeader
          title="Batches"
          subtitle={`Batch checkout and status for ${
            clientId
              ? `${clientId.replaceAll("_", " ")} / `
              : ""
          }${projectId.replaceAll("_", " ")}.`}
        />

        {message && (
          <p className="text-sm text-sky-400 mb-6">
            {message}
          </p>
        )}

        <div
          className={
            canViewAdvancedBatchModes()
              ? "grid grid-cols-4 gap-6 mb-6"
              : "grid grid-cols-1 gap-6 mb-6 max-w-sm"
          }
        >
          <button
            type="button"
            onClick={() => {
              setMode("review");
            }}
            className={
              mode === "review"
                ? "bg-lime-50 text-slate-700 rounded-2xl p-5 text-left"
                : "bg-slate-900 border border-slate-800 text-slate-300 rounded-2xl p-5 text-left hover:bg-slate-800"
            }
          >
            <h2 className="text-xl font-semibold">Review Batches</h2>
            <p className="text-sm mt-2 opacity-80">
              First-pass summary review batch checkout and status.
            </p>
          </button>

          {canViewAdvancedBatchModes() && (
            <>
              <button
                type="button"
                onClick={() => {
                  setMode("qc");
                }}
                className={
                  mode === "qc"
                    ? "bg-lime-50 text-slate-700 rounded-2xl p-5 text-left"
                    : "bg-slate-900 border border-slate-800 text-slate-300 rounded-2xl p-5 text-left hover:bg-slate-800"
                }
              >
                <h2 className="text-xl font-semibold">QC Batches</h2>
                <p className="text-sm mt-2 opacity-80">
                  Quality-control summary batch checkout and status.
                </p>
              </button>

              <button
                type="button"
                onClick={() => {
                  setMode("alt");
                }}
                className={
                  mode === "alt"
                    ? "bg-lime-50 text-slate-700 rounded-2xl p-5 text-left"
                    : "bg-slate-900 border border-slate-800 text-slate-300 rounded-2xl p-5 text-left hover:bg-slate-800"
                }
              >
                <h2 className="text-xl font-semibold">Alt Batches</h2>
                <p className="text-sm mt-2 opacity-80">
                  Supplemental summary workflow batches.
                </p>
              </button>

              <button
                type="button"
                onClick={() => {
                  setMode("statqc");
                }}
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
                  Randomized quality-control sampling by confidence level.
                </p>
              </button>
            </>
          )}
        </div>

        <ContentCard title={`${selectedLevel} Batches`}>
          <div className="mb-5 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-800 bg-slate-950 p-4">
            <div className="text-sm font-semibold text-white">
              Batch Status
            </div>

            <div className="flex flex-wrap gap-3 text-sm">
              <div className="rounded-lg border border-slate-800 bg-slate-900 px-3 py-2 text-slate-300">
                Total:{" "}
                <span className="font-semibold text-white">
                  {totalBatchCount}
                </span>
              </div>

              <div className="rounded-lg border border-slate-800 bg-slate-900 px-3 py-2 text-slate-300">
                Available:{" "}
                <span className="font-semibold text-lime-300">
                  {availableCount}
                </span>
              </div>

              <div className="rounded-lg border border-slate-800 bg-slate-900 px-3 py-2 text-slate-300">
                In Progress:{" "}
                <span className="font-semibold text-sky-300">
                  {checkedOutCount}
                </span>
              </div>

              <div className="rounded-lg border border-slate-800 bg-slate-900 px-3 py-2 text-slate-300">
                Completed:{" "}
                <span className="font-semibold text-slate-100">
                  {completedCount}
                </span>
              </div>
            </div>
          </div>

          {modeBatches.length === 0 ? (
            <p className="text-slate-400">
              No batches found for this category.
            </p>
          ) : (
            <div className="space-y-3">
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
                      <div className="border-t border-slate-800 bg-slate-950">
                        {[
                          {
                            key: "available",
                            label: "Available Batches",
                            count: group.available,
                            batches: group.batches.filter(
                              (batch) =>
                                getBatchStatusBucket(batch.status) === "available"
                            ),
                            defaultOpen: true,
                          },
                          {
                            key: "inProgress",
                            label: "In Progress",
                            count: group.inProgress,
                            batches: group.batches.filter(
                              (batch) =>
                                getBatchStatusBucket(batch.status) === "inProgress"
                            ),
                            defaultOpen: false,
                          },
                          {
                            key: "completed",
                            label: "Completed",
                            count: group.completed,
                            batches: group.batches.filter(
                              (batch) =>
                                getBatchStatusBucket(batch.status) === "completed"
                            ),
                            defaultOpen: false,
                          },
                        ].map((section) => {
                          const sectionStateKey = getStatusSectionKey(
                            group.groupKey,
                            section.key
                          );

                          const isSectionExpanded =
                            expandedStatusGroups[sectionStateKey] ??
                            section.defaultOpen;

                          return (
                            <div
                              key={section.key}
                              className="border-t border-slate-800"
                            >
                              <button
                                type="button"
                                onClick={() =>
                                  setExpandedStatusGroups((current) => ({
                                    ...current,
                                    [sectionStateKey]: !isSectionExpanded,
                                  }))
                                }
                                className="w-full px-4 py-3 bg-slate-900/80 hover:bg-slate-800 text-left"
                              >
                                <div className="flex items-center gap-4 text-sm">
                                  <span className="text-white font-semibold">
                                    {isSectionExpanded ? "▾" : "▸"}{" "}
                                    {section.label}
                                  </span>

                                  <span className="text-slate-400">
                                    {section.count} batch
                                    {section.count === 1 ? "" : "es"}
                                  </span>
                                </div>
                              </button>

                              {isSectionExpanded && (
                                <div className="p-4">
                                  {section.batches.length === 0 ? (
                                    <div className="rounded-xl border border-slate-800 bg-slate-900 px-4 py-4 text-sm text-slate-500">
                                      No batches in this section.
                                    </div>
                                  ) : (
                                    <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
                                      {section.batches.map((batch) => {
                                        const totalDocs =
                                          batch.document_count || 0;
                                        const reviewed =
                                          batch.completed_count || 0;
                                        const pending = Math.max(
                                          totalDocs - reviewed,
                                          0
                                        );

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

                                              <p>
                                                Date Checked Out:{" "}
                                                <span className="text-slate-200">
                                                  {batch.checked_out_at || "—"}
                                                </span>
                                              </p>
                                            </div>

                                            <div>
                                              {batch.status === "Available" && (
                                                <Button
                                                  fullWidth
                                                  onClick={() =>
                                                    checkoutBatch(batch.batch_id)
                                                  }
                                                >
                                                  Check Out
                                                </Button>
                                              )}

                                              {canOpenBatch(batch) && (
                                                <div className="space-y-2">
                                                  <Button
                                                    fullWidth
                                                    variant="secondary"
                                                    onClick={() =>
                                                      openBatchReview(batch.batch_id)
                                                    }
                                                  >
                                                    Open Review
                                                  </Button>

                                                  {batch.checked_out_by ===
                                                    user?.username && (
                                                    <div className="grid grid-cols-2 gap-2">
                                                      <Button
                                                        fullWidth
                                                        onClick={() =>
                                                          completeBatch(batch.batch_id)
                                                        }
                                                      >
                                                        Completed
                                                      </Button>

                                                      <Button
                                                        fullWidth
                                                        variant="secondary"
                                                        onClick={() =>
                                                          markBatchAvailable(
                                                            batch.batch_id
                                                          )
                                                        }
                                                      >
                                                        Mark Available
                                                      </Button>
                                                    </div>
                                                  )}
                                                </div>
                                              )}

                                              {batch.status === "Checked Out" &&
                                                canReassignBatch() && (
                                                  <div className="mt-3 rounded-xl border border-slate-800 bg-slate-900 p-3">
                                                    <p className="text-xs text-slate-400 mb-2">
                                                      Leadership Reassignment
                                                    </p>

                                                    <Button
                                                      fullWidth
                                                      variant="secondary"
                                                      onClick={() =>
                                                        markBatchAvailable(
                                                          batch.batch_id
                                                        )
                                                      }
                                                    >
                                                      Reassign to Available
                                                    </Button>
                                                  </div>
                                                )}
                                            </div>
                                          </div>
                                        );
                                      })}
                                    </div>
                                  )}
                                </div>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </ContentCard>

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