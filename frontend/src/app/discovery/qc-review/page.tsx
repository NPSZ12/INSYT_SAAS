"use client";

import AppShell from "../../../components/AppShell";
import PageContainer from "../../../components/PageContainer";
import PageHeader from "../../../components/PageHeader";
import ContentCard from "../../../components/ContentCard";

export default function discoveryQcReviewPage() {
  return (
    <AppShell>
      <PageContainer>
        <PageHeader
          title="discovery QC Review"
          subtitle="Review discovery QC decisions, coding, and reviewer output."
        />

        <ContentCard>
          <p className="text-slate-400">
            discovery QC Review will populate from discovery review/QC records.
          </p>
        </ContentCard>
      </PageContainer>
    </AppShell>
  );
}











