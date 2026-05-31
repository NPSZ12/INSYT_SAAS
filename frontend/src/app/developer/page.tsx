"use client";

import AppShell from "../../components/AppShell";
import PageContainer from "../../components/PageContainer";
import PageHeader from "../../components/PageHeader";
import ContentCard from "../../components/ContentCard";

export default function DeveloperPage() {
  return (
    <AppShell>
      <PageContainer>
        <PageHeader
          title="INSYT Developer"
          subtitle="INSYT platform administration and development tools."
        />

        <ContentCard title="INSYT Admin Only">
          <p className="text-slate-400">
            Access Restricted.
          </p>
        </ContentCard>
      </PageContainer>
    </AppShell>
  );
}