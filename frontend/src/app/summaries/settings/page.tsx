"use client";

import AppShell from "../../../components/AppShell";
import PageHeader from "../../../components/PageHeader";
import ContentCard from "../../../components/ContentCard";
import FormLabel from "../../../components/FormLabel";
import Input from "../../../components/Input";
import Select from "../../../components/Select";
import Checkbox from "../../../components/Checkbox";
import PageContainer from "../../../components/PageContainer";
import SectionGrid from "../../../components/SectionGrid";
import { Suspense } from "react";

function SettingsPageContent() {
  return (
    <AppShell>
      <PageContainer>
        <PageHeader
          title="Settings"
          subtitle="Configure platform preferences, security, and review defaults."
        />

        <SectionGrid cols={2}>
          <ContentCard title="Platform Defaults">
            <FormLabel>Default Batch Size</FormLabel>
            <div className="mb-5">
              <Select>
                <option>1 document</option>
                <option>5 documents</option>
                <option>10 documents</option>
                <option>20 documents</option>
                <option>50 documents</option>
              </Select>
            </div>

            <FormLabel>Default Review Mode</FormLabel>
            <Select>
              <option>Text + summaries Panel</option>
              <option>Native + summaries Panel</option>
              <option>Split View</option>
            </Select>
          </ContentCard>

          <ContentCard title="Security">
            <Checkbox label="Require MFA for Admin Users" defaultChecked />
            <Checkbox label="Enable Audit Logging" defaultChecked />
            <Checkbox label="Restrict Downloads by Role" />
          </ContentCard>

          <ContentCard title="Storage">
            <p className="text-slate-400 mb-4">
              Azure Blob project storage connection status.
            </p>

            <div className="bg-slate-950 border border-slate-800 rounded-xl p-4">
              Connected: projects container
            </div>
          </ContentCard>

          <ContentCard title="Branding">
            <FormLabel>Platform Name</FormLabel>
            <Input placeholder="INSYT summaries" />
          </ContentCard>
        </SectionGrid>
      </PageContainer>
    </AppShell>
  );
}

export default function SettingsPage() {
  return (
    <Suspense fallback={<div>Loading settings...</div>}>
      <SettingsPageContent />
    </Suspense>
  );
}









