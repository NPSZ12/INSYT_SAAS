"use client";

import { Suspense, useEffect, useState } from "react";

import AppShell from "../../../components/AppShell";
import PageContainer from "../../../components/PageContainer";
import PageHeader from "../../../components/PageHeader";
import ContentCard from "../../../components/ContentCard";
import Button from "../../../components/Button";
import { apiGet, apiPost } from "../../../lib/api";

type ClientProjectUser = {
  username: string;
  display_name: string;
  email?: string;
  role: string;
  status: string;
};

type ClientProject = {
  project_id: string;
  users: ClientProjectUser[];
};

type ClientRow = {
  client_name: string;
  projects: ClientProject[];
};

function ClientsPageContent() {
  const [clients, setClients] = useState<ClientRow[]>([]);
  const [expandedClient, setExpandedClient] = useState("");
  const [expandedProject, setExpandedProject] = useState("");
  const [message, setMessage] = useState("");

  function loadClients() {
    apiGet("/api/capture/clients")
      .then((response) => {
        setClients(response.clients || []);
      })
      .catch((error) => {
        console.error(error);
        setClients([]);
        setMessage("Failed to load clients.");
      });
  }

  useEffect(() => {
    loadClients();
  }, []);

  function removeUserFromProject(projectId: string, username: string) {
    const confirmed = window.confirm(
      `Remove ${username} from ${projectId}?`
    );

    if (!confirmed) return;

    apiPost("/api/capture/clients/remove-user", {
      project_id: projectId,
      username,
    })
      .then((response) => {
        setMessage(response.message || "User removed from project.");
        loadClients();
      })
      .catch((error) => {
        console.error(error);
        setMessage("Failed to remove user from project.");
      });
  }

  return (
    <AppShell>
      <PageContainer>
        <PageHeader
          title="Clients"
          subtitle="View clients, assigned projects, and review team access."
        />

        {message && (
          <p className="text-sm text-sky-400 mb-6">
            {message}
          </p>
        )}

        <ContentCard title="Client Project Access">
          <div className="bg-slate-950 border border-slate-800 rounded-xl overflow-auto max-h-[72vh]">
            <table className="w-full text-sm table-auto">
              <thead className="bg-slate-900 text-slate-400 sticky top-0 z-20">
                <tr>
                  <th className="p-3 text-left">Client</th>
                  <th className="p-3 text-left">Projects</th>
                </tr>
              </thead>

              <tbody>
                {clients
                  .slice()
                  .sort((a, b) =>
                    String(a.client_name || "Unknown Client").localeCompare(
                      String(b.client_name || "Unknown Client")
                    )
                  )
                  .map((client, index) => {
                    const clientName =
                      client.client_name || "Unknown Client";

                    return (
                      <tr
                        key={`${clientName}-${index}`}
                        className="border-t border-slate-800 align-top"
                      >
                        <td className="p-3 text-white w-1/3">
                          <button
                            type="button"
                            onClick={() => {
                              setExpandedClient(
                                expandedClient === clientName
                                  ? ""
                                  : clientName
                              );

                              setExpandedProject("");
                            }}
                            className="insyt-project text-sky-400 hover:text-sky-300 font-semibold"
                          >
                            {clientName}
                          </button>
                        </td>

                        <td className="p-3">
                          {expandedClient !== clientName ? (
                            <span className="text-slate-400">
                              {client.projects.length} project(s)
                            </span>
                          ) : (
                            <div className="space-y-3">
                              {client.projects.map((project) => (
                                <div
                                  key={project.project_id}
                                  className="bg-slate-900 border border-slate-800 rounded-xl"
                                >
                                  <button
                                    type="button"
                                    onClick={() =>
                                      setExpandedProject(
                                        expandedProject === project.project_id
                                          ? ""
                                          : project.project_id
                                      )
                                    }
                                    className="w-full text-left p-4 flex justify-between items-center"
                                  >
                                    <span className="insyt-project text-white font-semibold">
                                      {project.project_id.replaceAll("_", " ")}
                                    </span>

                                    <span className="text-xs text-slate-400">
                                      {project.users.length} assigned user(s)
                                    </span>
                                  </button>

                                  {expandedProject === project.project_id && (
                                    <div className="border-t border-slate-800 overflow-auto">
                                      <table className="w-full text-xs">
                                        <thead className="bg-slate-950 text-slate-400">
                                          <tr>
                                            <th className="p-3 text-left">Name</th>
                                            <th className="p-3 text-left">Email</th>
                                            <th className="p-3 text-left">Level</th>
                                            <th className="p-3 text-left">Status</th>
                                            <th className="p-3 text-left">Action</th>
                                          </tr>
                                        </thead>

                                        <tbody>
                                          {project.users.map((user) => (
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
                                                {user.status}
                                              </td>

                                              <td className="p-3">
                                                <Button
                                                  variant="secondary"
                                                  onClick={() =>
                                                    removeUserFromProject(
                                                      project.project_id,
                                                      user.username
                                                    )
                                                  }
                                                >
                                                  Remove
                                                </Button>
                                              </td>
                                            </tr>
                                          ))}
                                        </tbody>
                                      </table>
                                    </div>
                                  )}
                                </div>
                              ))}
                            </div>
                          )}
                        </td>
                      </tr>
                    );
                  })}
              </tbody>
            </table>
          </div>
        </ContentCard>
      </PageContainer>
    </AppShell>
  );
}


export default function ClientsPage() {
  return (
    <Suspense fallback={<div>Loading...</div>}>
      <ClientsPageContent />
    </Suspense>
  );
}






