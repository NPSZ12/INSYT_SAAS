"use client";

import AppShell from "../../../components/AppShell";
import PageContainer from "../../../components/PageContainer";
import PageHeader from "../../../components/PageHeader";
import ContentCard from "../../../components/ContentCard";

export default function DiscoveryQcReviewPage() {
  return (
    <AppShell>
      <PageContainer>
        <PageHeader
          title="Discovery QC Review"
          subtitle="Review Discovery QC decisions, coding, and reviewer output."
        />

        <ContentCard>
          <p className="text-slate-400">
            Discovery QC Review will populate from Discovery review/QC records.
          </p>
        </ContentCard>
      </PageContainer>
    </AppShell>
  );
}








