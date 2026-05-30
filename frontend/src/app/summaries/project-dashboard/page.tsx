"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";

import AppShell from "../../../components/AppShell";
import PageContainer from "../../../components/PageContainer";
import PageHeader from "../../../components/PageHeader";
import ContentCard from "../../../components/ContentCard";

function ProjectDashboardPageContent() {
  const searchParams = useSearchParams();

  const projectId = searchParams.get("project") || "";
  const clientId = searchParams.get("client") || "";

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
  const clientName = clientId
    ? clientId.replaceAll("_", " ")
    : "No client selected";

  return (
    <AppShell>
      <PageContainer>
        <PageHeader
          title={projectName}
          subtitle={
            clientId
              ? `${clientName} • Use the sidebar to access Batches, Review, Captured Entities, Timesheet, and Messaging.`
              : "Use the sidebar to access Batches, Review, Captured Entities, Timesheet, and Messaging."
          }
        />

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <ContentCard title="Project Workspace">
            <p className="text-slate-400">
              This dashboard is the central workspace for the selected project.
              Available workflow areas now appear in the sidebar.
            </p>

            <div className="mt-4 rounded-xl border border-slate-800 bg-slate-950 p-4 text-sm">
              <div className="text-slate-500">Client</div>
              <div className="text-white font-semibold">
                {clientName}
              </div>

              <div className="text-slate-500 mt-3">Project</div>
              <div className="text-white font-semibold">
                {projectName}
              </div>
            </div>
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