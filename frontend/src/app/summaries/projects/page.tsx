"use client";

import { useEffect, useState } from "react";
import AppShell from "../../../components/AppShell";
import PageHeader from "../../../components/PageHeader";
import PageContainer from "../../../components/PageContainer";
import SectionGrid from "../../../components/SectionGrid";
import ProjectCard from "../../../components/ProjectCard";
import { apiGet } from "../../../lib/api";
import type { Project } from "../../../types";
import { useRouter } from "next/navigation";

export default function ProjectsPage() {

  const router = useRouter();
  const [projects, setProjects] = useState<Project[]>([]);

  useEffect(() => {
    apiGet("/api/summaries/projects/")
      .then((response) => {
        console.log("AZURE PROJECTS RESPONSE:", response);

        const azureProjects = response.projects ?? [];

        setProjects(
          azureProjects.map((projectId: string) => ({
            name: projectId.replaceAll("_", " "),
            client: "Azure Blob Project",
            status: "Active",
            progress: 0,
            openHref: `/summaries/project-dashboard?project=${projectId}`,
          }))
        );
      })
      .catch((error) => {
        console.error("Failed to load Azure projects:", error);
        setProjects([]);
      });
  }, []);

  return (
    <AppShell>
      <PageContainer>

        <PageHeader
          title="Projects"
          subtitle="Select an active INSYT review project."
        />

        <SectionGrid cols={3}>
          {(projects || []).map((project) => (
            <ProjectCard
              key={project.name}
              name={project.name}
              client={project.client}
              status={project.status}
              docs={project.docs}
              qc={project.qc}
              onOpen={() => {
                const projectId = project.name.replaceAll(" ", "_");

                localStorage.setItem("insyt_selected_project", projectId);

                router.push(`/summaries/project-dashboard?project=${projectId}`);
              }}
            />
          ))}
        </SectionGrid>

      </PageContainer>
    </AppShell>
  );
}











