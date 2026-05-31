"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import AppShell from "../../../components/AppShell";
import PageHeader from "../../../components/PageHeader";
import PageContainer from "../../../components/PageContainer";
import SectionGrid from "../../../components/SectionGrid";
import ProjectCard from "../../../components/ProjectCard";
import ContentCard from "../../../components/ContentCard";
import FormLabel from "../../../components/FormLabel";
import Select from "../../../components/Select";

import { apiGet } from "../../../lib/api";

import type { Project } from "../../../types";

type StoredUser = {
  username: string;
  display_name: string;
  role: string;
  workspace_access?: string[];
  client_access?: string[];
  project_access?: string[];
  permissions?: string[];
};

function isAdminUser(user: StoredUser | null) {
  const role = user?.role?.toLowerCase() || "";

  return (
    role.includes("admin") ||
    role === "rm" ||
    role === "tl" ||
    role === "qc" ||
    role.includes("review manager") ||
    role.includes("team lead")
  );
}

export default function ProjectsPage() {
  const router = useRouter();

  const [user, setUser] = useState<StoredUser | null>(null);
  const [clients, setClients] = useState<string[]>([]);
  const [selectedClient, setSelectedClient] = useState("");
  const [projects, setProjects] = useState<Project[]>([]);
  const [accessDenied, setAccessDenied] = useState(false);

  const isAdmin = isAdminUser(user);

  function userCanAccessWorkspace(currentUser: StoredUser | null) {
    if (isAdminUser(currentUser)) return true;

    const allowedWorkspaces =
      currentUser?.workspace_access || [];

    return allowedWorkspaces.includes("capture");
  }

  function userCanAccessClient(
    currentUser: StoredUser | null,
    client: string
  ) {
    if (isAdminUser(currentUser)) return true;

    const allowedClients =
      currentUser?.client_access || [];

    return allowedClients.includes(client);
  }

  function userCanAccessProject(
    currentUser: StoredUser | null,
    client: string,
    projectId: string
  ) {
    if (isAdminUser(currentUser)) return true;

    const allowedProjects =
      currentUser?.project_access || [];

    return allowedProjects.includes(
      `${client}/${projectId}`
    );
  }

  function loadClients(currentUser: StoredUser | null) {
    if (!userCanAccessWorkspace(currentUser)) {
      setAccessDenied(true);
      setClients([]);
      setProjects([]);
      return;
    }

    setAccessDenied(false);

    apiGet("/api/capture/clients")
      .then((response) => {
        const incomingClients = response.clients || [];

        const visibleClients = isAdminUser(currentUser)
          ? incomingClients
          : incomingClients.filter((client: string) =>
              userCanAccessClient(currentUser, client)
            );

        setClients(visibleClients);

        if (visibleClients.length === 1) {
          setSelectedClient(visibleClients[0]);
        }
      })
      .catch((error) => {
        console.error("Failed to load clients:", error);
        setClients([]);
      });
  }

  function loadProjects(client: string) {
    if (!client || !user) {
      setProjects([]);
      return;
    }

    apiGet(
      `/api/capture/clients/${encodeURIComponent(
        client
      )}/projects`
    )
      .then((response) => {
        const projectList = response.projects || [];

        const visibleProjects = isAdmin
          ? projectList
          : projectList.filter((projectId: string) =>
              userCanAccessProject(user, client, projectId)
            );

        setProjects(
          visibleProjects.map((projectId: string) => ({
            name: projectId.replaceAll("_", " "),
            client,
            status: "Active",
            progress: 0,
            openHref: `/capture/project-dashboard?client=${encodeURIComponent(
              client
            )}&project=${encodeURIComponent(projectId)}`,
          }))
        );
      })
      .catch((error) => {
        console.error("Failed to load projects:", error);
        setProjects([]);
      });
  }

  useEffect(() => {
    const storedUser = localStorage.getItem("insyt_user");

    if (!storedUser) {
      setAccessDenied(true);
      return;
    }

    const parsedUser = JSON.parse(storedUser);

    setUser(parsedUser);
    loadClients(parsedUser);
  }, []);

  useEffect(() => {
    if (!selectedClient) {
      setProjects([]);
      return;
    }

    loadProjects(selectedClient);
  }, [selectedClient, user]);

  if (accessDenied) {
    return (
      <AppShell>
        <PageContainer>
          <PageHeader
            title="Access Restricted"
            subtitle="You do not have access to INSYT Capture projects."
          />

          <ContentCard title="No Access">
            <p className="text-sm text-slate-400">
              Please contact an INSYT administrator if you believe this is incorrect.
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
          title="Projects"
          subtitle="Select an active INSYT Capture review project."
        />

        <ContentCard title="Select Client">
          <div className="max-w-md">
            <FormLabel>Client</FormLabel>

            <Select
              value={selectedClient}
              onChange={setSelectedClient}
            >
              <option value="">Select client...</option>

              {clients.map((client) => (
                <option key={client} value={client}>
                  {client.replaceAll("_", " ")}
                </option>
              ))}
            </Select>
          </div>
        </ContentCard>

        <div className="mt-6">
          {!selectedClient ? (
            <ContentCard title="Projects">
              <p className="text-sm text-slate-400">
                Select a client to load projects.
              </p>
            </ContentCard>
          ) : projects.length === 0 ? (
            <ContentCard title="Projects">
              <p className="text-sm text-slate-400">
                No projects available for this client.
              </p>
            </ContentCard>
          ) : (
            <SectionGrid cols={3}>
              {projects.map((project) => (
                <ProjectCard
                  key={`${selectedClient}-${project.name}`}
                  name={project.name}
                  client={project.client}
                  status={project.status}
                  docs={project.docs}
                  qc={project.qc}
                  onOpen={() => {
                    const projectId =
                      project.name.replaceAll(" ", "_");

                    localStorage.setItem(
                      "insyt_selected_client",
                      selectedClient
                    );

                    localStorage.setItem(
                      "insyt_selected_project",
                      projectId
                    );

                    router.push(
                      `/capture/project-dashboard?client=${encodeURIComponent(
                        selectedClient
                      )}&project=${encodeURIComponent(projectId)}`
                    );
                  }}
                />
              ))}
            </SectionGrid>
          )}
        </div>
      </PageContainer>
    </AppShell>
  );
}