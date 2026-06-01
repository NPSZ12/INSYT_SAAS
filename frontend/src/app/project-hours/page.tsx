"use client";

import React, { useEffect, useState } from "react";

import AppShell from "../../components/AppShell";
import PageContainer from "../../components/PageContainer";
import PageHeader from "../../components/PageHeader";
import ContentCard from "../../components/ContentCard";
import { apiGet } from "../../lib/api";

type HoursRow = {
  client: string;
  workspace: string;
  project: string;
  role: string;
  total_hours: number;
};

function prettyWorkspace(workspace: string) {
  if (workspace === "capture") return "INSYT Capture";
  if (workspace === "discovery") return "INSYT Discovery";
  if (workspace === "summaries") return "INSYT Summaries";
  if (workspace === "development") return "INSYT Development";

  return workspace || "Unknown Workspace";
}

export default function ProjectHoursPage() {
  const [rows, setRows] = useState<HoursRow[]>([]);
  const [expandedClients, setExpandedClients] = useState<Record<string, boolean>>({});
  const [expandedWorkspaces, setExpandedWorkspaces] = useState<Record<string, boolean>>({});
  const [expandedProjects, setExpandedProjects] = useState<Record<string, boolean>>({});
  const [message, setMessage] = useState("");

  useEffect(() => {
    apiGet("/api/admin/project-hours-overview")
      .then((response: any) => {
        setRows(response.rows || []);
      })
      .catch((error) => {
        console.error(error);
        setMessage("Failed to load project hours.");
      });
  }, []);

  const grouped = rows.reduce((acc: any, row) => {
    acc[row.client] ??= {};
    acc[row.client][row.workspace] ??= {};
    acc[row.client][row.workspace][row.project] ??= [];
    acc[row.client][row.workspace][row.project].push(row);
    return acc;
  }, {});

  const clients = Object.keys(grouped).sort();

  return (
    <AppShell>
      <PageContainer>
        <PageHeader
          title="Project Hours"
          subtitle="Total project hours by client, workspace, project, and role."
        />

        {message && (
          <p className="mb-6 text-sm text-red-400">
            {message}
          </p>
        )}

        <ContentCard title="Project Hours Overview">
          <div className="overflow-auto rounded-xl border border-slate-800">
            <table className="w-full text-sm">
              <thead className="bg-slate-900 text-slate-400 sticky top-0 z-20">
                <tr>
                  <th className="p-3 text-left">Client</th>
                  <th className="p-3 text-left">Workspace</th>
                  <th className="p-3 text-left">Project</th>
                  <th className="p-3 text-left">Role</th>
                  <th className="p-3 text-right">Total Hours</th>
                </tr>
              </thead>

              <tbody>
                {clients.map((client) => {
                  const clientOpen = Boolean(expandedClients[client]);
                  const workspaces = Object.keys(grouped[client]).sort();

                  return (
                    <React.Fragment key={client}>
                      <tr className="border-t border-slate-800 bg-slate-950/80">
                        <td className="p-3 text-white font-semibold">
                          <button
                            type="button"
                            onClick={() =>
                              setExpandedClients((current) => ({
                                ...current,
                                [client]: !current[client],
                              }))
                            }
                            className="hover:text-sky-300"
                          >
                            {clientOpen ? "▼" : "▶"} {client}
                          </button>
                        </td>

                        <td className="p-3 text-slate-500">
                          {workspaces.length} workspace(s)
                        </td>
                        <td className="p-3 text-slate-500">—</td>
                        <td className="p-3 text-slate-500">—</td>
                        <td className="p-3 text-right text-slate-500">—</td>
                      </tr>

                      {clientOpen &&
                        workspaces.map((workspace) => {
                          const workspaceKey = `${client}/${workspace}`;
                          const workspaceOpen = Boolean(
                            expandedWorkspaces[workspaceKey]
                          );
                          const projects = Object.keys(
                            grouped[client][workspace]
                          ).sort();

                          return (
                            <React.Fragment key={workspaceKey}>
                              <tr className="border-t border-slate-800 bg-slate-900/60">
                                <td className="p-3" />
                                <td className="p-3 text-slate-100 font-medium">
                                  <button
                                    type="button"
                                    onClick={() =>
                                      setExpandedWorkspaces((current) => ({
                                        ...current,
                                        [workspaceKey]: !current[workspaceKey],
                                      }))
                                    }
                                    className="hover:text-sky-300"
                                  >
                                    {workspaceOpen ? "▼" : "▶"}{" "}
                                    {prettyWorkspace(workspace)}
                                  </button>
                                </td>
                                <td className="p-3 text-slate-500">
                                  {projects.length} project(s)
                                </td>
                                <td className="p-3 text-slate-500">—</td>
                                <td className="p-3 text-right text-slate-500">—</td>
                              </tr>

                              {workspaceOpen &&
                                projects.map((project) => {
                                  const projectKey = `${client}/${workspace}/${project}`;
                                  const projectOpen = Boolean(
                                    expandedProjects[projectKey]
                                  );
                                  const roleRows =
                                    grouped[client][workspace][project];

                                  const projectTotal = roleRows.reduce(
                                    (sum: number, row: HoursRow) =>
                                      sum + Number(row.total_hours || 0),
                                    0
                                  );

                                  return (
                                    <React.Fragment key={projectKey}>
                                      <tr className="border-t border-slate-800 bg-slate-950/40">
                                        <td className="p-3" />
                                        <td className="p-3" />
                                        <td className="p-3 text-slate-100">
                                          <button
                                            type="button"
                                            onClick={() =>
                                              setExpandedProjects((current) => ({
                                                ...current,
                                                [projectKey]: !current[projectKey],
                                              }))
                                            }
                                            className="hover:text-sky-300"
                                          >
                                            {projectOpen ? "▼" : "▶"}{" "}
                                            {project.replaceAll("_", " ")}
                                          </button>
                                        </td>
                                        <td className="p-3 text-slate-500">
                                          {roleRows.length} role(s)
                                        </td>
                                        <td className="p-3 text-right text-slate-300 font-semibold">
                                          {projectTotal.toFixed(2)}
                                        </td>
                                      </tr>

                                      {projectOpen &&
                                        roleRows.map((roleRow: HoursRow) => (
                                          <tr
                                            key={`${projectKey}/${roleRow.role}`}
                                            className="border-t border-slate-800"
                                          >
                                            <td className="p-3" />
                                            <td className="p-3" />
                                            <td className="p-3" />
                                            <td className="p-3 text-white">
                                              {roleRow.role}
                                            </td>
                                            <td className="p-3 text-right text-slate-300">
                                              {Number(
                                                roleRow.total_hours || 0
                                              ).toFixed(2)}
                                            </td>
                                          </tr>
                                        ))}
                                    </React.Fragment>
                                  );
                                })}
                            </React.Fragment>
                          );
                        })}
                    </React.Fragment>
                  );
                })}

                {clients.length === 0 && (
                  <tr>
                    <td
                      colSpan={5}
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