"use client";

import { Suspense, useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import AppShell from "../../components/AppShell";
import PageContainer from "../../components/PageContainer";
import PageHeader from "../../components/PageHeader";
import ContentCard from "../../components/ContentCard";

const tools = [
  {
    name: "XL Processing",
    path: "/cyber-utility/xl-processing",
    description: "Convert Excel workbooks to CSV outputs, preview spreadsheets, extract headers, and build master outputs.",
  },
  {
    name: "Merge / Dedupe",
    path: "",
    description: "Merge datasets, normalize records, and remove duplicates.",
  },
  {
    name: "Denist",
    path: "",
    description: "Remove known system/application files from processing populations.",
  },
  {
    name: "Assign Doc IDs",
    path: "",
    description: "Apply sequential Doc IDs and create defensible load-ready indexes.",
  },
  {
    name: "Entity Normalization",
    path: "",
    description: "Normalize names, emails, addresses, and entity variants.",
  },
  {
    name: "Breach Population Analyzer",
    path: "",
    description: "Analyze PII/PHI populations and reduce notification populations.",
  },
];

function CyberUtilityLandingContent() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const workspace = searchParams.get("workspace") || "";

  useEffect(() => {
    if (workspace !== "summaries") {
      return;
    }

    const params = new URLSearchParams(searchParams.toString());

    router.replace(`/summaries/files?${params.toString()}`);
  }, [router, searchParams, workspace]);

  if (workspace === "summaries") {
    return (
      <AppShell>
        <PageContainer>
          <PageHeader
            title="Redirecting"
            subtitle="Cyber² Utility is not available in INSYT Summaries."
          />
        </PageContainer>
      </AppShell>
    );
  }

  function openTool(path: string) {
    if (!path) {
      return;
    }

    const params = new URLSearchParams();

    const client = searchParams.get("client");
    const project = searchParams.get("project");
    const batch = searchParams.get("batch");

    if (client) params.set("client", client);
    if (project) params.set("project", project);
    if (batch) params.set("batch", batch);

    const query = params.toString();

    router.push(query ? `${path}?${query}` : path);
  }

  return (
    <AppShell>
      <PageContainer>
        <PageHeader
          title="Cyber² Utility Suite"
          subtitle="Select a utility workflow to run against Azure-hosted project files without downloading documents locally."
        />

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {tools.map((tool) => (
            <ContentCard key={tool.name} title={tool.name}>
              <p className="text-slate-400 mb-6">
                {tool.description}
              </p>

              <button
                type="button"
                onClick={() => openTool(tool.path)}
                className="bg-lime-50 hover:bg-lime-100 text-slate-700 rounded-xl px-4 py-3 font-semibold"
              >
                Open Tool
              </button>
            </ContentCard>
          ))}
        </div>
      </PageContainer>
    </AppShell>
  );
}

export default function Page() {
  return (
    <Suspense fallback={<div>Loading...</div>}>
      <CyberUtilityLandingContent />
    </Suspense>
  );
}