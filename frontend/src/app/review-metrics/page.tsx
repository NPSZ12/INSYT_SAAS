"use client";

import {
  Fragment,
  Suspense,
  useEffect,
  useMemo,
  useState,
} from "react";
import { useSearchParams } from "next/navigation";

import AppShell from "../../components/AppShell";
import PageHeader from "../../components/PageHeader";
import ContentCard from "../../components/ContentCard";
import { apiGet, apiPost } from "../../lib/api";


type ReviewHoursRow = {
  username: string;
  display_name: string;
  role: string;
  mon_hours: number;
  tue_hours: number;
  wed_hours: number;
  thu_hours: number;
  fri_hours: number;
  sat_hours: number;
  sun_hours: number;
  week_total: number;
};


type ReviewerMetricRow = {
  username: string;
  display_name: string;
  email?: string;
  role: string;
  status?: string;

  staffing_groups?: string[];
  performance_score?: number | null;
  performance_band?: string;

  hours: number;

  documents_reviewed: number;
  documents_coded: number;
  documents_per_hour: number;

  responsive: number;
  not_responsive: number;
  nfr: number;

  qc_reviewed: number;
  qc_no_change?: number;
  qc_changes: number;
  qc_nfr?: number;
  qc_accuracy?: number;

  batches_touched: number;
  projects_touched?: number;

  first_activity: string;
  last_activity: string;
};


function prettyWorkspace(value: string) {
  if (!value) return "Workspace";

  return (
    value.charAt(0).toUpperCase() +
    value.slice(1)
  );
}

function prettyRole(role: string) {
  const clean = String(
    role || ""
  )
    .trim()
    .toLowerCase();

  if (
    clean === "rm" ||
    clean === "review manager"
  ) {
    return "RM";
  }

  if (clean === "insyt manager") {
    return "SRM";
  }

  if (clean === "tl") {
    return "TL";
  }

  if (clean === "qc") {
    return "QC";
  }

  if (
    clean === "1l" ||
    clean === "1l reviewer"
  ) {
    return "Reviewer";
  }

  if (clean === "reviewer") {
    return "Reviewer";
  }

  return role;
}

function formatNumber(value: number) {
  return Number(value || 0).toLocaleString();
}


function formatHours(value: number) {
  return Number(value || 0).toFixed(2);
}


function buildMetricRow(
  row: ReviewHoursRow
): ReviewerMetricRow {
  return {
    username: row.username,
    display_name:
      row.display_name || row.username,
    role: prettyRole(
      row.role || "Reviewer"
    ),

    hours: Number(row.week_total || 0),

    documents_reviewed: 0,
    documents_coded: 0,
    documents_per_hour: 0,

    responsive: 0,
    not_responsive: 0,
    nfr: 0,

    qc_reviewed: 0,
    qc_changes: 0,

    batches_touched: 0,

    first_activity: "",
    last_activity: "",
  };
}


function ReviewMetricsContent() {
  const searchParams = useSearchParams();

  const workspace =
    searchParams.get("workspace") || "";

  const client =
    searchParams.get("client") || "";

  const project =
    searchParams.get("project") || "";

  const [rows, setRows] =
    useState<ReviewerMetricRow[]>([]);

  const [loading, setLoading] =
    useState(true);

  const [error, setError] =
    useState("");

  const [expandedUsers, setExpandedUsers] =
    useState<Record<string, boolean>>({});

  const isProjectMode =
    Boolean(workspace && client && project);

  const [nameFilter, setNameFilter] =
    useState("");

  const [levelFilter, setLevelFilter] =
    useState("");

  const [groupFilter, setGroupFilter] =
    useState("");

  const [scoreMin, setScoreMin] =
    useState("");

  const [editingUser, setEditingUser] =
    useState("");

  const [editGroups, setEditGroups] =
    useState("");

  const [editScore, setEditScore] =
    useState("");

  const [editBand, setEditBand] =
    useState("Unrated");

  const [savingProfile, setSavingProfile] =
    useState(false);

  useEffect(() => {
    let cancelled = false;

    async function loadMetrics() {
      setLoading(true);
      setError("");

      try {
        if (isProjectMode) {
          const params =
            new URLSearchParams({
              workspace,
              client,
              project,
              period: "project",
            });

          const data = await apiGet(
            `/api/review/metrics?${params.toString()}`
          );

          if (cancelled) return;

          const reviewerRows =
            Array.isArray(data?.reviewers)
              ? data.reviewers
              : [];

          setRows(
            reviewerRows.map((row: any) => ({
              username: row.username,
              display_name:
                row.display_name ||
                row.username,
              role:
                prettyRole(
                  row.role ||
                  "Reviewer"
                ),

              hours: Number(
                row.review_hours || 0
              ),

              documents_reviewed:
                Number(
                  row.documents_reviewed ||
                    0
                ),

              documents_coded:
                Number(
                  row.documents_coded ||
                    0
                ),

              documents_per_hour:
                Number(
                  row.documents_per_hour ||
                    0
                ),

              responsive:
                Number(
                  row.responsive || 0
                ),

              not_responsive:
                Number(
                  row.not_responsive || 0
                ),

              nfr:
                Number(
                  row.further_review || 0
                ),

              qc_reviewed:
                Number(
                  row.qc_reviewed || 0
                ),

              qc_no_change:
                Number(
                  row.qc_no_change || 0
                ),

              qc_changes:
                Number(
                  row.qc_changes || 0
                ),

              qc_nfr:
                Number(
                  row.qc_nfr || 0
                ),

              qc_accuracy:
                Number(row.qc_reviewed || 0) >
                0
                  ? (
                      Number(
                        row.qc_no_change || 0
                      ) /
                      Number(
                        row.qc_reviewed || 1
                      )
                    ) *
                    100
                  : 0,

              batches_touched:
                Number(
                  row.batches_touched || 0
                ),

              projects_touched: 1,

              first_activity:
                row.first_activity || "",

              last_activity:
                row.last_activity || "",
            }))
          );
        } else {
          const data = await apiGet(
            "/api/users/staffing-metrics"
          );

          if (cancelled) return;

          const reviewerRows =
            Array.isArray(data?.users)
              ? data.users
              : [];

          setRows(
            reviewerRows.map((row: any) => ({
              username: row.username,
              display_name:
                row.display_name ||
                row.username,
              email: row.email || "",
              role:
                prettyRole(
                  row.role ||
                  "Reviewer"
                ),
              status:
                row.status || "",

              staffing_groups:
                row.staffing_groups || [],

              performance_score:
                row.performance_score ??
                null,

              performance_band:
                row.performance_band ||
                "Unrated",

              hours:
                Number(
                  row.review_hours || 0
                ),

              documents_reviewed:
                Number(
                  row.documents_reviewed ||
                    0
                ),

              documents_coded:
                Number(
                  row.documents_coded ||
                    0
                ),

              documents_per_hour:
                Number(
                  row.documents_per_hour ||
                    0
                ),

              responsive:
                Number(
                  row.responsive || 0
                ),

              not_responsive:
                Number(
                  row.not_responsive || 0
                ),

              nfr:
                Number(
                  row.further_review || 0
                ),

              qc_reviewed:
                Number(
                  row.qc_reviewed || 0
                ),

              qc_no_change:
                Number(
                  row.qc_no_change || 0
                ),

              qc_changes:
                Number(
                  row.qc_changes || 0
                ),

              qc_nfr:
                Number(
                  row.qc_nfr || 0
                ),

              qc_accuracy:
                Number(
                  row.qc_accuracy || 0
                ),

              batches_touched:
                Number(
                  row.batches_touched || 0
                ),

              projects_touched:
                Number(
                  row.projects_touched || 0
                ),

              first_activity:
                row.first_activity || "",

              last_activity:
                row.last_activity || "",
            }))
          );
        }
      } catch (err) {
        console.error(
          "Failed to load Reviewer Metrics:",
          err
        );

        if (!cancelled) {
          setRows([]);
          setError(
            "Unable to load Reviewer Metrics."
          );
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    loadMetrics();

    return () => {
      cancelled = true;
    };
  }, [
    workspace,
    client,
    project,
    isProjectMode,
  ]);

  const levelOptions = useMemo(
    () =>
      Array.from(
        new Set(
          rows
            .map((row) => row.role)
            .filter(Boolean)
        )
      ).sort(),
    [rows]
  );

  const groupOptions = useMemo(
    () =>
      Array.from(
        new Set(
          rows.flatMap(
            (row) =>
              row.staffing_groups || []
          )
        )
      ).sort(),
    [rows]
  );

  const filteredRows = useMemo(() => {
    if (isProjectMode) {
      return rows;
    }

    const search =
      nameFilter
        .trim()
        .toLowerCase();

    const minimum =
      scoreMin === ""
        ? null
        : Number(scoreMin);

    return rows.filter((row) => {
      if (
        search &&
        !String(
          row.display_name || ""
        )
          .toLowerCase()
          .includes(search) &&
        !String(
          row.username || ""
        )
          .toLowerCase()
          .includes(search) &&
        !String(row.email || "")
          .toLowerCase()
          .includes(search)
      ) {
        return false;
      }

      if (
        levelFilter &&
        row.role !== levelFilter
      ) {
        return false;
      }

      if (
        groupFilter &&
        !(
          row.staffing_groups || []
        ).includes(groupFilter)
      ) {
        return false;
      }

      if (
        minimum !== null &&
        (
          row.performance_score === null ||
          row.performance_score === undefined ||
          row.performance_score < minimum
        )
      ) {
        return false;
      }

      return true;
    });
  }, [
    rows,
    isProjectMode,
    nameFilter,
    levelFilter,
    groupFilter,
    scoreMin,
  ]);

  const projectTotals = useMemo(() => {
    const total = {
      assigned_reviewers: rows.length,
      review_hours: 0,
      documents_reviewed: 0,
      documents_coded: 0,
      qc_reviewed: 0,
      qc_changes: 0,
      responsive: 0,
      not_responsive: 0,
      nfr: 0,
    };

    for (const row of rows) {
      total.review_hours +=
        Number(row.hours || 0);

      total.documents_reviewed +=
        Number(
          row.documents_reviewed || 0
        );

      total.documents_coded +=
        Number(
          row.documents_coded || 0
        );

      total.qc_reviewed +=
        Number(row.qc_reviewed || 0);

      total.qc_changes +=
        Number(row.qc_changes || 0);

      total.responsive +=
        Number(row.responsive || 0);

      total.not_responsive +=
        Number(
          row.not_responsive || 0
        );

      total.nfr +=
        Number(row.nfr || 0);
    }

    return total;
  }, [rows]);


  function toggleReviewer(
    username: string
  ) {
    setExpandedUsers(
      (current) => ({
        ...current,
        [username]:
          !current[username],
      })
    );
  }

  function beginEdit(row: ReviewerMetricRow) {
    setEditingUser(row.username);

    setEditGroups(
      (row.staffing_groups || []).join(", ")
    );

    setEditScore(
      row.performance_score === null ||
      row.performance_score === undefined
        ? ""
        : String(row.performance_score)
    );

    setEditBand(
      row.performance_band || "Unrated"
    );
  }

  function cancelEdit() {
    setEditingUser("");
    setEditGroups("");
    setEditScore("");
    setEditBand("Unrated");
  }

  async function saveReviewerProfile(
    row: ReviewerMetricRow
  ) {
    setSavingProfile(true);
    setError("");

    try {
      const staffingGroups =
        editGroups
          .split(",")
          .map((value) =>
            value.trim()
          )
          .filter(Boolean);

      const score =
        editScore.trim() === ""
          ? null
          : Number(editScore);

      await apiPost(
        "/api/users/reviewer-metrics-profile",
        {
          username: row.username,
          staffing_groups:
            staffingGroups,
          performance_score:
            score,
          performance_band:
            editBand || "Unrated",
          performance_rating_source:
            "metrics",
        }
      );

      setRows((current) =>
        current.map((item) =>
          item.username ===
          row.username
            ? {
                ...item,
                staffing_groups:
                  staffingGroups,
                performance_score:
                  score,
                performance_band:
                  editBand ||
                  "Unrated",
              }
            : item
        )
      );

      cancelEdit();
    } catch (err) {
      console.error(
        "Unable to save Reviewer Metrics profile:",
        err
      );

      setError(
        "Unable to save reviewer Group / Overall Score."
      );
    } finally {
      setSavingProfile(false);
    }
  }

  return (
    <AppShell>
      <div className="space-y-6">
        <PageHeader
          title="Reviewer Metrics"
          subtitle={
            isProjectMode
              ? `${prettyWorkspace(
                  workspace
                )} • ${client} • ${project}`
              : "Detailed reviewer performance across INSYT projects."
          }
        />

        {isProjectMode && (
          <ContentCard title="Overall Project Metrics">
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
              <MetricCard
                label="Assigned Reviewers"
                value={formatNumber(
                  projectTotals.assigned_reviewers
                )}
              />

              <MetricCard
                label="Review Hours"
                value={formatHours(
                  projectTotals.review_hours
                )}
              />

              <MetricCard
                label="Documents Reviewed"
                value={formatNumber(
                  projectTotals.documents_reviewed
                )}
              />

              <MetricCard
                label="Documents / Hour"
                value={
                  projectTotals.review_hours >
                  0
                    ? (
                        projectTotals.documents_reviewed /
                        projectTotals.review_hours
                      ).toFixed(2)
                    : "0.00"
                }
              />

              <MetricCard
                label="Documents Coded"
                value={formatNumber(
                  projectTotals.documents_coded
                )}
              />

              <MetricCard
                label="Responsive"
                value={formatNumber(
                  projectTotals.responsive
                )}
              />

              <MetricCard
                label="Not Responsive"
                value={formatNumber(
                  projectTotals.not_responsive
                )}
              />

              <MetricCard
                label="NFR"
                value={formatNumber(
                  projectTotals.nfr
                )}
              />

              <MetricCard
                label="QC Reviewed"
                value={formatNumber(
                  projectTotals.qc_reviewed
                )}
              />

              <MetricCard
                label="QC Changes"
                value={formatNumber(
                  projectTotals.qc_changes
                )}
              />
            </div>
          </ContentCard>
        )}

        {!isProjectMode && (
          <ContentCard title="Reviewer Search">
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
              <input
                value={nameFilter}
                onChange={(event) =>
                  setNameFilter(
                    event.target.value
                  )
                }
                placeholder="Search name, email, username"
                className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white outline-none focus:border-sky-500"
              />

              <select
                value={levelFilter}
                onChange={(event) =>
                  setLevelFilter(
                    event.target.value
                  )
                }
                className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white"
              >
                <option value="">
                  All Levels
                </option>

                {levelOptions.map(
                  (role) => (
                    <option
                      key={role}
                      value={role}
                    >
                      {role}
                    </option>
                  )
                )}
              </select>

              <select
                value={groupFilter}
                onChange={(event) =>
                  setGroupFilter(
                    event.target.value
                  )
                }
                className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white"
              >
                <option value="">
                  All Groups
                </option>

                {groupOptions.map(
                  (group) => (
                    <option
                      key={group}
                      value={group}
                    >
                      Group {group}
                    </option>
                  )
                )}
              </select>

              <input
                type="number"
                value={scoreMin}
                onChange={(event) =>
                  setScoreMin(
                    event.target.value
                  )
                }
                placeholder="Minimum Overall Score"
                className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white outline-none focus:border-sky-500"
              />
            </div>
          </ContentCard>
        )}

        <ContentCard title="Reviewer Metrics">
          {loading && (
            <div className="text-sm text-slate-400">
              Loading Review Metrics...
            </div>
          )}

          {!loading && error && (
            <div className="text-sm text-red-400">
              {error}
            </div>
          )}

          {!loading &&
            !error &&
            filteredRows.length === 0 && (
              <div className="text-sm text-slate-400">
                No assigned reviewers found.
              </div>
            )}

          {!loading &&
            !error &&
            filteredRows.length > 0 && (
              <div className="overflow-x-auto">
                <table className="min-w-[1500px] w-full text-sm">
                  <thead>
                    <tr className="border-b border-slate-700 text-slate-300">
                      <th className="p-3 text-left">
                        Expand
                      </th>

                      <th className="p-3 text-left">
                        Reviewer
                      </th>

                      <th className="p-3 text-left">
                        Role
                      </th>

                      <th className="p-3 text-left">
                        Group
                      </th>

                      <th className="p-3 text-right">
                        Overall Score
                      </th>

                      <th className="p-3 text-left">
                        Performance Band
                      </th>

                      <th className="p-3 text-right">
                        Hours
                      </th>

                      <th className="p-3 text-right">
                        Docs Reviewed
                      </th>

                      <th className="p-3 text-right">
                        Docs Coded
                      </th>

                      <th className="p-3 text-right">
                        Docs / Hr
                      </th>

                      <th className="p-3 text-right">
                        Responsive
                      </th>

                      <th className="p-3 text-right">
                        Not Responsive
                      </th>

                      <th className="p-3 text-right">
                        NFR
                      </th>

                      <th className="p-3 text-right">
                        QC Reviewed
                      </th>

                      <th className="p-3 text-right">
                        QC Changes
                      </th>

                      <th className="p-3 text-right">
                        Batches
                      </th>

                      <th className="p-3 text-left">
                        First Activity
                      </th>

                      <th className="p-3 text-left">
                        Last Activity
                      </th>
                    </tr>
                  </thead>

                  <tbody>
                    {filteredRows.map((row) => {
                      const expanded =
                        expandedUsers[
                          row.username
                        ] === true;

                      return (
                        <Fragment key={row.username}>
                          <tr
                            className="border-b border-slate-800"
                          >
                            <td className="p-3">
                              <button
                                type="button"
                                onClick={() =>
                                  toggleReviewer(
                                    row.username
                                  )
                                }
                                className="rounded border border-slate-700 px-2 py-1 text-xs hover:border-sky-500"
                              >
                                {expanded
                                  ? "−"
                                  : "+"}
                              </button>
                            </td>

                            <td className="p-3 whitespace-nowrap">
                              {row.display_name}
                            </td>

                            <td className="p-3 whitespace-nowrap">
                              {prettyRole(row.role)}
                            </td>

                            <td className="p-3 whitespace-nowrap">
                              {(row.staffing_groups || [])
                                .length > 0
                                ? (row.staffing_groups || [])
                                    .join(", ")
                                : "—"}
                            </td>

                            <td className="p-3 text-right font-semibold">
                              {row.performance_score ===
                                null ||
                              row.performance_score ===
                                undefined
                                ? "N/A"
                                : row.performance_score}
                            </td>

                            <td className="p-3 whitespace-nowrap">
                              {row.performance_band ||
                                "Unrated"}
                            </td>

                            <td className="p-3 text-right">
                              {formatHours(
                                row.hours
                              )}
                            </td>

                            <td className="p-3 text-right">
                              {formatNumber(
                                row.documents_reviewed
                              )}
                            </td>

                            <td className="p-3 text-right">
                              {formatNumber(
                                row.documents_coded
                              )}
                            </td>

                            <td className="p-3 text-right">
                              {row.documents_per_hour.toFixed(
                                2
                              )}
                            </td>

                            <td className="p-3 text-right">
                              {formatNumber(
                                row.responsive
                              )}
                            </td>

                            <td className="p-3 text-right">
                              {formatNumber(
                                row.not_responsive
                              )}
                            </td>

                            <td className="p-3 text-right">
                              {formatNumber(
                                row.nfr
                              )}
                            </td>

                            <td className="p-3 text-right">
                              {formatNumber(
                                row.qc_reviewed
                              )}
                            </td>

                            <td className="p-3 text-right">
                              {formatNumber(
                                row.qc_changes
                              )}
                            </td>

                            <td className="p-3 text-right">
                              {formatNumber(
                                row.batches_touched
                              )}
                            </td>

                            <td className="p-3 whitespace-nowrap">
                              {row.first_activity ||
                                "—"}
                            </td>

                            <td className="p-3 whitespace-nowrap">
                              {row.last_activity ||
                                "—"}
                            </td>
                          </tr>

                          {expanded && (
                            <tr
                              className="border-b border-slate-800 bg-slate-950/40"
                            >
                              <td
                                colSpan={18}
                                className="p-4"
                              >
                                <div className="grid gap-4 md:grid-cols-3 xl:grid-cols-5">
                                  <MetricCard
                                    label="Reviewer"
                                    value={
                                      row.display_name
                                    }
                                  />

                                  <MetricCard
                                    label="Role"
                                    value={
                                      prettyRole(row.role)
                                    }
                                  />

                                  <MetricCard
                                    label="Review Hours"
                                    value={formatHours(
                                      row.hours
                                    )}
                                  />

                                  <MetricCard
                                    label="Documents Reviewed"
                                    value={formatNumber(
                                      row.documents_reviewed
                                    )}
                                  />

                                  <MetricCard
                                    label="Documents / Hour"
                                    value={row.documents_per_hour.toFixed(
                                      2
                                    )}
                                  />

                                  {!isProjectMode && (
                                    <div className="mt-5 rounded-xl border border-slate-800 bg-slate-950/60 p-4">
                                      {editingUser ===
                                      row.username ? (
                                        <div className="grid gap-4 md:grid-cols-4">
                                          <div>
                                            <div className="mb-2 text-xs text-slate-400">
                                              Groups
                                            </div>

                                            <input
                                              value={editGroups}
                                              onChange={(event) =>
                                                setEditGroups(
                                                  event.target.value
                                                )
                                              }
                                              placeholder="1, 2, 3"
                                              className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white"
                                            />
                                          </div>

                                          <div>
                                            <div className="mb-2 text-xs text-slate-400">
                                              Overall Score
                                            </div>

                                            <input
                                              type="number"
                                              min="0"
                                              max="100"
                                              value={editScore}
                                              onChange={(event) =>
                                                setEditScore(
                                                  event.target.value
                                                )
                                              }
                                              placeholder="0-100"
                                              className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white"
                                            />
                                          </div>

                                          <div>
                                            <div className="mb-2 text-xs text-slate-400">
                                              Performance Band
                                            </div>

                                            <input
                                              value={editBand}
                                              onChange={(event) =>
                                                setEditBand(
                                                  event.target.value
                                                )
                                              }
                                              placeholder="Unrated"
                                              className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white"
                                            />
                                          </div>

                                          <div className="flex items-end gap-2">
                                            <button
                                              type="button"
                                              disabled={savingProfile}
                                              onClick={() =>
                                                saveReviewerProfile(
                                                  row
                                                )
                                              }
                                              className="rounded-lg bg-teal-600 px-4 py-2 text-sm font-semibold text-white hover:bg-teal-500 disabled:opacity-50"
                                            >
                                              Save
                                            </button>

                                            <button
                                              type="button"
                                              onClick={cancelEdit}
                                              className="rounded-lg border border-slate-700 px-4 py-2 text-sm text-slate-300 hover:bg-slate-800"
                                            >
                                              Cancel
                                            </button>
                                          </div>
                                        </div>
                                      ) : (
                                        <button
                                          type="button"
                                          onClick={() =>
                                            beginEdit(row)
                                          }
                                          className="rounded-lg border border-slate-700 px-4 py-2 text-sm text-slate-300 hover:bg-slate-800"
                                        >
                                          Edit Group / Score
                                        </button>
                                      )}
                                    </div>
                                  )}
                                </div>
                              </td>
                            </tr>
                          )}
                        </Fragment>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
        </ContentCard>
      </div>
    </AppShell>
  );
}

export default function ReviewMetricsPage() {
  return (
    <Suspense
      fallback={
        <AppShell>
          <div className="space-y-6">
            <PageHeader
              title="Reviewer Metrics"
              subtitle="Loading Reviewer Metrics..."
            />
          </div>
        </AppShell>
      }
    >
      <ReviewMetricsContent />
    </Suspense>
  );
}

function MetricCard({
  label,
  value,
}: {
  label: string;
  value: string;
}) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-950/50 p-4">
      <div className="text-xs uppercase tracking-wide text-slate-400">
        {label}
      </div>

      <div className="mt-2 text-xl font-semibold text-white">
        {value}
      </div>
    </div>
  );
}