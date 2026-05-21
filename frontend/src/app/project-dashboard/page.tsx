"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";

import AppShell from "../../components/AppShell";
import PageContainer from "../../components/PageContainer";
import PageHeader from "../../components/PageHeader";
import ContentCard from "../../components/ContentCard";

function ProjectDashboardPageContent() {
  const searchParams = useSearchParams();
  const projectId = searchParams.get("project");

  if (!projectId) {
    return (
      <AppShell>
        <PageContainer>
          <PageHeader
            title="No Project Selected"
            subtitle="Please return to Projects and select a project."
          />
        </PageContainer>
      </AppShell>
    );
  }

  const projectName = projectId.replaceAll("_", " ");

  return (
    <AppShell>
      <PageContainer>
        <PageHeader
          title={projectName}
          subtitle="Use the sidebar to access Batches, Review, Captured Entities, Timesheet, and Messaging."
        />

        <div className="grid grid-cols-2 gap-6">
          <ContentCard title="Project Workspace">
            <p className="text-slate-400">
              This dashboard is the central workspace for the selected project.
              Available workflow areas now appear in the sidebar.
            </p>
          </ContentCard>

          <ContentCard title="Reviewer Workflow">
            <p className="text-slate-400">
              Select Batches to check out work. Review requires a selected batch.
              Captured Entities will show only your captures for your active batch.
            </p>
          </ContentCard>
        </div>
      </PageContainer>
    </AppShell>
  );
}

export default function ProjectDashboardPage() {
  return (
    <Suspense fallback={<div>Loading project dashboard...</div>}>
      <ProjectDashboardPageContent />
    </Suspense>
  );
}








