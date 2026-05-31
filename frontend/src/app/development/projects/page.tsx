"use client";

import AppShell from "../../../components/AppShell";
import PageContainer from "../../../components/PageContainer";
import PageHeader from "../../../components/PageHeader";
import ContentCard from "../../../components/ContentCard";

export default function DevelopmentProjectsPage() {
  return (
    <AppShell>
      <PageContainer>
        <PageHeader
          title="INSYT Developer"
          subtitle="Future INSYT platform administration and development tools."
        />

        <ContentCard title="INSYT Admin Only">
          <p className="text-slate-400">
            This workspace is reserved for INSYT Admins. Developer tools will be added later.
          </p>
        </ContentCard>
      </PageContainer>
    </AppShell>
  );
}