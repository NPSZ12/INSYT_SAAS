"use client";

import { Fragment, Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";

import AppShell from "../../components/AppShell";
import PageContainer from "../../components/PageContainer";
import PageHeader from "../../components/PageHeader";
import ContentCard from "../../components/ContentCard";
import Button from "../../components/Button";
import { apiGet } from "../../lib/api";

type WeeklyTotal = {
  week_ending: string;
  project_weekly_total: number;
  one_l_weekly_total: number;
  qc_weekly_total: number;
  tl_weekly_total: number;
  rm_weekly_total: number;
};

type ProjectHoursRow = {
  workspace: string;
  client_id: string;
  project_id: string;

  project_total: number;
  one_l_project_total: number;
  qc_project_total: number;
  tl_project_total: number;
  rm_project_total: number;

  weekly_totals: WeeklyTotal[];
};

function prettyWorkspace(workspace: string) {
  if (workspace === "capture") return "INSYT Capture";
  if (workspace === "discovery") return "INSYT Discovery";
  if (workspace === "summaries") return "INSYT Summaries";
  if (workspace === "development") return "INSYT Development";

  return workspace || "Workspace";
}

function formatHours(value: number) {
  return Number(value || 0).toFixed(2);
}

function formatWeekEnding(value: string) {
  if (!value) return "—";

  const date = new Date(`${value}T00:00:00`);

  return date.toLocaleDateString("en-US", {
    month: "2-digit",
    day: "2-digit",
    year: "numeric",
  });
}

function getDefaultWeekEnding(row: ProjectHoursRow) {
  return row.weekly_totals?.[0]?.week_ending || "";
}

function ProjectHoursPageContent() {
  const searchParams = useSearchParams();

  const workspace =
    searchParams.get("workspace") || "capture";

  const [rows, setRows] = useState<ProjectHoursRow[]>([]);
  const [message, setMessage] = useState("");
  const [expandedRows, setExpandedRows] =
    useState<Record<string, boolean>>({});
  const [selectedWeekByProject, setSelectedWeekByProject] =
    useState<Record<string, string>>({});

  function getRowKey(row: ProjectHoursRow) {
    return `${row.client_id}/${row.project_id}`;
  }

  function loadProjectHours() {
    setMessage("");

    apiGet(
      `/api/timesheet/project-hours-summary?workspace=${encodeURIComponent(
        workspace
      )}`
    )
      .then((response: any) => {
        const incomingRows = response.rows || [];

        setRows(incomingRows);

        setSelectedWeekByProject((current) => {
          const next = { ...current };

          incomingRows.forEach((row: ProjectHoursRow) => {
            const rowKey = getRowKey(row);

            if (!next[rowKey]) {
              next[rowKey] = getDefaultWeekEnding(row);
            }
          });

          return next;
        });
      })
      .catch((error) => {
        console.error(error);
        setMessage("Failed to load project hours.");
      });
  }

  useEffect(() => {
    loadProjectHours();
  }, [workspace]);

  return (
    <AppShell>
      <PageContainer>
        <PageHeader
          title="Project Hours"
          subtitle={`${prettyWorkspace(
            workspace
          )} aggregate project-level review hours.`}
        />

        {message && (
          <p className="mb-6 text-sm text-sky-400">
            {message}
          </p>
        )}

        <ContentCard title="Project Hour Totals">
          <div className="mb-5 flex justify-end">
            <Button onClick={loadProjectHours}>
              Refresh
            </Button>
          </div>

          <div className="overflow-auto rounded-xl border border-slate-800">
            <table className="w-full text-sm">
              <thead className="bg-slate-900 text-slate-400">
                <tr>
                  <th className="p-3 text-left">Client</th>
                  <th className="p-3 text-left">Project</th>
                  <th className="p-3 text-right">Project Total</th>
                  <th className="p-3 text-right">1L Project Total</th>
                  <th className="p-3 text-right">QC Project Total</th>
                  <th className="p-3 text-right">TL Project Total</th>
                  <th className="p-3 text-right">RM Project Total</th>
                  <th className="p-3 text-right">Details</th>
                </tr>
              </thead>

              <tbody>
                {rows.map((row) => {
                  const rowKey = getRowKey(row);
                  const isExpanded = expandedRows[rowKey] || false;

                  const selectedWeekEnding =
                    selectedWeekByProject[rowKey] ||
                    getDefaultWeekEnding(row);

                  const selectedWeeklyTotal =
                    (row.weekly_totals || []).find(
                      (item) =>
                        item.week_ending === selectedWeekEnding
                    );

                  return (
                    <Fragment key={rowKey}>
                      <tr
                        key={rowKey}
                        className="border-t border-slate-800"
                      >
                        <td className="p-3 text-white">
                          {row.client_id}
                        </td>

                        <td className="p-3 text-white">
                          {row.project_id}
                        </td>

                        <td className="p-3 text-right font-semibold text-white">
                          {formatHours(row.project_total)}
                        </td>

                        <td className="p-3 text-right text-slate-300">
                          {formatHours(row.one_l_project_total)}
                        </td>

                        <td className="p-3 text-right text-slate-300">
                          {formatHours(row.qc_project_total)}
                        </td>

                        <td className="p-3 text-right text-slate-300">
                          {formatHours(row.tl_project_total)}
                        </td>

                        <td className="p-3 text-right text-slate-300">
                          {formatHours(row.rm_project_total)}
                        </td>

                        <td className="p-3 text-right">
                          <Button
                            variant="secondary"
                            onClick={() =>
                              setExpandedRows((current) => ({
                                ...current,
                                [rowKey]: !isExpanded,
                              }))
                            }
                          >
                            {isExpanded ? "Hide" : "Expand"}
                          </Button>
                        </td>
                      </tr>

                      {isExpanded && (
                        <tr
                          key={`${rowKey}-expanded`}
                          className="border-t border-slate-800 bg-slate-950"
                        >
                          <td colSpan={8} className="p-4">
                            <div className="rounded-2xl border border-slate-800 bg-slate-900 p-5">
                              <div className="mb-5 flex flex-wrap items-center justify-between gap-4">
                                <div>
                                  <h3 className="text-base font-semibold text-white">
                                    Weekly Project Hours
                                  </h3>

                                  <p className="mt-1 text-xs text-slate-400">
                                    Select a week ending to view aggregate weekly totals.
                                  </p>
                                </div>

                                <div className="min-w-[260px]">
                                  <label className="mb-2 block text-xs text-slate-400">
                                    Week Ending
                                  </label>

                                  <select
                                    value={selectedWeekEnding}
                                    onChange={(event) =>
                                      setSelectedWeekByProject(
                                        (current) => ({
                                          ...current,
                                          [rowKey]: event.target.value,
                                        })
                                      )
                                    }
                                    className="w-full rounded-xl border border-slate-700 bg-slate-950 px-4 py-3 text-sm text-white outline-none focus:border-sky-500"
                                  >
                                    {(row.weekly_totals || []).map(
                                      (week) => (
                                        <option
                                          key={week.week_ending}
                                          value={week.week_ending}
                                        >
                                          Week Ending{" "}
                                          {formatWeekEnding(
                                            week.week_ending
                                          )}
                                        </option>
                                      )
                                    )}

                                    {(row.weekly_totals || []).length ===
                                      0 && (
                                      <option value="">
                                        No weekly hours
                                      </option>
                                    )}
                                  </select>
                                </div>
                              </div>

                              <div className="overflow-auto rounded-xl border border-slate-800">
                                <table className="w-full text-sm">
                                  <thead className="bg-slate-950 text-slate-400">
                                    <tr>
                                      <th className="p-3 text-left">
                                        Week Ending
                                      </th>
                                      <th className="p-3 text-right">
                                        Project Weekly Total
                                      </th>
                                      <th className="p-3 text-right">
                                        1L Weekly Total
                                      </th>
                                      <th className="p-3 text-right">
                                        QC Weekly Total
                                      </th>
                                      <th className="p-3 text-right">
                                        TL Weekly Total
                                      </th>
                                      <th className="p-3 text-right">
                                        RM Weekly Total
                                      </th>
                                    </tr>
                                  </thead>

                                  <tbody>
                                    {selectedWeeklyTotal ? (
                                      <tr className="border-t border-slate-800">
                                        <td className="p-3 text-white">
                                          {formatWeekEnding(
                                            selectedWeeklyTotal.week_ending
                                          )}
                                        </td>

                                        <td className="p-3 text-right font-semibold text-white">
                                          {formatHours(
                                            selectedWeeklyTotal.project_weekly_total
                                          )}
                                        </td>

                                        <td className="p-3 text-right text-slate-300">
                                          {formatHours(
                                            selectedWeeklyTotal.one_l_weekly_total
                                          )}
                                        </td>

                                        <td className="p-3 text-right text-slate-300">
                                          {formatHours(
                                            selectedWeeklyTotal.qc_weekly_total
                                          )}
                                        </td>

                                        <td className="p-3 text-right text-slate-300">
                                          {formatHours(
                                            selectedWeeklyTotal.tl_weekly_total
                                          )}
                                        </td>

                                        <td className="p-3 text-right text-slate-300">
                                          {formatHours(
                                            selectedWeeklyTotal.rm_weekly_total
                                          )}
                                        </td>
                                      </tr>
                                    ) : (
                                      <tr>
                                        <td
                                          colSpan={6}
                                          className="p-6 text-center text-slate-500"
                                        >
                                          No weekly totals found for this project.
                                        </td>
                                      </tr>
                                    )}
                                  </tbody>
                                </table>
                              </div>
                            </div>
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  );
                })}

                {rows.length === 0 && (
                  <tr>
                    <td
                      colSpan={8}
                      className="p-6 text-center text-slate-500"
                    >
                      No project hours found.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </ContentCard>
      </PageContainer>
    </AppShell>
  );
}

export default function ProjectHoursPage() {
  return (
    <Suspense fallback={<div>Loading project hours...</div>}>
      <ProjectHoursPageContent />
    </Suspense>
  );
}