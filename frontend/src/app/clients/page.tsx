"use client";

import { Suspense } from "react";
import AppShell from "../../components/AppShell";
import PageContainer from "../../components/PageContainer";
import PageHeader from "../../components/PageHeader";

function ClientsPageContent() {
  return (
    <AppShell>
      <PageContainer>
        <PageHeader
          title="Clients"
          subtitle="Client, project, user, status, and access overview."
        />
      </PageContainer>
    </AppShell>
  );
}










export default function Page() {
  return (
    <Suspense fallback={<div>Loading...</div>}>
      <ClientsPageContent />
    </Suspense>
  );
}
