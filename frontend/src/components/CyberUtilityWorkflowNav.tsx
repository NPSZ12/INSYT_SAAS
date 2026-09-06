"use client";

import {
  usePathname,
  useRouter,
  useSearchParams,
} from "next/navigation";

const workflows = [
  {
    label: "Intake & Preparation",
    path: "/cyber-utility/intake",
  },
  {
    label: "Header & Schema Mapping",
    path: "/cyber-utility/schema-mapping",
  },
  {
    label: "Merge & Dedupe",
    path: "/cyber-utility/merge-dedupe",
  },
  {
    label: "Entity Normalization",
    path: "/cyber-utility/entity-normalization",
  },
  {
    label: "Population Analysis",
    path: "/cyber-utility/population-analysis",
  },
  {
    label: "Exports & Deliverables",
    path: "/cyber-utility/exports",
  },
];

export default function CyberUtilityWorkflowNav() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  function openWorkflow(path: string) {
    const params =
      new URLSearchParams();

    const workspace =
      searchParams.get("workspace");

    const client =
      searchParams.get("client");

    const project =
      searchParams.get("project");

    const batch =
      searchParams.get("batch");

    if (workspace) {
      params.set(
        "workspace",
        workspace
      );
    }

    if (client) {
      params.set(
        "client",
        client
      );
    }

    if (project) {
      params.set(
        "project",
        project
      );
    }

    if (batch) {
      params.set(
        "batch",
        batch
      );
    }

    router.push(
      `${path}?${params.toString()}`
    );
  }

  return (
    <div className="mb-6 overflow-x-auto rounded-xl border border-slate-800 bg-slate-950/80 p-2">
      <div className="flex min-w-max gap-2">
        {workflows.map(
          (workflow) => {
            const active =
              pathname === workflow.path ||
              (
                workflow.path ===
                  "/cyber-utility/schema-mapping" &&
                pathname.startsWith(
                  "/cyber-utility/schema-mapping/"
                )
              );

            return (
              <button
                key={workflow.path}
                type="button"
                onClick={() =>
                  openWorkflow(
                    workflow.path
                  )
                }
                className={
                  active
                    ? "rounded-lg border border-sky-500 bg-sky-950/60 px-4 py-2 text-sm font-semibold text-sky-300"
                    : "rounded-lg border border-slate-800 bg-slate-900 px-4 py-2 text-sm font-medium text-slate-400 transition hover:border-slate-700 hover:bg-slate-800 hover:text-white"
                }
              >
                {workflow.label}
              </button>
            );
          }
        )}
      </div>
    </div>
  );
}