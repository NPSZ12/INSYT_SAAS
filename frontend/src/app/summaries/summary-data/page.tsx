"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";

import AppShell from "../../../components/AppShell";
import PageContainer from "../../../components/PageContainer";
import PageHeader from "../../../components/PageHeader";
import ContentCard from "../../../components/ContentCard";
import DataTable from "../../../components/DataTable";
import { apiGet } from "../../../lib/api";

type SummaryDataRow = {
  pdf_name: string;
  title: string;
  citation: string;
  original_summary: string;
  qc_summary: string;
  last_modified: string;
};

function SummaryDataPageContent() {
  const searchParams = useSearchParams();

  const clientId = searchParams.get("client") || "";
  const projectId = searchParams.get("project") || "";

  const [rows, setRows] = useState<SummaryDataRow[]>([]);
  const [message, setMessage] = useState("");

  useEffect(() => {
    if (!clientId || !projectId) {
      setRows([]);
      return;
    }

    apiGet(
      `/api/summaries/summary-data?client=${encodeURIComponent(
        clientId
      )}&project=${encodeURIComponent(projectId)}`
    )
      .then((response) => {
        setRows(response.rows || []);
      })
      .catch((error) => {
        console.error(error);
        setMessage("Failed to load saved QC summaries.");
        setRows([]);
      });
  }, [clientId, projectId]);

  const columns = [
    { key: "pdf_name", label: "PDF Name" },
    { key: "title", label: "Title" },
    { key: "citation", label: "Citation" },
    { key: "original_summary", label: "Original Summary" },
    { key: "qc_summary", label: "QC Summary" },
    { key: "last_modified", label: "Last Modified" },
  ];

  if (!projectId) {
    return (
      <AppShell>
        <PageContainer>
          <PageHeader
            title="Saved QC Summaries"
            subtitle="Select a project first."
          />
        </PageContainer>
      </AppShell>
    );
  }

  return (
    <AppShell>
      <PageContainer>
        <PageHeader
          title="Saved QC Summaries"
          subtitle={`Saved summary edits for ${projectId.replaceAll(
            "_",
            " "
          )}.`}
        />

        {message && (
          <p className="mb-4 text-sm text-red-400">
            {message}
          </p>
        )}

        <ContentCard title="Updated Summary Data Table">
          <div className="max-h-[70vh] overflow-auto">
            <DataTable columns={columns} data={rows} />
          </div>
        </ContentCard>
      </PageContainer>
    </AppShell>
  );
}

export default function SummaryDataPage() {
  return (
    <Suspense fallback={<div>Loading saved QC summaries...</div>}>
      <SummaryDataPageContent />
    </Suspense>
  );
}