"use client";

import React, { Suspense, useEffect, useState } from "react";

import AppShell from "../../components/AppShell";
import PageContainer from "../../components/PageContainer";
import PageHeader from "../../components/PageHeader";
import ContentCard from "../../components/ContentCard";
import Button from "../../components/Button";
import { apiGet, apiPost } from "../../lib/api";

type StoredUser = {
  username: string;
  display_name: string;
  role: string;
};

type Reviewer = {
  username: string;
  display_name: string;
  email: string;
  role: string;
  status: string;
  auth_provider: string;
};

type ProjectNode = {
  project: string;
  reviewers: Reviewer[];
};

type WorkspaceNode = {
  workspace: string;
  projects: ProjectNode[];
};

type ClientNode = {
  client: string;
  workspaces: WorkspaceNode[];
};

const allowedRoles = ["INSYT Admin", "Admin", "RM"];

function ClientsPageContent() {
  const [user, setUser] = useState<StoredUser | null>(null);
  const [clients, setClients] = useState<ClientNode[]>([]);
  const [expandedClients, setExpandedClients] = useState<
    Record<string, boolean>
  >({});
  const [expandedWorkspaces, setExpandedWorkspaces] = useState<
    Record<string, boolean>
  >({});
  const [expandedProjects, setExpandedProjects] = useState<
    Record<string, boolean>
  >({});
  const [message, setMessage] = useState("");

  useEffect(() => {
    const storedUser = localStorage.getItem("insyt_user");

    if (storedUser) {
      setUser(JSON.parse(storedUser));
    }
  }, []);

  useEffect(() => {
    if (user && allowedRoles.includes(user.role)) {
      loadClients();
    }
  }, [user]);

  function loadClients() {
    apiGet("/api/admin/clients-overview")
      .then((response: any) => {
        setClients(response.clients || []);
      })
      .catch((error) => {
        console.error(error);
        setMessage("Failed to load client overview.");
      });
  }

  function toggleClient(client: string) {
    setExpandedClients((current) => ({
      ...current,
      [client]: !current[client],
    }));
  }

  function toggleWorkspace(client: string, workspace: string) {
    const key = `${client}/${workspace}`;

    setExpandedWorkspaces((current) => ({
      ...current,
      [key]: !current[key],
    }));
  }

  function toggleProject(
    client: string,
    workspace: string,
    project: string
  ) {
    const key = `${client}/${workspace}/${project}`;

    setExpandedProjects((current) => ({
      ...current,
      [key]: !current[key],
    }));
  }

  function updateReviewerStatus(
    reviewer: Reviewer,
    nextStatus: "Active" | "Inactive"
  ) {
    setMessage("");

    apiPost("/api/admin/users/status", {
      username: reviewer.username,
      status: nextStatus,
    })
      .then(() => {
        setMessage(
          `${reviewer.display_name} set to ${nextStatus}.`
        );
        loadClients();
      })
      .catch((error) => {
        console.error(error);
        setMessage("Failed to update reviewer status.");
      });
  }

  function prettyWorkspace(workspace: string) {
    if (workspace === "capture") return "INSYT Capture";
    if (workspace === "discovery") return "INSYT Discovery";
    if (workspace === "summaries") return "INSYT Summaries";
    if (workspace === "development") return "INSYT Development";

    return workspace || "Unknown Workspace";
  }

  if (!user) {
    return (
      <AppShell>
        <PageContainer>
          <p className="text-slate-400">Loading clients...</p>
        </PageContainer>
      </AppShell>
    );
  }

  if (!allowedRoles.includes(user.role)) {
    return (
      <AppShell>
        <PageContainer>
          <PageHeader
            title="Clients"
            subtitle="Client, project, user, status, and access overview."
          />

          <ContentCard title="Access Denied">
            <p className="text-slate-400">
              You do not have permission to view Client Administration.
            </p>
          </ContentCard>
        </PageContainer>
      </AppShell>
    );
  }

  return (
    <AppShell>
      <PageContainer>
        <PageHeader
          title="Clients"
          subtitle="Client, workspace, project, reviewer, and access status overview."
        />

        {message && (
          <p className="mb-6 text-sm text-sky-400">
            {message}
          </p>
        )}

        <ContentCard title="Client Access Overview">
          <div className="overflow-auto rounded-xl border border-slate-800">
            <table className="w-full text-sm">
              <thead className="bg-slate-900 text-slate-400 sticky top-0 z-20">
                <tr>
                  <th className="p-3 text-left">Client</th>
                  <th className="p-3 text-left">Workspace</th>
                  <th className="p-3 text-left">Project</th>
                  <th className="p-3 text-left">Assigned Reviewer</th>
                  <th className="p-3 text-left">Role</th>
                  <th className="p-3 text-left">Auth</th>
                  <th className="p-3 text-left">Status</th>
                  <th className="p-3 text-left">Access</th>
                </tr>
              </thead>

              <tbody>
                {clients.map((clientNode) => {
                  const clientOpen =
                    Boolean(expandedClients[clientNode.client]);

                  return (
                    <React.Fragment key={clientNode.client}>
                      <tr
                        key={clientNode.client}
                        className="border-t border-slate-800 bg-slate-950/80"
                      >
                        <td className="p-3 text-white font-semibold">
                          <button
                            type="button"
                            onClick={() =>
                              toggleClient(clientNode.client)
                            }
                            className="text-left hover:text-sky-300"
                          >
                            {clientOpen ? "▼" : "▶"}{" "}
                            {clientNode.client}
                          </button>
                        </td>

                        <td className="p-3 text-slate-500">
                          {clientNode.workspaces.length} workspace(s)
                        </td>

                        <td className="p-3 text-slate-500">—</td>
                        <td className="p-3 text-slate-500">—</td>
                        <td className="p-3 text-slate-500">—</td>
                        <td className="p-3 text-slate-500">—</td>
                        <td className="p-3 text-slate-500">—</td>
                        <td className="p-3 text-slate-500">—</td>
                      </tr>

                      {clientOpen &&
                        clientNode.workspaces.map((workspaceNode) => {
                          const workspaceKey = `${clientNode.client}/${workspaceNode.workspace}`;
                          const workspaceOpen =
                            Boolean(expandedWorkspaces[workspaceKey]);

                          return (
                            <React.Fragment key={workspaceKey}>
                              <tr
                                key={workspaceKey}
                                className="border-t border-slate-800 bg-slate-900/60"
                              >
                                <td className="p-3" />

                                <td className="p-3 text-slate-100 font-medium">
                                  <button
                                    type="button"
                                    onClick={() =>
                                      toggleWorkspace(
                                        clientNode.client,
                                        workspaceNode.workspace
                                      )
                                    }
                                    className="text-left hover:text-sky-300"
                                  >
                                    {workspaceOpen ? "▼" : "▶"}{" "}
                                    {prettyWorkspace(
                                      workspaceNode.workspace
                                    )}
                                  </button>
                                </td>

                                <td className="p-3 text-slate-500">
                                  {workspaceNode.projects.length} project(s)
                                </td>

                                <td className="p-3 text-slate-500">—</td>
                                <td className="p-3 text-slate-500">—</td>
                                <td className="p-3 text-slate-500">—</td>
                                <td className="p-3 text-slate-500">—</td>
                                <td className="p-3 text-slate-500">—</td>
                              </tr>

                              {workspaceOpen &&
                                workspaceNode.projects.map((projectNode) => {
                                  const projectKey = `${clientNode.client}/${workspaceNode.workspace}/${projectNode.project}`;
                                  const projectOpen =
                                    Boolean(expandedProjects[projectKey]);

                                  return (
                                    <React.Fragment key={projectKey}>
                                      <tr
                                        key={projectKey}
                                        className="border-t border-slate-800 bg-slate-950/40"
                                      >
                                        <td className="p-3" />
                                        <td className="p-3" />

                                        <td className="p-3 text-slate-100">
                                          <button
                                            type="button"
                                            onClick={() =>
                                              toggleProject(
                                                clientNode.client,
                                                workspaceNode.workspace,
                                                projectNode.project
                                              )
                                            }
                                            className="text-left hover:text-sky-300"
                                          >
                                            {projectOpen ? "▼" : "▶"}{" "}
                                            {projectNode.project.replaceAll(
                                              "_",
                                              " "
                                            )}
                                          </button>
                                        </td>

                                        <td className="p-3 text-slate-500">
                                          {projectNode.reviewers.length} reviewer(s)
                                        </td>

                                        <td className="p-3 text-slate-500">—</td>
                                        <td className="p-3 text-slate-500">—</td>
                                        <td className="p-3 text-slate-500">—</td>
                                        <td className="p-3 text-slate-500">—</td>
                                      </tr>

                                      {projectOpen &&
                                        projectNode.reviewers.map(
                                          (reviewer) => (
                                            <tr
                                              key={`${projectKey}/${reviewer.username}`}
                                              className="border-t border-slate-800"
                                            >
                                              <td className="p-3" />
                                              <td className="p-3" />
                                              <td className="p-3" />

                                              <td className="p-3 text-white">
                                                <div>
                                                  {reviewer.display_name}
                                                </div>
                                                <div className="text-xs text-slate-500">
                                                  {reviewer.email || reviewer.username}
                                                </div>
                                              </td>

                                              <td className="p-3 text-slate-300">
                                                {reviewer.role}
                                              </td>

                                              <td className="p-3 text-slate-300">
                                                {reviewer.auth_provider === "entra"
                                                  ? "Microsoft Entra"
                                                  : "Local"}
                                              </td>

                                              <td className="p-3">
                                                <span
                                                  className={
                                                    reviewer.status === "Active"
                                                      ? "rounded-full bg-emerald-500/10 px-3 py-1 text-xs text-emerald-300"
                                                      : "rounded-full bg-red-500/10 px-3 py-1 text-xs text-red-300"
                                                  }
                                                >
                                                  {reviewer.status}
                                                </span>
                                              </td>

                                              <td className="p-3">
                                                <Button
                                                  variant={
                                                    reviewer.status === "Active"
                                                      ? "danger"
                                                      : "secondary"
                                                  }
                                                  onClick={() =>
                                                    updateReviewerStatus(
                                                      reviewer,
                                                      reviewer.status === "Active"
                                                        ? "Inactive"
                                                        : "Active"
                                                    )
                                                  }
                                                >
                                                  {reviewer.status === "Active"
                                                    ? "Set Inactive"
                                                    : "Set Active"}
                                                </Button>
                                              </td>
                                            </tr>
                                          )
                                        )}
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
                      colSpan={8}
                      className="p-6 text-center text-slate-500"
                    >
                      No clients found.
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

export default function Page() {
  return (
    <Suspense fallback={<div>Loading...</div>}>
      <ClientsPageContent />
    </Suspense>
  );
}