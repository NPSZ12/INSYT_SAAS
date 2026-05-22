"use client";

import AppShell from "../../../components/AppShell";
import PageContainer from "../../../components/PageContainer";
import PageHeader from "../../../components/PageHeader";
import ContentCard from "../../../components/ContentCard";

export default function summariesQcReviewPage() {
  return (
    <AppShell>
      <PageContainer>
        <PageHeader
          title="summaries QC Review"
          subtitle="Review summaries QC decisions, coding, and reviewer output."
        />

        <ContentCard>
          <p className="text-slate-400">
            summaries QC Review will populate from summaries review/QC records.
          </p>
        </ContentCard>
      </PageContainer>
    </AppShell>
  );
}











