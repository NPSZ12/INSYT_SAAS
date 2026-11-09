"use client";

import { useEffect, useMemo, useState } from "react";
import { apiGet } from "../../lib/api";

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
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [selectedHeader, setSelectedHeader] = useState("");
  const [expandedHeaders, setExpandedHeaders] =
    useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;

    async function load() {
      setSets([]);
      setSelectedIds([]);
      setSelectedHeader("");
      setError("");

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

        if (active) {
          setSets(response.merge_sets);
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

  const selectedGroup = groups.find(
    (group) => group.headerSetId === selectedHeader
  );

  const selectedForFurther =
    selectedGroup?.terminal ?? undefined;

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

  if (!sets.length) {
    return (
      <p className="text-sm text-slate-400">
        No completed merge sets saved for this project.
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
            disabled
            title="Available after C² transfer validation"
            className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-40"
          >
            Send to C²
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
            {groups.map((group) => {
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

      {selectedGroup?.ambiguous && (
        <p role="alert" className="mt-2 text-xs text-amber-300">
          This Header Set has multiple or incomplete merge
          histories. Automatic continuation is unavailable
          until the correct lineage is identified.
        </p>
      )}

      {selectedIds.length > 0 && (
        <p className="mt-2 text-xs text-slate-400">
          Individual Merge Set selection is retained for
          future C² transfer. Select the Header Set row
          to continue deduplication from its latest pass.
        </p>
      )}

      <p className="mt-3 text-xs text-slate-400">
        Transfer to C² will be enabled after the separate
        Captured Entities C² workflow is validated.
      </p>
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