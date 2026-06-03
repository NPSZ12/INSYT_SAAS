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

type StoredUser = {
  username: string;
  display_name?: string;
  role: string;
};

export default function ProjectSidebar() {
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const projectId = searchParams.get("project");
  const clientId = searchParams.get("client") || "";
  const selectedBatch = searchParams.get("batch");
  const workspaceParam = searchParams.get("workspace");

  const [selectedOutlineItem, setSelectedOutlineItem] =
    useState<PdfOutlineItem | null>(null);

  const [outlineItems, setOutlineItems] =
    useState<PdfOutlineItem[]>([]);

  const [collapsed, setCollapsed] =
    useState(false);

  const isCapture =
    workspaceParam === "capture" ||
    pathname.startsWith("/capture");
  
  const isSummaries =
    workspaceParam === "summaries" ||
    pathname.startsWith("/summaries");

  const isDiscovery =
    workspaceParam === "discovery" ||
    pathname.startsWith("/discovery");

  const workspaceBase = isSummaries
    ? "/summaries"
    : isDiscovery
      ? "/discovery"
      : "/capture";

  const workspaceName = isSummaries
    ? "summaries"
    : isDiscovery
      ? "discovery"
      : "capture";

  const router = useRouter();

  const [user, setUser] = useState<StoredUser | null>(null);
  const [currentUserBatch, setCurrentUserBatch] = useState("");

  useEffect(() => {
    const storedUser = localStorage.getItem("insyt_user");

    if (storedUser) {
      setUser(JSON.parse(storedUser));
    }
  }, []);

  useEffect(() => {
    if (!user?.username || !projectId) {
      setCurrentUserBatch("");
      return;
    }

    apiGet(
      `/api/${workspaceName}/projects/${encodeURIComponent(
        projectId
      )}/batches?client=${encodeURIComponent(clientId)}`
    )
      .then((response: any) => {
        const checkedOutBatch = (response.batches || []).find(
          (batch: any) =>
            String(batch.status || "").toLowerCase() === "checked out" &&
            batch.checked_out_by === user.username
        );

        const batchName =
          checkedOutBatch?.batch_name ||
          checkedOutBatch?.batch_id ||
          checkedOutBatch?.name ||
          "";

        setCurrentUserBatch(batchName);
      })
      .catch((error: any) => {
        console.error("Failed to load current user batch:", error);
        setCurrentUserBatch("");
      });
  }, [workspaceName, clientId, projectId, user?.username]);

  const selectedDocId = searchParams.get("doc") || "";

  useEffect(() => {
    if (
      !isSummaries ||
      !clientId ||
      !projectId ||
      !selectedBatch ||
      !selectedDocId
    ) {
      setOutlineItems([]);
      setSelectedOutlineItem(null);
      return;
    }

    apiGet(
      `/api/summaries/review/current?client=${encodeURIComponent(
        clientId
      )}&project=${encodeURIComponent(
        projectId
      )}&batch=${encodeURIComponent(
        selectedBatch
      )}&doc=${encodeURIComponent(selectedDocId)}`
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
    clientId,
    projectId,
    selectedBatch,
    selectedDocId,
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

  const reviewBatch =
    selectedBatch || currentUserBatch;

  const reviewQuery = clientId
    ? `?client=${encodedClientId}&project=${encodedProjectId}${
        reviewBatch
          ? `&batch=${encodeURIComponent(reviewBatch)}`
          : ""
      }`
    : `?project=${encodedProjectId}${
        reviewBatch
          ? `&batch=${encodeURIComponent(reviewBatch)}`
          : ""
      }`;

  function isHiddenFor1L(label: string) {
    if (user?.role !== "1L") return false;

    return [
      "Batch Management",
      "Search Folders",
      "Files",
      "QC Review",
      "Review Team",
      "Admin",
      "Settings",
    ].includes(label);
  }

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
      href: `${workspaceBase}/review${reviewQuery}`,
      icon: FileSearch,
    },
    {
      label: "QC Review",
      href: `${workspaceBase}/qc-review${projectQuery}`,
      icon: ClipboardList,
    },
    {
      label: isSummaries
        ? "Saved QC Summaries"
        : "Captured Entities",
      href: isSummaries
        ? `/summaries/summary-data?client=${clientId}&project=${projectId}`
        : `${workspaceBase}/captured-entities?client=${clientId}&project=${projectId}`,
      icon: Database,
    },
    {
      label: "Review Hours",
      href: `/review-hours?workspace=${workspaceName}&client=${encodeURIComponent(clientId)}&project=${encodeURIComponent(projectId || "")}`,
      icon: Clock,
    },
    {
      label: "Messaging",
      href: `${workspaceBase}/messaging${projectQuery}`,
      icon: MessageSquare,
    },
    {
      label: "Review Team",
      href: `/project-users?workspace=${workspaceName}&client=${encodeURIComponent(
        clientId
      )}&project=${encodeURIComponent(projectId || "")}`,
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
          {navItems
            .filter((item) => !isHiddenFor1L(item.label))
            .map((item) => {
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
            selectedOutlineItemId={selectedOutlineItem?.id}
            onSelectOutlineItem={(item) => {
              handleOutlineSelect(item);

              const params = new URLSearchParams(
                searchParams.toString()
              );

              params.set("outline", item.id);

              const targetPage =
                item.summaryPdfPage ??
                item.summary_pdf_page ??
                item.pdfPage ??
                item.pdf_page ??
                item.page ??
                item.pageStart;

              if (targetPage) {
                params.set("page", String(targetPage));
              }

              router.replace(`${pathname}?${params.toString()}`);
            }}
            onSelectHyperlink={(text: string) => {
              console.log("Navigate PDF to:", text);
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