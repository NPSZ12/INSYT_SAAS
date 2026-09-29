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
import { apiGet } from "../../lib/api";


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
  role: string;

  hours: number;

  documents_reviewed: number;
  documents_coded: number;
  documents_per_hour: number;

  responsive: number;
  not_responsive: number;
  nfr: number;

  qc_reviewed: number;
  qc_changes: number;

  batches_touched: number;

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
    role: row.role || "Reviewer",

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


  useEffect(() => {
    if (
      !workspace ||
      !client ||
      !project
    ) {
      setRows([]);
      setLoading(false);
      return;
    }

    let cancelled = false;

    async function loadMetrics() {
      setLoading(true);
      setError("");

      try {
        const params =
          new URLSearchParams({
            workspace,
            client,
            project,
          });

        const data = await apiGet(
          `/api/timesheet/review-hours?${params.toString()}`
        );

        if (cancelled) {
          return;
        }

        const reviewRows =
          Array.isArray(data?.rows)
            ? data.rows
            : [];

        setRows(
          reviewRows.map(
            (row: ReviewHoursRow) =>
              buildMetricRow(row)
          )
        );
      } catch (err) {
        console.error(
          "Failed to load Review Metrics:",
          err
        );

        if (!cancelled) {
          setRows([]);
          setError(
            "Unable to load Review Metrics."
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


  if (
    !workspace ||
    !client ||
    !project
  ) {
    return (
      <AppShell>
        <div className="space-y-6">
          <PageHeader
            title="Review Metrics"
            subtitle="Return to Projects and select a project first."
          />
        </div>
      </AppShell>
    );
  }


  return (
    <AppShell>
      <div className="space-y-6">
        <PageHeader
          title="Review Metrics"
          subtitle={`${prettyWorkspace(
            workspace
          )} • ${client} • ${project}`}
        />

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
            rows.length === 0 && (
              <div className="text-sm text-slate-400">
                No assigned reviewers found.
              </div>
            )}

          {!loading &&
            !error &&
            rows.length > 0 && (
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
                    {rows.map((row) => {
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
                              {row.role}
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
                                colSpan={15}
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
                                      row.role
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
              title="Review Metrics"
              subtitle="Loading Review Metrics..."
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