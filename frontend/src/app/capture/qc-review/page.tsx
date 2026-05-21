"use client";

import AppShell from "../../../components/AppShell";
import PageContainer from "../../../components/PageContainer";
import PageHeader from "../../../components/PageHeader";
import ContentCard from "../../../components/ContentCard";

export default function CaptureQcReviewPage() {
  return (
    <AppShell>
      <PageContainer>
        <PageHeader
          title="Capture QC Review"
          subtitle="Review Capture QC decisions, coding, and reviewer output."
        />

        <ContentCard>
          <p className="text-slate-400">
            Capture QC Review will populate from Capture review/QC records.
          </p>
        </ContentCard>
      </PageContainer>
    </AppShell>
  );
}











