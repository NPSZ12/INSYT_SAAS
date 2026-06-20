"use client";

import { useEffect, useState } from "react";

import Button from "../Button";
import ContentCard from "../ContentCard";
import StatusBadge from "../StatusBadge";
import { apiGet, apiPost } from "../../lib/api";

type SummarySet = {
  batch_summary_set_id: string;
  source_doc_id: string;
  source_pdf_name: string;
  summary_start_index: number;
  summary_end_index: number;
  summary_count: number;
  status: string;
  checked_out_by?: string | null;
  checked_out_at?: string | null;
  completed_by?: string | null;
  completed_at?: string | null;
  blob_path?: string;
};

type SummarySetItem = {
  summary_id: string;
  section_id: string;
  section_index?: number;
  title: string;
  citation: string;
  original_summary: string;
  qc_summary: string;
  page?: number | null;
  page_start?: number | null;
  page_end?: number | null;
  pdf_page?: number | null;
  saved?: boolean;
  saved_row?: any;
};

type SummarySetDetail = {
  batch_summary_set_id: string;
  source_doc_id: string;
  source_pdf_name: string;
  source_pdf_path: string;
  text_path: string;
  summary_start_index: number;
  summary_end_index: number;
  summary_count: number;
  status: string;
  items: SummarySetItem[];
};

type StoredUser = {
  username: string;
  display_name: string;
  role: string;
};

type Props = {
  clientId: string;
  projectId: string;
  user: StoredUser | null;
};

const SUMMARY_SET_SIZES = [1, 5, 10, 25, 50];

export default function SummarySetsPanel({
  clientId,
  projectId,
  user,
}: Props) {
  const [docId, setDocId] = useState("");
  const [summariesPerSet, setSummariesPerSet] = useState(10);
  const [overwrite, setOverwrite] = useState(true);

  const [summarySets, setSummarySets] = useState<SummarySet[]>([]);
  const [expandedDocIds, setExpandedDocIds] = useState<Record<string, boolean>>({});
  const [activeSetId, setActiveSetId] = useState("");
  const [activeSet, setActiveSet] = useState<SummarySetDetail | null>(null);
  const [activeSummaryId, setActiveSummaryId] = useState("");

  const [qcDraft, setQcDraft] = useState("");
  const [message, setMessage] = useState("");
  const [isBusy, setIsBusy] = useState(false);

  const activeItem =
    activeSet?.items?.find((item) => item.summary_id === activeSummaryId) ||
    activeSet?.items?.[0] ||
    null;

  useEffect(() => {
    loadSummarySets();
  }, [clientId, projectId]);

  useEffect(() => {
    if (!activeItem) {
      setQcDraft("");
      return;
    }

    setQcDraft(
      activeItem.saved_row?.qc_summary ||
        activeItem.qc_summary ||
        activeItem.original_summary ||
        ""
    );
  }, [activeItem?.summary_id, activeItem?.saved_row?.updated_at]);

  function loadSummarySets() {
    if (!clientId || !projectId) {
      setSummarySets([]);
      return;
    }

    apiGet(
      `/api/summaries/summary-sets/?client=${encodeURIComponent(
        clientId
      )}&project=${encodeURIComponent(projectId)}`
    )
      .then((response) => {
        setSummarySets(response.summary_sets || []);
      })
      .catch((error) => {
        console.error(error);
        setMessage("Failed to load Summary Sets.");
      });
  }

  function createSummarySets() {
    if (!clientId || !projectId || !docId.trim()) {
      setMessage("Enter the promoted PDF Doc ID before creating Summary Sets.");
      return;
    }

    setIsBusy(true);
    setMessage("");

    apiPost("/api/summaries/summary-sets/create", {
      client: clientId,
      project: projectId,
      doc_id: docId.trim(),
      summaries_per_set: summariesPerSet,
      overwrite,
    })
      .then((response) => {
        setMessage(
          `Created ${response.summary_set_count || 0} Summary Set(s) from ${
            response.summary_count || 0
          } summaries.`
        );
        loadSummarySets();
      })
      .catch((error) => {
        console.error(error);
        setMessage(
          "Failed to create Summary Sets. Confirm the PDF was promoted and source/summary_extracts/{doc_id}.json exists."
        );
      })
      .finally(() => {
        setIsBusy(false);
      });
  }

  function openSummarySet(batchSummarySetId: string) {
    setIsBusy(true);
    setMessage("");

    apiGet(
      `/api/summaries/summary-sets/${encodeURIComponent(
        batchSummarySetId
      )}?client=${encodeURIComponent(clientId)}&project=${encodeURIComponent(
        projectId
      )}`
    )
      .then((response) => {
        const detail = response.summary_set;
        setActiveSet(detail);
        setActiveSetId(batchSummarySetId);

        const firstUnsaved =
          detail?.items?.find((item: SummarySetItem) => !item.saved) ||
          detail?.items?.[0];

        setActiveSummaryId(firstUnsaved?.summary_id || "");
      })
      .catch((error) => {
        console.error(error);
        setMessage("Failed to open Summary Set.");
      })
      .finally(() => {
        setIsBusy(false);
      });
  }

  function saveQcSummary() {
    if (!activeSet || !activeItem || !user) {
      setMessage("Open a Summary Set and select a summary before saving.");
      return;
    }

    setIsBusy(true);
    setMessage("");

    apiPost("/api/summaries/summary-sets/save", {
      client: clientId,
      project: projectId,
      batch_summary_set_id: activeSet.batch_summary_set_id,
      summary_id: activeItem.summary_id,
      section_id: activeItem.section_id,
      title: activeItem.title,
      citation: activeItem.citation,
      original_summary: activeItem.original_summary,
      qc_summary: qcDraft,
      saved_by: user.username,
    })
      .then(() => {
        setMessage("QC Summary saved.");
        openSummarySet(activeSet.batch_summary_set_id);
        loadSummarySets();
      })
      .catch((error) => {
        console.error(error);
        setMessage("Failed to save QC Summary.");
      })
      .finally(() => {
        setIsBusy(false);
      });
  }

  function unlinkSummary(summaryId: string) {
    if (!activeSet || !user) return;

    setIsBusy(true);

    apiPost("/api/summaries/summary-sets/unlink", {
      client: clientId,
      project: projectId,
      batch_summary_set_id: activeSet.batch_summary_set_id,
      summary_id: summaryId,
      acted_by: user.username,
    })
      .then(() => {
        setMessage("Saved QC Summary unlinked.");
        openSummarySet(activeSet.batch_summary_set_id);
      })
      .catch((error) => {
        console.error(error);
        setMessage("Failed to unlink saved QC Summary.");
      })
      .finally(() => {
        setIsBusy(false);
      });
  }

  function deleteSummary(summaryId: string) {
    if (!activeSet || !user) return;

    const confirmed = window.confirm(
      "Delete this saved QC Summary from this Summary Set?"
    );

    if (!confirmed) return;

    setIsBusy(true);

    apiPost("/api/summaries/summary-sets/delete", {
      client: clientId,
      project: projectId,
      batch_summary_set_id: activeSet.batch_summary_set_id,
      summary_id: summaryId,
      acted_by: user.username,
    })
      .then(() => {
        setMessage("Saved QC Summary deleted.");
        openSummarySet(activeSet.batch_summary_set_id);
      })
      .catch((error) => {
        console.error(error);
        setMessage("Failed to delete saved QC Summary.");
      })
      .finally(() => {
        setIsBusy(false);
      });
  }

  function completeSummarySet() {
    if (!activeSet || !user) return;

    setIsBusy(true);

    apiPost("/api/summaries/summary-sets/complete", {
      client: clientId,
      project: projectId,
      batch_summary_set_id: activeSet.batch_summary_set_id,
      completed_by: user.username,
      allow_incomplete: false,
    })
      .then(() => {
        setMessage("Summary Set completed.");
        openSummarySet(activeSet.batch_summary_set_id);
        loadSummarySets();
      })
      .catch((error) => {
        console.error(error);

        const forceComplete = window.confirm(
          "This Summary Set may have unsaved summaries. Complete anyway?"
        );

        if (!forceComplete || !activeSet || !user) {
          setMessage("Summary Set was not completed.");
          return;
        }

        return apiPost("/api/summaries/summary-sets/complete", {
          client: clientId,
          project: projectId,
          batch_summary_set_id: activeSet.batch_summary_set_id,
          completed_by: user.username,
          allow_incomplete: true,
        }).then(() => {
          setMessage("Summary Set completed with incomplete items.");
          openSummarySet(activeSet.batch_summary_set_id);
          loadSummarySets();
        });
      })
      .finally(() => {
        setIsBusy(false);
      });
  }

  const savedCount =
    activeSet?.items?.filter((item) => item.saved).length || 0;

  async function createSummaryExtracts() {
    const trimmedDocId = docId.trim();

    if (!clientId || !projectId || !trimmedDocId) {
      setMessage("Enter the promoted PDF Doc ID before creating Summary Extracts.");
      return;
    }

    setIsBusy(true);
    setMessage("");

    try {
      const response = await apiPost("/api/summaries/summary-sets/extracts/create", {
        client: clientId,
        project: projectId,
        doc_id: trimmedDocId,
        overwrite: false,
        max_chars_per_section: 2500,
      });

      setMessage(
        `Summary Extract ${response.status}. Sections: ${
          response.section_count || 0
        }.`
      );

      loadSummarySets();
    } catch (error) {
      console.error(error);
      setMessage("Failed to create Summary Extracts.");
    } finally {
      setIsBusy(false);
    }
  }

  const groupedSummarySets = summarySets.reduce<Record<string, SummarySet[]>>(
    (groups, set) => {
      const key = set.source_doc_id || "Unknown Doc ID";

      if (!groups[key]) {
        groups[key] = [];
      }

      groups[key].push(set);
      return groups;
    },
    {}
  );

  const summarySetGroups = Object.entries(groupedSummarySets).map(
    ([sourceDocId, sets]) => {
      const totalSummaries = sets.reduce(
        (total, set) => total + Number(set.summary_count || 0),
        0
      );

      const completedCount = sets.filter(
        (set) => String(set.status || "").toLowerCase() === "completed"
      ).length;

      const checkedOutCount = sets.filter((set) => set.checked_out_by).length;

      const availableCount = sets.filter(
        (set) =>
          !set.checked_out_by &&
          String(set.status || "available").toLowerCase() !== "completed"
      ).length;

      const firstSet = sets[0];

      return {
        sourceDocId,
        sourcePdfName: firstSet?.source_pdf_name || "",
        sets,
        setCount: sets.length,
        totalSummaries,
        completedCount,
        checkedOutCount,
        availableCount,
      };
    }
  );

  return (
    <ContentCard title="Summary Sets">
      <div className="mb-5 rounded-xl border border-slate-800 bg-slate-950 p-4">
        <div className="mb-4">
          <h3 className="text-sm font-semibold text-white">
            Create Summary Sets
          </h3>
          <p className="mt-1 text-xs text-slate-400">
            Create batchable Summary Sets from a promoted PDF summary extract.
            The full PDF remains available, but each set only shows its assigned
            summaries.
          </p>
        </div>

        <div className="grid grid-cols-1 gap-3 md:grid-cols-[1fr_180px_260px]">
          <div>
            <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-500">
              Promoted PDF Doc ID
            </label>
            <input
              value={docId}
              onChange={(event) => setDocId(event.target.value)}
              placeholder="INSYT000000006"
              className="w-full rounded-xl border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-white outline-none focus:border-lime-400"
            />
          </div>

          <div>
            <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-500">
              Summaries per set
            </label>
            <select
              value={summariesPerSet}
              onChange={(event) =>
                setSummariesPerSet(Number(event.target.value))
              }
              className="w-full rounded-xl border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-white outline-none focus:border-lime-400"
            >
              {SUMMARY_SET_SIZES.map((size) => (
                <option key={size} value={size}>
                  {size}
                </option>
              ))}
            </select>
          </div>

          <div className="flex items-end gap-2">
            <Button
              fullWidth
              onClick={createSummaryExtracts}
              disabled={isBusy || !docId.trim()}
              className="rounded-full bg-sky-500 px-5 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-sky-400 disabled:cursor-not-allowed disabled:opacity-50"
            >
              Create Summary Extracts
            </Button>

            <Button
              fullWidth
              onClick={createSummarySets}
              disabled={isBusy}
              className="rounded-full bg-lime-500 px-5 py-2.5 text-sm font-semibold text-slate-950 shadow-sm hover:bg-lime-400 disabled:cursor-not-allowed disabled:opacity-50"
            >
              Create Summary Sets
            </Button>
          </div>
        </div>

        <label className="mt-3 flex items-center gap-2 text-xs text-slate-400">
          <input
            type="checkbox"
            checked={overwrite}
            onChange={(event) => setOverwrite(event.target.checked)}
          />
          Overwrite existing Summary Sets with the same IDs
        </label>
      </div>

      {message && (
        <p className="mb-4 rounded-xl border border-slate-800 bg-slate-950 px-4 py-3 text-sm text-sky-300">
          {message}
        </p>
      )}

      <div className="mb-6">
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-sm font-semibold text-white">
            Available Summary Sets
          </h3>
          <Button variant="secondary" onClick={loadSummarySets}>
            Refresh
          </Button>
        </div>

        {summarySetGroups.length === 0 ? (
          <p className="rounded-xl border border-slate-800 bg-slate-950 p-4 text-sm text-slate-400">
            No Summary Sets found.
          </p>
        ) : (
          <div className="space-y-3">
            {summarySetGroups.map((group) => {
              const isExpanded = !!expandedDocIds[group.sourceDocId];

              return (
                <div
                  key={group.sourceDocId}
                  className="overflow-hidden rounded-2xl border border-slate-800 bg-slate-950"
                >
                  <button
                    type="button"
                    onClick={() =>
                      setExpandedDocIds((current) => ({
                        ...current,
                        [group.sourceDocId]: !current[group.sourceDocId],
                      }))
                    }
                    className="flex w-full items-center justify-between gap-4 px-4 py-4 text-left hover:bg-slate-900"
                  >
                    <div>
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-sm font-semibold text-white">
                          {group.sourceDocId}
                        </span>

                        <span className="rounded-full border border-slate-700 px-2.5 py-1 text-xs text-slate-300">
                          {group.setCount} set{group.setCount === 1 ? "" : "s"}
                        </span>

                        <span className="rounded-full border border-slate-700 px-2.5 py-1 text-xs text-slate-300">
                          {group.totalSummaries} summaries
                        </span>

                        <span className="rounded-full border border-emerald-700 bg-emerald-950 px-2.5 py-1 text-xs text-emerald-300">
                          {group.availableCount} available
                        </span>

                        <span className="rounded-full border border-sky-700 bg-sky-950 px-2.5 py-1 text-xs text-sky-300">
                          {group.checkedOutCount} checked out
                        </span>

                        <span className="rounded-full border border-lime-700 bg-lime-950 px-2.5 py-1 text-xs text-lime-300">
                          {group.completedCount} completed
                        </span>
                      </div>

                      <p className="mt-1 text-xs text-slate-400">
                        Source: {group.sourcePdfName || "—"}
                      </p>
                    </div>

                    <span className="rounded-full border border-slate-700 px-3 py-1 text-xs font-semibold text-slate-300">
                      {isExpanded ? "Collapse" : "Expand"}
                    </span>
                  </button>

                  {isExpanded && (
                    <div className="border-t border-slate-800 p-3">
                      <div className="overflow-x-auto">
                        <table className="w-full min-w-[760px] text-left text-sm">
                          <thead>
                            <tr className="border-b border-slate-800 text-xs uppercase tracking-wide text-slate-500">
                              <th className="px-3 py-2">Summary Set</th>
                              <th className="px-3 py-2">Range</th>
                              <th className="px-3 py-2">Count</th>
                              <th className="px-3 py-2">Status</th>
                              <th className="px-3 py-2">Checked Out By</th>
                              <th className="px-3 py-2">Completed By</th>
                              <th className="px-3 py-2 text-right">Action</th>
                            </tr>
                          </thead>

                          <tbody>
                            {group.sets.map((set) => (
                              <tr
                                key={set.batch_summary_set_id}
                                className={
                                  activeSetId === set.batch_summary_set_id
                                    ? "border-b border-slate-800 bg-lime-950/30"
                                    : "border-b border-slate-800"
                                }
                              >
                                <td className="px-3 py-3 font-semibold text-white">
                                  {set.batch_summary_set_id}
                                </td>

                                <td className="px-3 py-3 text-slate-300">
                                  {set.summary_start_index}–{set.summary_end_index}
                                </td>

                                <td className="px-3 py-3 text-slate-300">
                                  {set.summary_count}
                                </td>

                                <td className="px-3 py-3">
                                  <StatusBadge>{set.status || "available"}</StatusBadge>
                                </td>

                                <td className="px-3 py-3 text-slate-300">
                                  {set.checked_out_by || "—"}
                                </td>

                                <td className="px-3 py-3 text-slate-300">
                                  {set.completed_by || "—"}
                                </td>

                                <td className="px-3 py-3 text-right">
                                  <Button
                                    variant="secondary"
                                    onClick={() =>
                                      openSummarySet(set.batch_summary_set_id)
                                    }
                                    disabled={isBusy}
                                  >
                                    Open
                                  </Button>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>

      {activeSet && (
        <div className="rounded-2xl border border-slate-800 bg-slate-950 p-4">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <div>
              <h3 className="text-lg font-semibold text-white">
                {activeSet.batch_summary_set_id}
              </h3>
              <p className="text-sm text-slate-400">
                {savedCount} of {activeSet.items?.length || 0} summaries saved
              </p>
            </div>

            <Button onClick={completeSummarySet} disabled={isBusy}>
              Complete Summary Set
            </Button>
          </div>

          <div className="grid grid-cols-1 gap-4 xl:grid-cols-[360px_1fr]">
            <div className="rounded-xl border border-slate-800 bg-slate-900 p-3">
              <h4 className="mb-3 text-sm font-semibold text-white">
                PDF Outline for this Summary Set
              </h4>

              <div className="max-h-[520px] space-y-2 overflow-y-auto pr-1">
                {(activeSet.items || []).map((item) => (
                  <button
                    key={item.summary_id}
                    type="button"
                    onClick={() => setActiveSummaryId(item.summary_id)}
                    className={
                      activeSummaryId === item.summary_id
                        ? "w-full rounded-lg border border-lime-400 bg-lime-50 px-3 py-2 text-left text-sm text-slate-900"
                        : "w-full rounded-lg border border-slate-800 bg-slate-950 px-3 py-2 text-left text-sm text-slate-300 hover:bg-slate-800"
                    }
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-semibold">
                        {item.saved ? "✓ " : ""}
                        {item.title || item.summary_id}
                      </span>
                      <span className="text-xs opacity-70">
                        {item.citation || ""}
                      </span>
                    </div>
                  </button>
                ))}
              </div>
            </div>

            <div className="rounded-xl border border-slate-800 bg-slate-900 p-4">
              {!activeItem ? (
                <p className="text-sm text-slate-400">
                  Select a summary from the Summary Set outline.
                </p>
              ) : (
                <>
                  <div className="mb-4">
                    <h4 className="text-lg font-semibold text-white">
                      {activeItem.title || activeItem.summary_id}
                    </h4>
                    <p className="mt-1 text-sm text-slate-400">
                      Citation: {activeItem.citation || "—"}
                    </p>
                  </div>

                  <div className="mb-4">
                    <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-500">
                      Original Summary
                    </label>
                    <div className="max-h-52 overflow-y-auto whitespace-pre-wrap rounded-xl border border-slate-800 bg-slate-950 p-3 text-sm text-slate-300">
                      {activeItem.original_summary || "—"}
                    </div>
                  </div>

                  <div className="mb-4">
                    <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-500">
                      QC Summary
                    </label>
                    <textarea
                      value={qcDraft}
                      onChange={(event) => setQcDraft(event.target.value)}
                      rows={10}
                      className="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white outline-none focus:border-lime-400"
                    />
                  </div>

                  <div className="mb-5 flex flex-wrap gap-2">
                    <Button onClick={saveQcSummary} disabled={isBusy}>
                      Save QC Summary
                    </Button>

                    {activeItem.saved && (
                      <>
                        <Button
                          variant="secondary"
                          onClick={() => unlinkSummary(activeItem.summary_id)}
                          disabled={isBusy}
                        >
                          Unlink
                        </Button>

                        <Button
                          variant="secondary"
                          onClick={() => deleteSummary(activeItem.summary_id)}
                          disabled={isBusy}
                        >
                          Delete
                        </Button>
                      </>
                    )}
                  </div>

                  {activeItem.saved_row && (
                    <div className="rounded-xl border border-slate-800 bg-slate-950 p-3 text-xs text-slate-400">
                      <p>
                        Saved By:{" "}
                        <span className="text-slate-200">
                          {activeItem.saved_row.saved_by || "—"}
                        </span>
                      </p>
                      <p>
                        Saved At:{" "}
                        <span className="text-slate-200">
                          {activeItem.saved_row.saved_at || "—"}
                        </span>
                      </p>
                      <p>
                        Link ID:{" "}
                        <span className="text-slate-200">
                          {activeItem.saved_row.link_id || "—"}
                        </span>
                      </p>
                    </div>
                  )}
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </ContentCard>
  );
}