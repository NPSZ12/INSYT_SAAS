"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";

import AppShell from "../../components/AppShell";
import PageContainer from "../../components/PageContainer";
import PageHeader from "../../components/PageHeader";
import ContentCard from "../../components/ContentCard";
import Button from "../../components/Button";
import { apiGet, apiPost } from "../../lib/api";

type ProjectUser = {
  username: string;
  display_name: string;
  email: string;
  role: string;
  status: string;
  auth_provider: string;
};

function prettyWorkspace(workspace: string) {
  if (workspace === "capture") return "INSYT Capture";
  if (workspace === "discovery") return "INSYT Discovery";
  if (workspace === "summaries") return "INSYT Summaries";
  if (workspace === "development") return "INSYT Development";

  return workspace || "Workspace";
}

function ProjectUsersPageContent() {
  const searchParams = useSearchParams();

  const workspace = searchParams.get("workspace") || "";
  const client = searchParams.get("client") || "";
  const project = searchParams.get("project") || "";

  const [users, setUsers] = useState<ProjectUser[]>([]);
  const [message, setMessage] = useState("");

  function loadUsers() {
    if (!workspace || !client || !project) {
      setMessage("Missing workspace, client, or project.");
      return;
    }

    const query = new URLSearchParams({
      workspace,
      client,
      project,
    });

    apiGet(`/api/admin/project-users?${query.toString()}`)
      .then((response: any) => {
        setUsers(response.users || []);
      })
      .catch((error) => {
        console.error(error);
        setMessage("Failed to load project review team.");
      });
  }

  useEffect(() => {
    loadUsers();
  }, [workspace, client, project]);

  function updateUserStatus(
    user: ProjectUser,
    nextStatus: "Active" | "Inactive"
  ) {
    apiPost("/api/admin/users/status", {
      username: user.username,
      status: nextStatus,
    })
      .then(() => {
        setMessage(`${user.display_name} set to ${nextStatus}.`);
        loadUsers();
      })
      .catch((error) => {
        console.error(error);
        setMessage("Failed to update user status.");
      });
  }

  return (
    <AppShell>
      <PageContainer>
        <PageHeader
          title="Review Team"
          subtitle={`${prettyWorkspace(workspace)} • ${client || "Client"} • ${
            project ? project.replaceAll("_", " ") : "Project"
          }`}
        />

        {message && (
          <p className="mb-6 text-sm text-sky-400">
            {message}
          </p>
        )}

        <ContentCard title="Assigned Project Users">
          <div className="overflow-auto rounded-xl border border-slate-800">
            <table className="w-full text-sm">
              <thead className="bg-slate-900 text-slate-400">
                <tr>
                  <th className="p-3 text-left">User</th>
                  <th className="p-3 text-left">Email</th>
                  <th className="p-3 text-left">Role</th>
                  <th className="p-3 text-left">Authentication</th>
                  <th className="p-3 text-left">Status</th>
                  <th className="p-3 text-left">Access</th>
                </tr>
              </thead>

              <tbody>
                {users.map((user) => (
                  <tr
                    key={user.username}
                    className="border-t border-slate-800"
                  >
                    <td className="p-3 text-white">
                      {user.display_name || user.username}
                    </td>

                    <td className="p-3 text-slate-300">
                      {user.email || "—"}
                    </td>

                    <td className="p-3 text-slate-300">
                      {user.role}
                    </td>

                    <td className="p-3 text-slate-300">
                      {user.auth_provider === "entra"
                        ? "Microsoft Entra"
                        : "Local INSYT"}
                    </td>

                    <td className="p-3">
                      <span
                        className={
                          user.status === "Active"
                            ? "rounded-full bg-emerald-500/10 px-3 py-1 text-xs text-emerald-300"
                            : "rounded-full bg-red-500/10 px-3 py-1 text-xs text-red-300"
                        }
                      >
                        {user.status}
                      </span>
                    </td>

                    <td className="p-3">
                      <Button
                        variant={
                          user.status === "Active"
                            ? "danger"
                            : "secondary"
                        }
                        onClick={() =>
                          updateUserStatus(
                            user,
                            user.status === "Active"
                              ? "Inactive"
                              : "Active"
                          )
                        }
                      >
                        {user.status === "Active"
                          ? "Set Inactive"
                          : "Set Active"}
                      </Button>
                    </td>
                  </tr>
                ))}

                {users.length === 0 && (
                  <tr>
                    <td
                      colSpan={6}
                      className="p-6 text-center text-slate-500"
                    >
                      No users assigned to this project.
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

export default function ProjectUsersPage() {
  return (
    <Suspense fallback={<div>Loading review team...</div>}>
      <ProjectUsersPageContent />
    </Suspense>
  );
}