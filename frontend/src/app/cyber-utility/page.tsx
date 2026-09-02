"use client";

import { Suspense, useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import AppShell from "../../components/AppShell";
import PageContainer from "../../components/PageContainer";
import PageHeader from "../../components/PageHeader";
import ContentCard from "../../components/ContentCard";

const tools = [
  {
    name: "Intake & Preparation",
    path: "/cyber-utility/intake",
    description:
      "Review spreadsheet and CSV files promoted from INSYT Detection, confirm source lineage, and prepare datasets for Cyber² processing.",
  },
  {
    name: "Header & Schema Mapping",
    path: "/cyber-utility/schema-mapping",
    description:
      "Inspect source headers, map fields to project protocol schemas, and create normalized working datasets.",
  },
  {
    name: "Merge & Dedupe",
    path: "/cyber-utility/merge-dedupe",
    description:
      "Combine compatible datasets, preserve source lineage, and remove duplicate records using selected matching fields.",
  },
  {
    name: "Entity Normalization",
    path: "/cyber-utility/entity-normalization",
    description:
      "Normalize names, emails, addresses, phone numbers, identifiers, and related entity variants across structured datasets.",
  },
  {
    name: "Population Analysis",
    path: "/cyber-utility/population-analysis",
    description:
      "Analyze unique individuals, identifiers, relationships, record counts, and reportable populations across processed datasets.",
  },
  {
    name: "Exports & Deliverables",
    path: "/cyber-utility/exports",
    description:
      "Generate final CSV/XLSX outputs, population files, processing reports, audit manifests, and project deliverables.",
  },
];

function CyberUtilityLandingContent() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const workspace = searchParams.get("workspace") || "";
  const client = searchParams.get("client") || "";
  const project = searchParams.get("project") || "";

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

  if (!client || !project) {
    return (
      <AppShell>
        <PageContainer>
          <PageHeader
            title="Cyber² Utility Suite"
            subtitle="Cyber² must be opened from within an INSYT project."
          />

          <ContentCard title="Project Required">
            <p className="text-slate-400">
              Select a client project first, then open Cyber² from the
              project sidebar.
            </p>
          </ContentCard>
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
    const workspace = searchParams.get("workspace");

    if (workspace) params.set("workspace", workspace);
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
          subtitle={`Structured-data processing for ${client} / ${project}.`}
        />

        <div className="mb-6 rounded-xl border border-slate-800 bg-slate-900 px-5 py-4">
          <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
            <div>
              <div className="text-[11px] uppercase tracking-[0.16em] text-slate-500">
                Workspace
              </div>

              <div className="mt-1 text-sm font-semibold text-slate-200">
                {workspace || "capture"}
              </div>
            </div>

            <div>
              <div className="text-[11px] uppercase tracking-[0.16em] text-slate-500">
                Client
              </div>

              <div className="mt-1 text-sm font-semibold text-slate-200">
                {client}
              </div>
            </div>

            <div>
              <div className="text-[11px] uppercase tracking-[0.16em] text-slate-500">
                Project
              </div>

              <div className="mt-1 text-sm font-semibold text-sky-400">
                {project.replaceAll("_", " ")}
              </div>
            </div>
          </div>
        </div>

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
                Open Workflow
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