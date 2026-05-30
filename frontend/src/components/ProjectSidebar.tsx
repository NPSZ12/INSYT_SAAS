"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

import PdfOutlinePane, {
  type PdfOutlineItem,
} from "./summaries/PdfOutlinePane";

import { apiGet } from "../lib/api";

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
  ChevronLeft,
  ChevronRight,
} from "lucide-react";

type NavItem = {
  label: string;
  href: string;
  icon: any;
};

function parseSummaryOutline(text: string): PdfOutlineItem[] {
  const source = String(text || "")
    .replace(/\r\n/g, "\n")
    .replace(/\r/g, "\n");

  const pattern =
    /(\d{1,3}:\s+.*?)(?=\d{4}\/\d{2}\/\d{2})\s*(\d{4}\/\d{2}\/\d{2}[\s\S]*?%)\s*([\s\S]*?)(?=^\d{1,3}:\s+|\s\d{1,3}:\s+|\Z)/gm;

  const items: PdfOutlineItem[] = [];

  for (const match of source.matchAll(pattern)) {
    const title =
      match[1]?.replace(/\s+/g, " ").trim() || "";

    const citation =
      match[2]?.replace(/\s+/g, " ").trim() || "";

    const originalSummary =
      match[3]?.replace(/\s+/g, " ").trim() || "";

    if (!title || !citation) continue;

    const pageMatch = citation.match(/\bp\.\s*(\d+)/i);

    const page = pageMatch
      ? Number(pageMatch[1])
      : undefined;

    items.push({
      id: `summary-${items.length + 1}`,
      title,
      citation,
      originalSummary,
      qcSummary: originalSummary,
      page,
    });
  }

  return items;
}

export default function ProjectSidebar() {
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const projectId = searchParams.get("project");
  const clientId = searchParams.get("client") || "";
  const selectedBatch = searchParams.get("batch");

  const [selectedOutlineItem, setSelectedOutlineItem] =
    useState<PdfOutlineItem | null>(null);

  const [outlineItems, setOutlineItems] =
    useState<PdfOutlineItem[]>([]);

  const [collapsed, setCollapsed] =
    useState(false);

  const isSummaries =
    pathname.startsWith("/summaries");

  const isDiscovery =
    pathname.startsWith("/discovery");

  const workspaceBase = isSummaries
    ? "/summaries"
    : isDiscovery
      ? "/discovery"
      : "/capture";

  const router = useRouter();

  useEffect(() => {
    if (!isSummaries || !projectId || !selectedBatch) {
      setOutlineItems([]);
      setSelectedOutlineItem(null);
      return;
    }

    apiGet(
      `/api/summaries/review/current?project=${encodeURIComponent(
        projectId
      )}&batch=${encodeURIComponent(selectedBatch)}`
    )
      .then((response: any) => {
        const incomingOutlineItems =
          response?.outline_items || [];

        setOutlineItems(incomingOutlineItems);

        if (incomingOutlineItems.length > 0) {
          setSelectedOutlineItem(incomingOutlineItems[0]);
        } else {
          setSelectedOutlineItem(null);
        }
      })
      .catch((error: any) => {
        console.error(
          "Failed to load PDF Outline:",
          error
        );

        setOutlineItems([]);
        setSelectedOutlineItem(null);
      });
  }, [
    isSummaries,
    projectId,
    selectedBatch,
  ]);

  if (!projectId) {
    return null;
  }

  function handleOutlineSelect(item: PdfOutlineItem) {
    setSelectedOutlineItem(item);

    const params = new URLSearchParams(searchParams.toString());
    params.set("outline", item.id);

    router.replace(`${pathname}?${params.toString()}`);
  }

  const encodedClientId =
    encodeURIComponent(clientId);

  const encodedProjectId =
    encodeURIComponent(projectId);

  const projectQuery = clientId
    ? `?client=${encodedClientId}&project=${encodedProjectId}${
        selectedBatch
          ? `&batch=${encodeURIComponent(
              selectedBatch
            )}`
          : ""
      }`
    : `?project=${encodedProjectId}${
        selectedBatch
          ? `&batch=${encodeURIComponent(
              selectedBatch
            )}`
          : ""
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
    <aside
      className={`relative bg-slate-950 border-r border-slate-800 min-h-screen h-screen flex flex-col transition-all duration-300 ${
        collapsed ? "w-16" : "w-64"
      }`}
    >
      <button
        type="button"
        onClick={() =>
          setCollapsed((value) => !value)
        }
        className="absolute -right-3 top-1/2 z-30 flex h-8 w-8 -translate-y-1/2 items-center justify-center rounded-full border border-slate-700 bg-slate-900 text-slate-300 shadow-lg hover:bg-slate-800 hover:text-white"
        title={
          collapsed
            ? "Expand Project Sidebar"
            : "Collapse Project Sidebar"
        }
      >
        {collapsed ? (
          <ChevronRight size={18} />
        ) : (
          <ChevronLeft size={18} />
        )}
      </button>

      <div
        className={
          isSummaries
            ? "h-1/2 flex flex-col border-b border-slate-800"
            : "h-full flex flex-col"
        }
      >
        <div className="shrink-0 p-5 pb-4 border-b border-slate-800 bg-slate-950">
          {!collapsed && (
            <>
              <div className="text-[11px] uppercase tracking-[0.18em] text-slate-500 mb-2">
                Project Tools
              </div>

              <div className="insyt-project text-sky-400 text-sm font-semibold truncate">
                {projectId.replaceAll("_", " ")}
              </div>
            </>
          )}

          {collapsed && (
            <div className="text-center text-[11px] font-bold text-sky-400">
              P
            </div>
          )}
        </div>

        <nav
          className={`space-y-2 overflow-y-auto flex-1 ${
            collapsed
              ? "p-2 pt-4"
              : "p-5 pt-4 pr-4"
          }`}
        >
          {navItems.map((item) => {
            const itemPath =
              item.href.split("?")[0];

            const active =
              pathname === itemPath;

            const Icon = item.icon;

            return (
              <Link
                key={item.href}
                href={item.href}
                title={item.label}
                className={
                  active
                    ? `flex items-center ${
                        collapsed
                          ? "justify-center px-2"
                          : "gap-3 px-3"
                      } py-2.5 rounded-xl bg-teal-600 text-white`
                    : `flex items-center ${
                        collapsed
                          ? "justify-center px-2"
                          : "gap-3 px-3"
                      } py-2.5 rounded-xl hover:bg-slate-800 text-slate-300`
                }
              >
                <Icon size={18} />

                {!collapsed && (
                  <span className="insyt-workspace text-sm">
                    {item.label}
                  </span>
                )}
              </Link>
            );
          })}
        </nav>
      </div>

      {isSummaries && !collapsed && (
        <div className="h-1/2 flex flex-col overflow-hidden">
          <PdfOutlinePane
            projectId={projectId}
            outlineItems={outlineItems}
            selectedOutlineItemId={
              selectedOutlineItem?.id
            }
            onSelectOutlineItem={
              handleOutlineSelect
            }
            onSelectHyperlink={(
              text: string
            ) => {
              console.log(
                "Navigate PDF to:",
                text
              );
            }}
          />
        </div>
      )}

      {isSummaries && collapsed && (
        <div className="h-1/2 flex items-center justify-center border-t border-slate-800">
          <div className="rotate-90 whitespace-nowrap text-[11px] uppercase tracking-[0.18em] text-slate-500">
            PDF Outline
          </div>
        </div>
      )}
    </aside>
  );
}