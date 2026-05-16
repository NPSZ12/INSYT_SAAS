"use client";

import { useEffect, useState } from "react";
import { apiGet } from "../../lib/api";

import AppShell from "../../components/AppShell";
import StatCard from "../../components/StatCard";
import PageHeader from "../../components/PageHeader";
import ContentCard from "../../components/ContentCard";
import PageContainer from "../../components/PageContainer";
import SectionGrid from "../../components/SectionGrid";

export default function DashboardPage() {

  const [projectCount, setProjectCount] = useState("0");

  useEffect(() => {
    apiGet("/api/azure-projects")
      .then((projects: string[]) => setProjectCount(String(projects.length)))
      .catch(console.error);
  }, []);

  return (
    <AppShell>
      <PageContainer>

        {/* Header */}
        <div className="flex justify-between items-center mb-10">
          <PageHeader
            title="Dashboard"
            subtitle="Enterprise Review & Intelligence Platform"
          />

          <div className="bg-slate-900 px-5 py-3 rounded-xl border border-slate-800">
            INSYT Admin
          </div>
        </div>

        {/* Stats */}
        <SectionGrid cols={4}>

          <StatCard title="Azure Projects" value={projectCount} />

          <StatCard
            title="Active Reviewers"
            value="38"
          />

          <StatCard
            title="Open Batches"
            value="94"
          />

          <StatCard
            title="QC Completion"
            value="87%"
          />

        </SectionGrid>

        {/* Activity */}
        <ContentCard title="Recent Activity">

          <div className="space-y-4">

            <div className="flex justify-between border-b border-slate-800 pb-4">
              <span>Project Timber — Batch 004 Checked Out</span>
              <span className="text-slate-500">2 mins ago</span>
            </div>

            <div className="flex justify-between border-b border-slate-800 pb-4">
              <span>QC Review Completed — BFS Employee Data</span>
              <span className="text-slate-500">18 mins ago</span>
            </div>

            <div className="flex justify-between border-b border-slate-800 pb-4">
              <span>New Upload Processed — Alpine Claims</span>
              <span className="text-slate-500">43 mins ago</span>
            </div>

          </div>

        </ContentCard>

      </PageContainer>
    </AppShell>
  );
}
