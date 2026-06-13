"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";

import AppShell from "./AppShell";
import PageContainer from "./PageContainer";
import PageHeader from "./PageHeader";
import ContentCard from "./ContentCard";
import AzureProcessingCenterPanel from "./processing-center/AzureProcessingCenterPanel";

type ProcessingCenterPageProps = {
  workspace: "capture" | "discovery" | "summaries";
  title?: string;
  subtitle?: string;
};

function getWorkspaceLabel(workspace: string) {
  if (workspace === "capture") return "Capture";
  if (workspace === "discovery") return "Discovery";
  if (workspace === "summaries") return "Summaries";
  return "Workspace";
}

function ProcessingCenterPageContent({
  workspace,
  title,
  subtitle,
}: ProcessingCenterPageProps) {
  const searchParams = useSearchParams();

  const workspaceLabel = getWorkspaceLabel(workspace);

  const clientId =
    searchParams.get("client") ||
    searchParams.get("clientId") ||
    "";

  const projectId =
    searchParams.get("project") ||
    searchParams.get("project_id") ||
    "";

  return (
    <AppShell>
      <PageContainer>
        <PageHeader
          title={title || `${workspaceLabel} Processing Center`}
          subtitle={
            subtitle ||
            `Upload, process, and publish documents through the Azure Processing Center for ${workspaceLabel} review.`
          }
        />

        {!clientId || !projectId ? (
          <ContentCard>
            <div className="text-sm text-red-300">
              Missing client or project in the URL.
            </div>
          </ContentCard>
        ) : null}

        {clientId && projectId ? (
          <AzureProcessingCenterPanel
            workspace={workspace}
            clientId={clientId}
            projectId={projectId}
          />
        ) : null}
      </PageContainer>
    </AppShell>
  );
}

export default function ProcessingCenterPage(props: ProcessingCenterPageProps) {
  return (
    <Suspense
      fallback={
        <AppShell>
          <PageContainer>
            <div className="rounded-2xl border border-slate-800 bg-slate-950/70 p-6 text-slate-300">
              Loading Processing Center...
            </div>
          </PageContainer>
        </AppShell>
      }
    >
      <ProcessingCenterPageContent {...props} />
    </Suspense>
  );
}