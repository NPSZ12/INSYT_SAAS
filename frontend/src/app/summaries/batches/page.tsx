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
  const [expandedBatchName, setExpandedBatchName] = useState("");
  const [message, setMessage] = useState("");

  const projectQuery = `client=${encodeURIComponent(
    clientId
  )}&project=${encodeURIComponent(projectId)}`;

  useEffect(() => {
    const storedUser = localStorage.getItem("insyt_user");

    if (storedUser) {
      setUser(JSON.parse(storedUser));
    }
  }, []);

  function loadBatches() {
    if (!projectId) return;

    apiGet(`/api/summaries/projects/${projectId}/batches`)
      .then((response) => {
        const normalized = (response.batches || []).map((batch: any) => {
          const batchName = batch.batch_name || batch.batch_id || batch.name;

          return {
            project_id: batch.project_id,
            batch_id: batchName,
            name: batchName,
            status: batch.status || "Available",
            document_count:
              batch.document_count ||
              batch.doc_ids?.length ||
              Number(batch.documents || 0),
            checked_out_by: batch.checked_out_by || null,
            checked_out_at: batch.checked_out_at || "",
            completed_at: batch.completed_at || "",
            level: batch.level || "1L",
            workflow_type: batch.workflow_type || "standard",
            doc_ids: batch.doc_ids || [],
          };
        });

        setBatches(normalized);
      })
      .catch((error) => {
        console.error(error);
        setMessage("Failed to load batches.");
      });
  }

  useEffect(() => {
    loadBatches();
  }, [projectId]);

  const selectedLevel =
    mode === "review"
      ? "1L"
      : mode === "qc"
        ? "QC"
        : mode === "alt"
          ? "ALT Workflow"
          : "Statistical QC";

  const modeBatches = batches
    .filter((batch) => batch.level === selectedLevel)
    .sort((a, b) => {
      if (a.status === "Available" && b.status !== "Available") return -1;
      if (a.status !== "Available" && b.status === "Available") return 1;
      return a.name.localeCompare(b.name);
    });

  const batchNames = Array.from(
    new Set(modeBatches.map((batch) => batch.name))
  );

  const expandedBatches = modeBatches.filter(
    (batch) => batch.name === expandedBatchName
  );

  function checkoutBatch(batchId: string) {
    if (!projectId || !user) return;

    apiPost(`/api/summaries/projects/${projectId}/batches/checkout`, {
      batch_name: batchId,
      username: user.username,
    })
      .then((response) => {
        setMessage(response.message || "Batch checked out.");
        loadBatches();
      })
      .catch((error) => {
        console.error(error);
        setMessage("Batch checkout failed.");
      });
  }

  if (!projectId) {
    return (
      <AppShell>
        <PageContainer>
          <PageHeader
            title="Batches"
            subtitle="Select a project first."
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
          subtitle={`Batch checkout and status for ${projectId.replaceAll("_", " ")}.`}
        />

        {message && (
          <p className="text-sm text-sky-400 mb-6">
            {message}
          </p>
        )}

        <div className="grid grid-cols-4 gap-6 mb-6">
          <button
            type="button"
            onClick={() => {
              setMode("review");
              setExpandedBatchName("");
            }}
            className={
              mode === "review"
                ? "bg-lime-50 text-slate-700 rounded-2xl p-5 text-left"
                : "bg-slate-900 border border-slate-800 text-slate-300 rounded-2xl p-5 text-left hover:bg-slate-800"
            }
          >
            <h2 className="text-xl font-semibold">Review Batches</h2>
            <p className="text-sm mt-2 opacity-80">
              First-pass review batch checkout and status.
            </p>
          </button>

          <button
            type="button"
            onClick={() => {
              setMode("qc");
              setExpandedBatchName("");
            }}
            className={
              mode === "qc"
                ? "bg-lime-50 text-slate-700 rounded-2xl p-5 text-left"
                : "bg-slate-900 border border-slate-800 text-slate-300 rounded-2xl p-5 text-left hover:bg-slate-800"
            }
          >
            <h2 className="text-xl font-semibold">QC Batches</h2>
            <p className="text-sm mt-2 opacity-80">
              Quality-control batch checkout and status.
            </p>
          </button>

          <button
            type="button"
            onClick={() => {
              setMode("alt");
              setExpandedBatchName("");
            }}
            className={
              mode === "alt"
                ? "bg-lime-50 text-slate-700 rounded-2xl p-5 text-left"
                : "bg-slate-900 border border-slate-800 text-slate-300 rounded-2xl p-5 text-left hover:bg-slate-800"
            }
          >
            <h2 className="text-xl font-semibold">Alt Batches</h2>
            <p className="text-sm mt-2 opacity-80">
              Supplemental/Search Folder workflow batches.
            </p>
          </button>

          <button
            type="button"
            onClick={() => {
              setMode("statqc");
              setExpandedBatchName("");
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

        </div>

        <ContentCard title={`${selectedLevel} Batch Names`}>
          {batchNames.length === 0 ? (
            <p className="text-slate-400">
              No batches found for this category.
            </p>
          ) : (
            <div className="space-y-4">
              {batchNames.map((batchName) => {
                const related = modeBatches.filter(
                  (batch) => batch.name === batchName
                );

                const availableCount = related.filter(
                  (batch) => batch.status === "Available"
                ).length;

                return (
                  <div
                    key={batchName}
                    className="bg-slate-950 border border-slate-800 rounded-xl"
                  >
                    <button
                      type="button"
                      onClick={() =>
                        setExpandedBatchName(
                          expandedBatchName === batchName ? "" : batchName
                        )
                      }
                      className="w-full flex items-center justify-between p-4 text-left"
                    >
                      <div>
                        <div className="text-lg font-semibold text-white">
                          {batchName}
                        </div>

                        <div className="text-sm text-slate-400">
                          {related.length} batch record(s) · {availableCount} available
                        </div>
                      </div>

                      <StatusBadge>
                        {expandedBatchName === batchName ? "Expanded" : "Collapsed"}
                      </StatusBadge>
                    </button>

                    {expandedBatchName === batchName && (
                      <div className="border-t border-slate-800 overflow-auto">
                        <table className="w-full text-xs table-auto">
                          <thead className="bg-slate-900 text-slate-400 sticky top-0 z-20">
                            <tr>
                              <th className="p-3 text-left">Status</th>
                              <th className="p-3 text-left">Name</th>
                              <th className="p-3 text-left">Docs</th>
                              <th className="p-3 text-left">Checked Out By</th>
                              <th className="p-3 text-left">Date Checked Out</th>
                              <th className="p-3 text-left">Date Completed</th>
                              <th className="p-3 text-left">Action</th>
                            </tr>
                          </thead>

                          <tbody>
                            {related
                              .sort((a, b) => {
                                if (a.status === "Available" && b.status !== "Available") {
                                  return -1;
                                }

                                if (a.status !== "Available" && b.status === "Available") {
                                  return 1;
                                }

                                return a.name.localeCompare(b.name);
                              })
                              .map((batch) => (
                                <tr
                                  key={batch.batch_id}
                                  className="border-t border-slate-800"
                                >
                                  <td className="p-3">
                                    <StatusBadge>{batch.status}</StatusBadge>
                                  </td>

                                  <td className="p-3 text-white">
                                    {batch.batch_id}
                                  </td>

                                  <td className="p-3 text-slate-300">
                                    {batch.document_count}
                                  </td>

                                  <td className="p-3 text-slate-300">
                                    {batch.checked_out_by || "—"}
                                  </td>

                                  <td className="p-3 text-slate-300">
                                    {batch.checked_out_at || "—"}
                                  </td>

                                  <td className="p-3 text-slate-300">
                                    {batch.completed_at || "—"}
                                  </td>

                                  <td className="p-3">
                                    {batch.status === "Available" && (
                                      <Button
                                        onClick={() =>
                                          checkoutBatch(batch.batch_id)
                                        }
                                      >
                                        Check Out
                                      </Button>
                                    )}

                                    {batch.status === "Checked Out" &&
                                      batch.checked_out_by === user?.username && (
                                        <Button
                                          variant="secondary"
                                          onClick={() =>
                                            router.push(
                                              `/summaries/review?client=${encodeURIComponent(
                                                clientId
                                              )}&project=${encodeURIComponent(
                                                projectId
                                              )}&batch=${encodeURIComponent(
                                                batch.batch_id
                                              )}`
                                            )
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
                                  </td>
                                </tr>
                              ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </ContentCard>
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









