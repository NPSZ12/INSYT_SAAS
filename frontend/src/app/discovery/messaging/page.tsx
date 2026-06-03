"use client";

import AppShell from "../../../components/AppShell";
import PageContainer from "../../../components/PageContainer";
import PageHeader from "../../../components/PageHeader";
import MessagingPanel from "../../../components/MessagingPanel";

export default function DiscoveryMessagingPage() {
  return (
    <AppShell>
      <PageContainer>
        <PageHeader
          title="Messaging"
          subtitle="Project team, admin team, and private messages."
        />

        <MessagingPanel workspace="discovery" />
      </PageContainer>
    </AppShell>
  );
}