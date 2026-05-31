"use client";

import AppShell from "../../components/AppShell";
import PageContainer from "../../components/PageContainer";
import PageHeader from "../../components/PageHeader";
import ContentCard from "../../components/ContentCard";

export default function DevelopmentPage() {
  return (
    <AppShell>
      <PageContainer>
        <PageHeader
          title="INSYT Developer"
          subtitle="Future INSYT platform administration and development tools."
        />

        <ContentCard title="Coming Soon">
          <div className="py-12 text-center">
            <h2 className="text-2xl font-semibold text-white mb-4">
              INSYT Developer
            </h2>

            <p className="text-slate-400 max-w-2xl mx-auto">
              This workspace is reserved for INSYT platform
              administration, development, system configuration,
              integrations, and future platform tools.
            </p>

            <div className="mt-8 inline-flex rounded-xl border border-sky-500 bg-sky-950/40 px-6 py-3 text-sky-300 font-semibold">
              INSYT Admin Only
            </div>
          </div>
        </ContentCard>
      </PageContainer>
    </AppShell>
  );
}