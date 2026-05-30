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

export default function ProjectsPage() {
  const router = useRouter();

  const [clients, setClients] = useState<string[]>([]);
  const [selectedClient, setSelectedClient] = useState("");
  const [projects, setProjects] = useState<Project[]>([]);

  function loadClients() {
    apiGet("/api/discovery/clients")
      .then((response) => {
        setClients(response.clients || []);
      })
      .catch((error) => {
        console.error("Failed to load clients:", error);
        setClients([]);
      });
  }

  function loadProjects(client: string) {
    if (!client) {
      setProjects([]);
      return;
    }

    apiGet(
      `/api/discovery/clients/${encodeURIComponent(client)}/projects`
    )
      .then((response) => {
        const projectList = response.projects || [];

        setProjects(
          projectList.map((projectId: string) => ({
            name: projectId.replaceAll("_", " "),
            client,
            status: "Active",
            progress: 0,
            openHref: `/discovery/project-dashboard?client=${encodeURIComponent(
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
    loadClients();
  }, []);

  useEffect(() => {
    if (!selectedClient) {
      setProjects([]);
      return;
    }

    loadProjects(selectedClient);
  }, [selectedClient]);

  return (
    <AppShell>
      <PageContainer>
        <PageHeader
          title="Projects"
          subtitle="Select a client and active INSYT Discovery project."
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
          ) : (
            <SectionGrid cols={3}>
              {(projects || []).map((project) => (
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
                      `/discovery/project-dashboard?client=${encodeURIComponent(
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