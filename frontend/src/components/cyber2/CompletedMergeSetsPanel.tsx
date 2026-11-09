"use client";

import { useEffect, useState } from "react";
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

export default function CompletedMergeSetsPanel({
  base,
  client,
  project,
  refreshKey,
  onDedupeFurther,
}: Props) {
  const [sets, setSets] = useState<CompletedSet[]>([]);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;

    async function load() {
      setSets([]);
      setSelectedIds([]);
      setError("");

      if (!client || !project) return;

      setLoading(true);

      try {
        const query = new URLSearchParams({ client, project });

        const response = await apiGet(
          `${base}/merge-dedupe/completed?${query.toString()}`
        );

        if (
          response?.status !== "ok" ||
          !Array.isArray(response?.merge_sets)
        ) {
          throw new Error("Invalid Completed Merge Sets response.");
        }

        if (active) setSets(response.merge_sets);
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

  const eligibleIds = sets
    .filter((item) => item.status === "completed")
    .map((item) => item.merge_set_id);

  const selectedCount = selectedIds.length;
  const selectedForFurther =
    selectedCount === 1
      ? sets.find(
          (item) =>
            item.merge_set_id === selectedIds[0] &&
            item.status === "completed"
        )
      : undefined;

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
            title="Use this completed set as the next deduplication input"
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
              <input
                type="checkbox"
                aria-label="Select all completed merge sets"
                checked={
                  eligibleIds.length > 0 &&
                  eligibleIds.every((id) => selectedIds.includes(id))
                }
                onChange={(event) =>
                  setSelectedIds(
                    event.target.checked ? [...eligibleIds] : []
                  )
                }
              />
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
              <th key={heading} className="whitespace-nowrap p-3">
                {heading}
              </th>
            ))}
          </tr>
        </thead>

        <tbody>
          {sets.map((set) => (
            <tr
              key={set.merge_set_id}
              className="border-t border-slate-800"
            >
              <td className="sticky left-0 bg-slate-950 p-3">
                <input
                  type="checkbox"
                  aria-label={`Select ${set.merge_set_id}`}
                  disabled={set.status !== "completed"}
                  checked={selectedIds.includes(set.merge_set_id)}
                  onChange={(event) =>
                    setSelectedIds((previous) =>
                      event.target.checked
                        ? [...previous, set.merge_set_id]
                        : previous.filter(
                            (id) => id !== set.merge_set_id
                          )
                    )
                  }
                />
              </td>
              <td className="whitespace-nowrap p-3 text-sky-300">
                {set.merge_set_id}
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
        </tbody>
        </table>
      </div>

      <p className="mt-3 text-xs text-slate-400">
        Transfer to C² will be enabled after the separate
        Captured Entities C² workflow is validated.
      </p>
    </div>
  );
}
