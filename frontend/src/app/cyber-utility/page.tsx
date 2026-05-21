"use client";

import AppShell from "../../components/AppShell";
import PageContainer from "../../components/PageContainer";
import PageHeader from "../../components/PageHeader";
import ContentCard from "../../components/ContentCard";
import { Suspense, useState } from "react";
import { apiPost } from "../../lib/api";
import { usePathname, useSearchParams } from "next/navigation";


const tools = [
  {
    name: "XL Processing",
    description: "Convert Excel workbooks to CSV outputs inside Azure storage.",
  },
  {
    name: "Merge / Dedupe",
    description: "Merge datasets, normalize records, and remove duplicates.",
  },
  {
    name: "Denist",
    description: "Remove known system/application files from processing populations.",
  },
  {
    name: "Assign Doc IDs",
    description: "Apply sequential Doc IDs and create defensible load-ready indexes.",
  },
  {
    name: "Entity Normalization",
    description: "Normalize names, emails, addresses, and entity variants.",
  },
  {
    name: "Breach Population Analyzer",
    description: "Analyze PII/PHI populations and reduce notification populations.",
  },
];

function CyberUtilityPageContent() {

  const [message, setMessage] = useState("");
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const selectedProject =
    searchParams.get("project") || "";

  const workspace = pathname.startsWith("/summaries")
    ? "summaries"
    : pathname.startsWith("/discovery")
      ? "discovery"
      : "capture";


  function runTool(toolName: string) {
    if (!selectedProject) {
      setMessage("Select a project first.");
      return;
    }
  apiPost("/api/cyber-utility/jobs", {
    workspace,
    project_id: selectedProject,
    tool_name: toolName,
    input_path: null,
    output_path: null,
    options: {},
  })
    .then((response) => {
      setMessage(
        `${response.tool_name} queued. Job ID: ${response.job_id}`
      );
    })
    .catch((error) => {
      console.error(error);
      setMessage("Failed to queue Cyber² Utility job.");
    });
}
  return (
    <AppShell>
      <PageContainer>
        <PageHeader
          title="Cyber² Utility Suite"
          subtitle="Run utility workflows against Azure-hosted project files without downloading documents locally."
        />
        {message && (
          <p className="text-sm text-sky-400 mb-6">
            {message}
          </p>
        )}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {tools.map((tool) => (
            <ContentCard key={tool.name} title={tool.name}>
              <p className="text-slate-400 mb-6">
                {tool.description}
              </p>

              <button
                type="button"
                onClick={() => runTool(tool.name)}
                className="bg-lime-50 hover:bg-lime-50 text-white rounded-xl px-4 py-3 font-semibold"
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
      <CyberUtilityPageContent />
    </Suspense>
  );
}

