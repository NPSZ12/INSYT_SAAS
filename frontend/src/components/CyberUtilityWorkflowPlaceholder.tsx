"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";

import AppShell from "./AppShell";
import PageContainer from "./PageContainer";
import PageHeader from "./PageHeader";
import ContentCard from "./ContentCard";

type CyberUtilityWorkflowPlaceholderProps = {
  title: string;
  subtitle: string;
  description: string;
};

export default function CyberUtilityWorkflowPlaceholder({
  title,
  subtitle,
  description,
}: CyberUtilityWorkflowPlaceholderProps) {
  const searchParams = useSearchParams();

  const workspace =
    searchParams.get("workspace") || "capture";

  const client =
    searchParams.get("client") || "";

  const project =
    searchParams.get("project") || "";

  const params =
    new URLSearchParams();

  params.set("workspace", workspace);

  if (client) {
    params.set("client", client);
  }

  if (project) {
    params.set("project", project);
  }

  const cyberUtilityHref =
    `/cyber-utility?${params.toString()}`;

  return (
    <AppShell>
      <PageContainer>
        <PageHeader
          title={title}
          subtitle={subtitle}
        />

        <div className="mb-6 rounded-xl border border-slate-800 bg-slate-900 px-5 py-4">
          <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
            <div>
              <div className="text-[11px] uppercase tracking-[0.16em] text-slate-500">
                Workspace
              </div>

              <div className="mt-1 text-sm font-semibold text-slate-200">
                {workspace}
              </div>
            </div>

            <div>
              <div className="text-[11px] uppercase tracking-[0.16em] text-slate-500">
                Client
              </div>

              <div className="mt-1 text-sm font-semibold text-slate-200">
                {client || "Not Selected"}
              </div>
            </div>

            <div>
              <div className="text-[11px] uppercase tracking-[0.16em] text-slate-500">
                Project
              </div>

              <div className="mt-1 text-sm font-semibold text-sky-400">
                {project
                  ? project.replaceAll("_", " ")
                  : "Not Selected"}
              </div>
            </div>
          </div>
        </div>

        <ContentCard title={title}>
          <p className="mb-6 text-slate-400">
            {description}
          </p>

          <div className="rounded-xl border border-slate-800 bg-slate-950 p-6">
            <div className="text-[11px] uppercase tracking-[0.18em] text-slate-500">
              Workflow Status
            </div>

            <div className="mt-2 text-lg font-semibold text-slate-200">
              Ready for Development
            </div>

            <p className="mt-2 text-sm text-slate-500">
              This Cyber² workflow has been established for the
              current project. Processing functionality will be
              added here.
            </p>
          </div>

          <div className="mt-6">
            <Link
              href={cyberUtilityHref}
              className="inline-flex rounded-xl border border-slate-700 bg-slate-800 px-4 py-3 text-sm font-semibold text-slate-200 transition hover:bg-slate-700"
            >
              Back to Cyber²
            </Link>
          </div>
        </ContentCard>
      </PageContainer>
    </AppShell>
  );
}