"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";

import {
  LayoutDashboard,
  FileText,
  FileSearch,
  MessageSquare,
  Clock,
  Database,
  Layers,
  Search,
  Users,
  ClipboardList,
  FolderTree,
  Settings,
  ShieldCheck,
} from "lucide-react";

type NavItem = {
  label: string;
  href: string;
  icon: any;
};

export default function ProjectSidebar() {
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const projectId = searchParams.get("project");
  const selectedBatch = searchParams.get("batch");

  if (!projectId) {
    return null;
  }

  const isSummaries = pathname.startsWith("/summaries");
  const isDiscovery = pathname.startsWith("/discovery");

  const workspaceBase = isSummaries
    ? "/summaries"
    : isDiscovery
      ? "/discovery"
      : "/capture";

  const encodedProjectId = encodeURIComponent(projectId);

  const projectQuery = `?project=${encodedProjectId}${
    selectedBatch ? `&batch=${encodeURIComponent(selectedBatch)}` : ""
  }`;

  const navItems: NavItem[] = [
    {
      label: "Dashboard",
      href: `${workspaceBase}/project-dashboard${projectQuery}`,
      icon: LayoutDashboard,
    },
    {
      label: "Protocol",
      href: `${workspaceBase}/protocol${projectQuery}`,
      icon: FileText,
    },
    {
      label: "Files",
      href: `${workspaceBase}/files${projectQuery}`,
      icon: FileText,
    },
    {
      label: "Batches",
      href: `${workspaceBase}/batches${projectQuery}`,
      icon: Layers,
    },
    {
      label: "Batch Management",
      href: `${workspaceBase}/batch-management${projectQuery}`,
      icon: FolderTree,
    },
    {
      label: "Search Folders",
      href: `${workspaceBase}/search-folders${projectQuery}`,
      icon: Search,
    },
    {
      label: "Review",
      href: `${workspaceBase}/review${projectQuery}`,
      icon: FileSearch,
    },
    {
      label: "QC Review",
      href: `${workspaceBase}/qc-review${projectQuery}`,
      icon: ClipboardList,
    },
    {
      label: "Captured Entities",
      href: `${workspaceBase}/captured-entities${projectQuery}`,
      icon: Database,
    },
    {
      label: "Project Hours",
      href: `${workspaceBase}/project-hours${projectQuery}`,
      icon: Clock,
    },
    {
      label: "Messaging",
      href: `${workspaceBase}/messaging${projectQuery}`,
      icon: MessageSquare,
    },
    {
      label: "User Access",
      href: `${workspaceBase}/user-access${projectQuery}`,
      icon: Users,
    },
    {
      label: "Admin",
      href: `${workspaceBase}/admin${projectQuery}`,
      icon: ShieldCheck,
    },
    {
      label: "Settings",
      href: `${workspaceBase}/settings${projectQuery}`,
      icon: Settings,
    },
  ];

  return (
    <aside className="w-64 bg-slate-950 border-r border-slate-800 p-5 min-h-screen h-screen flex flex-col">
      <div className="shrink-0 mb-4">
        <div className="text-[11px] uppercase tracking-[0.18em] text-slate-500 mb-2">
          Project Tools
        </div>

        <div className="insyt-project text-sky-400 text-sm font-semibold truncate">
          {projectId.replaceAll("_", " ")}
        </div>
      </div>

      <nav className="space-y-2 overflow-y-auto pr-1 flex-1">
        {navItems.map((item) => {
          const itemPath = item.href.split("?")[0];
          const active = pathname === itemPath;
          const Icon = item.icon;

          return (
            <Link
              key={item.href}
              href={item.href}
              className={
                active
                  ? "flex items-center gap-3 px-3 py-2.5 rounded-xl bg-teal-600 text-white"
                  : "flex items-center gap-3 px-3 py-2.5 rounded-xl hover:bg-slate-800 text-slate-300"
              }
            >
              <Icon size={18} />

              <span className="insyt-workspace text-sm">
                {item.label}
              </span>
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}