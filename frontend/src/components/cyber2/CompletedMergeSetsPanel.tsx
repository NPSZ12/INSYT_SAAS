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
};

export default function CompletedMergeSetsPanel({
  base,
  client,
  project,
  refreshKey,
}: Props) {
  const [sets, setSets] = useState<CompletedSet[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;

    async function load() {
      setSets([]);
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

  return (
    <div className="overflow-x-auto rounded-lg border border-slate-800">
      <table className="w-full text-left text-sm">
        <thead className="bg-slate-900 text-slate-300">
          <tr>
            {[
              "Merge Set ID",
              "Header Set",
              "Completed",
              "RAW Rows",
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

      <p className="p-3 text-xs text-slate-400">
        Transfer to C² will be enabled after the separate
        Captured Entities C² workflow is validated.
      </p>
    </div>
  );
}
