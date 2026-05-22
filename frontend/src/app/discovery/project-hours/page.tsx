"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";

import AppShell from "../../../components/AppShell";
import PageContainer from "../../../components/PageContainer";
import PageHeader from "../../../components/PageHeader";
import ContentCard from "../../../components/ContentCard";
import DataTable from "../../../components/DataTable";
import Button from "../../../components/Button";

function TimesheetPageContent() {
  const searchParams = useSearchParams();

  const projectId = searchParams.get("project");

  const columns = [
    { key: "date", label: "Date" },
    { key: "clock_in", label: "Clock In" },
    { key: "clock_out", label: "Clock Out" },
    { key: "hours", label: "Hours" },
  ];

  const data = [
    {
      date: "2026-05-11",
      clock_in: "9:00 AM",
      clock_out: "12:30 PM",
      hours: "3.5",
    },
    {
      date: "2026-05-10",
      clock_in: "1:00 PM",
      clock_out: "5:00 PM",
      hours: "4.0",
    },
  ];

  if (!projectId) {
    return (
      <AppShell>
        <PageContainer>
          <PageHeader
            title="No Project Selected"
            subtitle="Return to Projects and select a project first."
          />
        </PageContainer>
      </AppShell>
    );
  }

  return (
    <AppShell>
      <PageContainer>
        <PageHeader
          title="Timesheet"
          subtitle={`Hours worked for ${projectId.replaceAll("_", " ")}.`}
        />

        <div className="grid grid-cols-2 gap-6 mb-6">
          <ContentCard title="Current Session">
            <p className="text-slate-400 mb-6">
              Track time spent reviewing this project.
            </p>

            <div className="flex gap-4">
              <Button>Clock In</Button>
              <Button variant="secondary">Clock Out</Button>
            </div>
          </ContentCard>

          <ContentCard title="Weekly Summary">
            <p className="text-slate-400">This Week</p>
            <p className="text-4xl font-bold mt-2">7.5 hrs</p>
          </ContentCard>
        </div>

        <ContentCard title="Time Entries">
          <DataTable columns={columns} data={data} />
        </ContentCard>
      </PageContainer>
    </AppShell>
  );
}
export default function TimesheetPage() {
  return (
    <Suspense fallback={<div>Loading login...</div>}>
      <TimesheetPageContent />
    </Suspense>
  );
}













