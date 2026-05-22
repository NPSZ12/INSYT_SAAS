"use client";

import { useRouter } from "next/navigation";

import AppShell from "../../components/AppShell";
import PageContainer from "../../components/PageContainer";
import PageHeader from "../../components/PageHeader";
import ContentCard from "../../components/ContentCard";
import Button from "../../components/Button";

export default function summariesPage() {
  const router = useRouter();

  return (
    <AppShell>
      <PageContainer>
        <PageHeader
          title="INSYT summaries"
          subtitle="Project intake, batching, review, entity summaries, and export workflows."
        />

        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
          <ContentCard title="Project Dashboard">
            <p className="text-slate-400 mb-4">
              Open project-level dashboards, review status, batches, and workflow activity.
            </p>
            <Button onClick={() => router.push("/project-dashboard")}>
              Open Dashboard
            </Button>
          </ContentCard>

          <ContentCard title="Batches">
            <p className="text-slate-400 mb-4">
              Create, manage, check out, and complete review batches.
            </p>
            <Button onClick={() => router.push("/batches")}>
              Open Batches
            </Button>
          </ContentCard>

          <ContentCard title="Review">
            <p className="text-slate-400 mb-4">
              Launch the document review workspace.
            </p>
            <Button onClick={() => router.push("/review")}>
              Open Review
            </Button>
          </ContentCard>

          <ContentCard title="summariesd Entities">
            <p className="text-slate-400 mb-4">
              View extracted/summariesd entities and quality-control outputs.
            </p>
            <Button onClick={() => router.push("/summariesd-entities")}>
              Open Entities
            </Button>
          </ContentCard>

          <ContentCard title="Files">
            <p className="text-slate-400 mb-4">
              Browse project files, uploads, text, natives, and outputs.
            </p>
            <Button onClick={() => router.push("/files")}>
              Open Files
            </Button>
          </ContentCard>

          <ContentCard title="User Access">
            <p className="text-slate-400 mb-4">
              Manage users, roles, launch access, project access, and passwords.
            </p>
            <Button onClick={() => router.push("/user-access")}>
              Open User Access
            </Button>
          </ContentCard>
        </div>
      </PageContainer>
    </AppShell>
  );
}











