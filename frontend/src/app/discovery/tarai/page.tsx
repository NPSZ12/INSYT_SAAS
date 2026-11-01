"use client";

import AppShell from "../../../components/AppShell";
import PageContainer from "../../../components/PageContainer";
import PageHeader from "../../../components/PageHeader";
import ContentCard from "../../../components/ContentCard";

export default function TARaiPage() {
  return (
    <AppShell>
      <PageContainer>
        <PageHeader
          title="TARai"
          subtitle="Technology-Assisted Review | INSYT Discovery"
        />

        <ContentCard title="AI-Assisted Privilege Review">
          <div className="space-y-4 text-sm text-slate-300">
            <p>
              TARai is the AI-assisted review workspace
              for INSYT Discovery.
            </p>

            <p>
              This workspace will use Discovery protocol rules
              to support AI privilege suggestions, responsiveness,
              issue classification, and reviewer approval.
            </p>

            <p className="text-amber-300">
              AI classification is not yet enabled.
              Existing document coding remains available
              through Discovery Review.
            </p>
          </div>
        </ContentCard>
      </PageContainer>
    </AppShell>
  );
}