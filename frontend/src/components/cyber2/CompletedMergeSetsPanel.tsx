"use client";

import { Fragment, useEffect, useMemo, useState } from "react";
import { apiGet, apiPost } from "../../lib/api";

type CompletedSet = {
  merge_set_id: string;
  status: string;
  header_set_id: string;
  created_at: string;
  raw_record_count: number;
  working_record_count: number;
  merged_group_count: number;
  merge_index: string[];
  parent_merge_set_id?: string | null;
  pass_number?: number;
};

type C2SourceReview = {
  status: string;
  workspace: string;
  client: string;
  project: string;
  header_set_id: string;
  merge_set_id: string;
  working_record_count: number;
  original_source_record_count: number;
  document_count: number;
  documents: Array<{
    doc_id: string;
    original_filename: string;
    original_workbook_name: string;
    sheet_name: string;
  }>;
  origin_authorized: boolean;
  transfer_authorized: boolean;
};

type C2ReviewSelection = {
  base: string;
  client: string;
  project: string;
  mergeSetId: string;
  headerSetId: string;
  review: C2SourceReview;
};

type C2TransferredSet = {
  header_set_id: string;
  merge_set_id: string;
  working_record_count: number;
};

type Props = {
  base: string;
  client: string;
  project: string;
  refreshKey: number;
  onDedupeFurther: (
    mergeSetId: string,
    headerSetId: string
  ) => void;
};

type HeaderGroup = {
  headerSetId: string;
  sets: CompletedSet[];
  terminal: CompletedSet | null;
  ambiguous: boolean;
};

function groupCompletedSets(sets: CompletedSet[]): HeaderGroup[] {
  const buckets = new Map<string, CompletedSet[]>();

  for (const set of sets) {
    const bucket = buckets.get(set.header_set_id) ?? [];
    bucket.push(set);
    buckets.set(set.header_set_id, bucket);
  }

  return [...buckets.entries()]
    .map(([headerSetId, entries]) => {
      const ordered = [...entries].sort((a, b) => {
        const passDifference =
          (a.pass_number ?? 1) - (b.pass_number ?? 1);

        if (passDifference !== 0) return passDifference;

        const dateDifference =
          a.created_at.localeCompare(b.created_at);

        if (dateDifference !== 0) return dateDifference;

        return a.merge_set_id.localeCompare(b.merge_set_id);
      });

      const completed = ordered.filter(
        (set) => set.status === "completed"
      );

      const parentIds = new Set(
        completed
          .map((set) => set.parent_merge_set_id)
          .filter((id): id is string => Boolean(id))
      );

      const terminals = completed.filter(
        (set) => !parentIds.has(set.merge_set_id)
      );

      const knownIds = new Set(
        completed.map((set) => set.merge_set_id)
      );

      const hasMissingParent = completed.some(
        (set) =>
          Boolean(set.parent_merge_set_id) &&
          !knownIds.has(set.parent_merge_set_id!)
      );

      // Only one unambiguous, complete lineage may auto-continue.
      const unambiguous =
        terminals.length === 1 && !hasMissingParent;

      return {
        headerSetId,
        sets: ordered,
        terminal: unambiguous ? terminals[0] : null,
        ambiguous: !unambiguous,
      };
    })
    .sort((a, b) =>
      a.headerSetId.localeCompare(b.headerSetId)
    );
}

export default function CompletedMergeSetsPanel({
  base,
  client,
  project,
  refreshKey,
  onDedupeFurther,
}: Props) {
  const [sets, setSets] = useState<CompletedSet[]>([]);
  const [transferredSets, setTransferredSets] =
    useState<C2TransferredSet[]>([]);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [selectedHeader, setSelectedHeader] = useState("");
  const [expandedHeaders, setExpandedHeaders] =
    useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [c2Review, setC2Review] =
    useState<C2ReviewSelection | null>(null);
  const [c2Busy, setC2Busy] = useState(false);
  const [c2Attested, setC2Attested] = useState(false);
  const [c2Error, setC2Error] = useState("");
  const [c2Success, setC2Success] = useState("");

  useEffect(() => {
    let active = true;

    async function load() {
      setSets([]);
      setTransferredSets([]);
      setSelectedIds([]);
      setSelectedHeader("");
      setError("");
      setC2Review(null);
      setC2Attested(false);
      setC2Error("");
      setC2Success("");

      if (!client || !project) return;

      setLoading(true);

      try {
        const query = new URLSearchParams({
          client,
          project,
        });

        const response = await apiGet(
          `${base}/merge-dedupe/completed?${query.toString()}`
        );

        if (
          response?.status !== "ok" ||
          !Array.isArray(response?.merge_sets)
        ) {
          throw new Error(
            "Invalid Completed Merge Sets response."
          );
        }

        // Read durable transferred snapshots, not browser-only state.
        const sent = await apiGet(
          `${base}/c2/project-records?${query.toString()}`
        );

        if (
          sent?.status !== "ok" ||
          sent.client !== client ||
          sent.project !== project ||
          !Array.isArray(sent.transferred_sets)
        ) {
          throw new Error("Invalid C² transfer inventory.");
        }

        const seen = new Set<string>();
        for (const item of sent.transferred_sets) {
          if (
            typeof item?.header_set_id !== "string" ||
            !item.header_set_id ||
            typeof item?.merge_set_id !== "string" ||
            !item.merge_set_id ||
            !Number.isInteger(item.working_record_count) ||
            item.working_record_count < 1 ||
            seen.has(item.header_set_id)
          ) {
            throw new Error("Invalid transferred set.");
          }
          seen.add(item.header_set_id);
        }

        if (active) {
          setSets(response.merge_sets);
          setTransferredSets(sent.transferred_sets);
        }
      } catch (reason) {
        if (active) {
          setError(
            reason instanceof Error
              ? reason.message
              : "Unable to retrieve completed merge sets."
          );
        }
      } finally {
        if (active) setLoading(false);
      }
    }

    void load();

    return () => {
      active = false;
    };
  }, [base, client, project, refreshKey]);

  const groups = useMemo(
    () => groupCompletedSets(sets),
    [sets]
  );

  const transferredHeaderIds = new Set(
    transferredSets.map((item) => item.header_set_id)
  );
  const pendingGroups = groups.filter(
    (group) => !transferredHeaderIds.has(group.headerSetId)
  );
  const sentGroups = groups.filter(
    (group) => transferredHeaderIds.has(group.headerSetId)
  );

  const selectedGroup = pendingGroups.find(
    (group) => group.headerSetId === selectedHeader
  );

  const selectedForFurther =
    selectedGroup?.terminal ?? undefined;

  // Only an explicitly selected, unambiguous terminal
  // Merge Set may be transferred. Selecting the parent Header
  // Set never transfers a deduplicated dataset implicitly.
  const c2Candidate =
    selectedIds.length === 1
      ? pendingGroups.find(
          (group) =>
            !group.ambiguous &&
            group.terminal?.merge_set_id === selectedIds[0]
        )?.terminal
      : undefined;

  async function openC2Review() {
    if (!c2Candidate || c2Busy) return;

    const target = c2Candidate;
    setC2Busy(true);
    setC2Error("");
    setC2Success("");
    setC2Attested(false);

    try {
      const query = new URLSearchParams({
        client,
        project,
        merge_set_id: target.merge_set_id,
      });

      const result = (await apiGet(
        `${base}/c2/source-review?${query.toString()}`
      )) as C2SourceReview;

      if (
        result?.status !== "review_required" ||
        result.merge_set_id !== target.merge_set_id ||
        result.header_set_id !== target.header_set_id ||
        result.client !== client ||
        result.project !== project ||
        !Array.isArray(result.documents) ||
        result.documents.length === 0 ||
        result.document_count !== result.documents.length ||
        result.origin_authorized !== false ||
        result.transfer_authorized !== false ||
        !Number.isInteger(result.working_record_count) ||
        result.working_record_count <= 0 ||
        !Number.isInteger(result.original_source_record_count) ||
        result.original_source_record_count <= 0
      ) {
        throw new Error("C² source review response is invalid.");
      }

      const ids = result.documents.map((doc) => doc.doc_id);

      if (
        ids.some((id) => typeof id !== "string" || !id.trim()) ||
        new Set(ids).size !== ids.length
      ) {
        throw new Error("C² source document inventory is invalid.");
      }

      setC2Review({
        base,
        client,
        project,
        mergeSetId: target.merge_set_id,
        headerSetId: target.header_set_id,
        review: result,
      });
    } catch (reason) {
      setC2Error(
        reason instanceof Error
          ? reason.message
          : "Unable to load C² source review."
      );
    } finally {
      setC2Busy(false);
    }
  }

  async function approveAndTransferC2() {
    const selected = c2Review;

    if (!selected || !c2Attested || c2Busy) return;

    if (
      selected.base !== base ||
      selected.client !== client ||
      selected.project !== project
    ) {
      setC2Error("Project context changed. Reopen C² review.");
      return;
    }

    setC2Busy(true);
    setC2Error("");

    try {
      // Recheck the server-derived inventory immediately before
      // submitting the administrator's reviewed document IDs.
      const query = new URLSearchParams({
        client: selected.client,
        project: selected.project,
        merge_set_id: selected.mergeSetId,
      });

      const fresh = (await apiGet(
        `${selected.base}/c2/source-review?${query.toString()}`
      )) as C2SourceReview;

      const earlier = selected.review.documents
        .map((doc) => doc.doc_id)
        .sort();

      const current = Array.isArray(fresh?.documents)
        ? fresh.documents.map((doc) => doc.doc_id).sort()
        : [];

      if (
        fresh?.status !== "review_required" ||
        fresh.merge_set_id !== selected.mergeSetId ||
        fresh.header_set_id !== selected.headerSetId ||
        fresh.client !== selected.client ||
        fresh.project !== selected.project ||
        fresh.document_count !== current.length ||
        earlier.length !== current.length ||
        earlier.some((id, index) => id !== current[index]) ||
        fresh.working_record_count !==
          selected.review.working_record_count ||
        fresh.original_source_record_count !==
          selected.review.original_source_record_count
      ) {
        throw new Error(
          "Source inventory changed. Close and reopen C² review."
        );
      }

      const body = {
        client: selected.client,
        project: selected.project,
        merge_set_id: selected.mergeSetId,
      };

      await apiPost(`${selected.base}/c2/approve-origin`, {
        ...body,
        reviewed_doc_ids: earlier,
        attested_non_ai: true,
      });

      const transfer = await apiPost(
        `${selected.base}/c2/transfer`,
        body
      );

      if (
        transfer?.merge_set_id &&
        transfer.merge_set_id !== selected.mergeSetId
      ) {
        throw new Error("Unexpected C² transfer receipt.");
      }

      // Confirm the immutable transfer can be read back.
      const readQuery = new URLSearchParams({
        client: selected.client,
        project: selected.project,
      });

      const saved = await apiGet(
        `${selected.base}/c2/project-records?` +
          readQuery.toString()
      );

      if (
        saved?.status !== "ok" ||
        !Array.isArray(saved?.transferred_sets) ||
        !saved.transferred_sets.some(
          (item: { merge_set_id?: string }) =>
            item.merge_set_id === selected.mergeSetId
        )
      ) {
        throw new Error(
          "C² transfer response received, but read-back " +
            "verification did not confirm the saved Merge Set."
        );
      }

      setTransferredSets(saved.transferred_sets);
      setSelectedIds([]);
      setSelectedHeader("");

      setC2Success(
        `Verified C² transfer: ${selected.mergeSetId}. ` +
          "Open Captured Entities → C² to inspect the records."
      );
      setC2Review(null);
      setC2Attested(false);
    } catch (reason) {
      setC2Error(
        reason instanceof Error
          ? reason.message
          : "C² approval or transfer failed."
      );
    } finally {
      setC2Busy(false);
    }
  }

  function toggleHeaderSelection(headerSetId: string) {
    setSelectedHeader((previous) =>
      previous === headerSetId ? "" : headerSetId
    );
    setSelectedIds([]);
  }

  function toggleExpanded(headerSetId: string) {
    setExpandedHeaders((previous) =>
      previous.includes(headerSetId)
        ? previous.filter((id) => id !== headerSetId)
        : [...previous, headerSetId]
    );
  }

  function toggleSetSelection(
    mergeSetId: string,
    checked: boolean
  ) {
    setSelectedHeader("");
    setSelectedIds((previous) =>
      checked
        ? [...new Set([...previous, mergeSetId])]
        : previous.filter((id) => id !== mergeSetId)
    );
  }

  if (loading) {
    return (
      <p className="text-sm text-slate-400">
        Loading completed sets...
      </p>
    );
  }

  if (error) {
    return (
      <p role="alert" className="text-sm text-rose-300">
        {error}
      </p>
    );
  }

  const selectedCount =
    selectedHeader ? 1 : selectedIds.length;

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-3">
          <h3 className="insyt-section-title text-xl insyt-text-primary">
            5. Completed Merge Sets
          </h3>
          <span className="text-xs text-slate-400">
            {selectedCount} selected
          </span>
        </div>

        <div className="ml-auto flex flex-wrap gap-2">
          <button
            type="button"
            disabled={!selectedForFurther}
            onClick={() => {
              if (!selectedForFurther) return;
              onDedupeFurther(
                selectedForFurther.merge_set_id,
                selectedForFurther.header_set_id
              );
            }}
            title="Continue from the latest completed pass in the selected Header Set"
            className="rounded-lg bg-sky-600 px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-40"
          >
            Dedupe Further
          </button>

          <button
            type="button"
            disabled={!c2Candidate || c2Busy}
            onClick={() => void openC2Review()}
            title="Review the terminal Merge Set before transferring to C²"
            className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-40"
          >
            {c2Busy ? "Checking C²..." : "Send to C²"}
          </button>
        </div>
      </div>

      <div className="max-h-[450px] overflow-auto rounded-lg border border-slate-800">
        <table className="w-full text-left text-sm">
          <thead className="sticky top-0 z-10 bg-slate-900 text-slate-300">
            <tr>
              <th className="sticky left-0 bg-slate-900 p-3">
                Select
              </th>
              {[
                "Merge Set ID",
                "Header Set",
                "Completed",
                "Source Rows",
                "Working Rows",
                "Groups Merged",
                "Merge Index",
              ].map((heading) => (
                <th
                  key={heading}
                  className="whitespace-nowrap p-3"
                >
                  {heading}
                </th>
              ))}
            </tr>
          </thead>

          <tbody>
            {pendingGroups.map((group) => {
              const expanded = expandedHeaders.includes(
                group.headerSetId
              );

              return (
                <FragmentRows
                  key={group.headerSetId}
                  group={group}
                  expanded={expanded}
                  selectedHeader={selectedHeader}
                  selectedIds={selectedIds}
                  onToggleExpanded={() =>
                    toggleExpanded(group.headerSetId)
                  }
                  onToggleHeader={() =>
                    toggleHeaderSelection(group.headerSetId)
                  }
                  onToggleSet={toggleSetSelection}
                />
              );
            })}
          </tbody>
        </table>
      </div>

      {pendingGroups.length === 0 && (
        <p className="mt-3 text-sm text-slate-400">
          No pending completed Merge Sets.
        </p>
      )}

      <section
        aria-label="Sent to C²"
        className="mt-8 border-t border-slate-700 pt-5"
      >
        <h3 className="insyt-section-title text-xl insyt-text-primary">
          6. Sent to C²
        </h3>
        <p className="mb-3 mt-2 text-xs text-slate-400">
          Verified transfers. Source Merge Sets remain preserved.
        </p>

        {sentGroups.length === 0 ? (
          <p className="text-sm text-slate-400">
            No Merge Sets sent to C² yet.
          </p>
        ) : (
          <div className="overflow-auto rounded-lg border border-slate-800">
            <table className="w-full text-left text-sm">
              <thead className="bg-slate-900 text-slate-300">
                <tr>
                  {[
                    "Header Set",
                    "Transferred Merge Set",
                    "Pass",
                    "Source Rows",
                    "C² Records",
                    "Status",
                  ].map((heading) => (
                    <th key={heading} className="whitespace-nowrap p-3">
                      {heading}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {sentGroups.map((group) => {
                  const transfer = transferredSets.find(
                    (item) => item.header_set_id === group.headerSetId
                  );
                  const pass = group.sets.find(
                    (item) => item.merge_set_id === transfer?.merge_set_id
                  );

                  const expanded = expandedHeaders.includes(
                    group.headerSetId
                  );

                  return (
                    <Fragment key={group.headerSetId}>
                      <tr className="border-t border-slate-800 bg-slate-950">
                      <td className="p-3 text-sky-300">
                        <button
                          type="button"
                          onClick={() => toggleExpanded(group.headerSetId)}
                          aria-expanded={expanded}
                          aria-label={`${expanded ? "Collapse" : "Expand"} transferred Header Set ${group.headerSetId}`}
                          className="font-semibold text-sky-300 underline hover:text-sky-200"
                        >
                          {expanded ? "v" : ">"} {group.headerSetId}
                        </button>
                      </td>
                      <td className="whitespace-nowrap p-3 font-mono text-xs">
                        {transfer?.merge_set_id}
                      </td>
                      <td className="p-3">
                        {pass
                          ? `Pass ${pass.pass_number ?? 1}`
                          : "Historical transfer"}
                      </td>
                      <td className="p-3">
                        {pass?.raw_record_count ?? "--"}
                      </td>
                      <td className="p-3 text-emerald-300">
                        {transfer?.working_record_count}
                      </td>
                      <td className="p-3 text-emerald-300">
                        Sent to C²
                      </td>
                      </tr>

                      {expanded &&
                        group.sets.map((set) => (
                          <tr
                            key={set.merge_set_id}
                            className="border-t border-slate-800 bg-slate-900/60"
                          >
                            <td colSpan={6} className="p-4">
                              <div className="mb-3 flex flex-wrap items-center gap-3">
                                <span className="font-semibold text-sky-300">
                                  Pass {set.pass_number ?? 1}
                                </span>
                                <span className="break-all font-mono text-xs text-slate-300">
                                  {set.merge_set_id}
                                </span>
                                {set.merge_set_id === transfer?.merge_set_id && (
                                  <span className="text-xs font-semibold text-emerald-300">
                                    Sent to C²
                                  </span>
                                )}
                              </div>

                              <div className="grid gap-3 text-xs text-slate-300 md:grid-cols-3">
                                <div>
                                  <span className="text-slate-400">
                                    Merge Index / Categories:
                                  </span>
                                  <div className="mt-1 font-medium text-slate-100">
                                    {set.merge_index?.join(" + ") || "Not specified"}
                                  </div>
                                </div>
                                <div>
                                  <span className="text-slate-400">
                                    Original Source Rows:
                                  </span>
                                  <div className="mt-1">
                                    {set.raw_record_count}
                                  </div>
                                </div>
                                <div>
                                  <span className="text-slate-400">
                                    Working Rows:
                                  </span>
                                  <div className="mt-1">
                                    {set.working_record_count}
                                  </div>
                                </div>
                                <div>
                                  <span className="text-slate-400">
                                    Groups Merged:
                                  </span>
                                  <div className="mt-1">
                                    {set.merged_group_count}
                                  </div>
                                </div>
                                <div>
                                  <span className="text-slate-400">
                                    Completed:
                                  </span>
                                  <div className="mt-1">
                                    {set.created_at}
                                  </div>
                                </div>
                                <div>
                                  <span className="text-slate-400">
                                    Status:
                                  </span>
                                  <div className="mt-1">
                                    {set.status}
                                  </div>
                                </div>
                              </div>
                            </td>
                          </tr>
                        ))}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {selectedGroup?.ambiguous && (
        <p role="alert" className="mt-2 text-xs text-amber-300">
          This Header Set has multiple or incomplete merge
          histories. Automatic continuation is unavailable
          until the correct lineage is identified.
        </p>
      )}

      {selectedIds.length > 0 && (
        <p className="mt-2 text-xs text-slate-400">
          Select the individual Latest Merge Set for transfer to C².
          Select the Header Set row to continue deduplication.
        </p>
      )}

      <p className="mt-3 text-xs text-slate-400">
        Select the individual Merge Set marked Latest to send
        that completed version to C². Earlier passes and
        ambiguous histories are not eligible.
      </p>

      {c2Error && (
        <p role="alert" className="mt-3 text-sm text-rose-300">
          {c2Error}
        </p>
      )}

      {c2Success && (
        <p role="status" className="mt-3 text-sm text-emerald-300">
          {c2Success}
        </p>
      )}

      {c2Review && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label="Review C² source documents"
          className="mt-4 rounded-xl border border-slate-600 bg-slate-900 p-5"
        >
          <h4 className="mb-2 text-lg font-semibold text-white">
            Review source documents before Send to C²
          </h4>

          <p className="mb-3 break-all text-xs text-slate-300">
            Merge Set: {c2Review.mergeSetId}
          </p>

          <p className="mb-3 text-sm text-slate-200">
            {c2Review.review.document_count} source documents ?
            {" "}{c2Review.review.working_record_count} working records ?
            {" "}{c2Review.review.original_source_record_count}
            {" "}original source records
          </p>

          <div className="max-h-60 overflow-auto rounded-lg border border-slate-700 p-3">
            <ul className="space-y-2 text-sm text-slate-200">
              {c2Review.review.documents.map((doc) => (
                <li key={doc.doc_id} className="break-words">
                  <span className="font-mono text-xs">
                    {doc.doc_id}
                  </span>
                  {" ? "}
                  {doc.original_filename ||
                    doc.original_workbook_name ||
                    "Unnamed source"}
                  {doc.sheet_name ? ` / ${doc.sheet_name}` : ""}
                </li>
              ))}
            </ul>
          </div>

          <label className="mt-4 flex items-start gap-3 text-sm text-slate-200">
            <input
              type="checkbox"
              checked={c2Attested}
              disabled={c2Busy}
              onChange={(event) =>
                setC2Attested(event.target.checked)
              }
              className="mt-1"
            />
            <span>
              I reviewed the source-document inventory and attest
              that these records came from non-AI structured data
              processing and are eligible for the C² tab.
            </span>
          </label>

          <div className="mt-4 flex gap-3">
            <button
              type="button"
              disabled={c2Busy}
              onClick={() => {
                setC2Review(null);
                setC2Attested(false);
                setC2Error("");
              }}
              className="rounded-lg border border-slate-500 px-4 py-2 text-sm text-white disabled:opacity-40"
            >
              Cancel
            </button>
            <button
              type="button"
              disabled={!c2Attested || c2Busy}
              onClick={() => void approveAndTransferC2()}
              className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-40"
            >
              {c2Busy ? "Processing..." : "Approve and Send to C²"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function FragmentRows({
  group,
  expanded,
  selectedHeader,
  selectedIds,
  onToggleExpanded,
  onToggleHeader,
  onToggleSet,
}: {
  group: HeaderGroup;
  expanded: boolean;
  selectedHeader: string;
  selectedIds: string[];
  onToggleExpanded: () => void;
  onToggleHeader: () => void;
  onToggleSet: (
    mergeSetId: string,
    checked: boolean
  ) => void;
}) {
  const latest = group.terminal;

  return (
    <>
      <tr className="border-t border-sky-900 bg-slate-900/70">
        <td className="sticky left-0 bg-slate-900 p-3">
          <input
            type="checkbox"
            aria-label={`Select Header Set ${group.headerSetId}`}
            checked={selectedHeader === group.headerSetId}
            onChange={onToggleHeader}
          />
        </td>
        <td className="whitespace-nowrap p-3">
          <button
            type="button"
            onClick={onToggleExpanded}
            aria-expanded={expanded}
            aria-label={`${expanded ? "Collapse" : "Expand"} Header Set ${group.headerSetId}`}
            className="font-semibold text-sky-300 hover:text-sky-200"
          >
            {expanded ? "▾" : "▸"} {group.headerSetId}
          </button>
        </td>
        <td className="p-3 text-slate-300">
          {group.sets.length} saved passes
        </td>
        <td className="p-3 text-slate-400">
          {latest?.created_at ?? "—"}
        </td>
        <td className="p-3 text-slate-200">
          {latest?.raw_record_count ?? "—"}
        </td>
        <td className="p-3 font-semibold text-emerald-300">
          {latest?.working_record_count ?? "—"}
        </td>
        <td className="p-3 text-slate-200">
          {latest?.merged_group_count ?? "—"}
        </td>
        <td className="p-3 text-slate-300">
          {latest
            ? `Latest: ${latest.merge_index?.join(" + ") || ""}`
            : "Multiple or incomplete histories"}
        </td>
      </tr>

      {expanded &&
        group.sets.map((set) => (
          <tr
            key={set.merge_set_id}
            className="border-t border-slate-800 bg-slate-950"
          >
            <td className="sticky left-0 bg-slate-950 p-3">
              <input
                type="checkbox"
                aria-label={`Select ${set.merge_set_id}`}
                disabled={set.status !== "completed"}
                checked={selectedIds.includes(set.merge_set_id)}
                onChange={(event) =>
                  onToggleSet(
                    set.merge_set_id,
                    event.target.checked
                  )
                }
              />
            </td>
            <td className="whitespace-nowrap p-3 pl-8 text-sky-300">
              Pass {set.pass_number ?? 1}:{" "}
              {set.merge_set_id}
              {latest?.merge_set_id === set.merge_set_id && (
                <span className="ml-2 text-xs text-emerald-300">
                  Latest
                </span>
              )}
            </td>
            <td className="p-3 text-slate-200">
              {set.header_set_id}
            </td>
            <td className="whitespace-nowrap p-3 text-slate-200">
              {set.created_at}
            </td>
            <td className="p-3 text-slate-200">
              {set.raw_record_count}
            </td>
            <td className="p-3 text-slate-200">
              {set.working_record_count}
            </td>
            <td className="p-3 text-slate-200">
              {set.merged_group_count}
            </td>
            <td className="p-3 text-slate-200">
              {set.merge_index?.join(" + ") || ""}
            </td>
          </tr>
        ))}
    </>
  );
}