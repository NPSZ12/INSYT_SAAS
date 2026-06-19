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
  HardDriveUpload,
  UploadCloud,
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
  const [hasNewMessages, setHasNewMessages] = useState(false);

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

  const selectedDocId = searchParams.get("doc") || "";

  const isSummariesBatchReviewDoc =
    isSummaries &&
    pathname.startsWith("/summaries/review/doc") &&
    Boolean(selectedBatch) &&
    Boolean(selectedDocId);

  const isSummariesFileReviewDoc =
    isSummaries &&
    pathname.startsWith("/summaries/files/review") &&
    Boolean(selectedDocId);

  const isSummariesReviewDoc =
    isSummariesBatchReviewDoc ||
    isSummariesFileReviewDoc;

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
    const username = String(user?.username || "");
    const role = String(user?.role || "");

    if (!username || !clientId || !projectId) {
      setHasNewMessages(false);
      return;
    }

    let cancelled = false;

    async function checkNewMessages() {
      try {
        const query = new URLSearchParams({
          workspace: String(workspaceName || ""),
          client: String(clientId || ""),
          project: String(projectId || ""),
          username,
          role,
        });

        const response = await apiGet(
          `/api/messages/new-status?${query.toString()}`
        );

        if (!cancelled) {
          setHasNewMessages(Boolean(response.has_new_messages));
        }
      } catch (error) {
        console.warn("Unable to check new messages", error);

        if (!cancelled) {
          setHasNewMessages(false);
        }
      }
    }

    checkNewMessages();

    const timer = window.setInterval(checkNewMessages, 30000);

    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [workspaceName, clientId, projectId, user?.username, user?.role]);

  useEffect(() => {
    if (!user?.username || !projectId) {
      setCurrentUserBatch("");
      return;
    }

    // Do not passively fetch Summaries batches from every Summaries page.
    // Summaries direct file review must be allowed to open by doc without
    // the sidebar performing a background batch lookup.
    //
    // The Review button still refreshes the current batch on click inside
    // refreshAndOpenReview().
    if (workspaceName === "summaries") {
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


  useEffect(() => {
    if (
      !isSummariesReviewDoc ||
      !clientId ||
      !projectId ||
      !selectedDocId
    ) {
      setOutlineItems([]);
      setSelectedOutlineItem(null);
      return;
    }

    const params = new URLSearchParams();

    params.set("client", clientId);
    params.set("project", projectId);

    if (selectedBatch) {
      params.set("batch", selectedBatch);
    }

    params.set("doc", selectedDocId);

    apiGet(`/api/summaries/review/current?${params.toString()}`)
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
    isSummariesReviewDoc,
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


  const projectContextParams = new URLSearchParams();

  projectContextParams.set("workspace", workspaceName);

  if (clientId) {
    projectContextParams.set("client", clientId);
  }

  if (projectId) {
    projectContextParams.set("project", projectId);
  }

  const projectQuery = `?${projectContextParams.toString()}`;

  const overlaysQuery = projectQuery;

  const reviewContextParams = new URLSearchParams(
    projectContextParams.toString()
  );

  if (currentUserBatch) {
    reviewContextParams.set("batch", currentUserBatch);
  }

  const reviewQuery = `?${reviewContextParams.toString()}`;

  async function refreshAndOpenReview() {
    if (!projectId) return;

    let latestBatch = "";
    const refreshToken = Date.now();

    try {
      if (user?.username) {
        const response = await apiGet(
          `/api/${workspaceName}/projects/${encodeURIComponent(
            projectId
          )}/batches?client=${encodeURIComponent(clientId)}`
        );

        const checkedOutBatch = (response.batches || []).find(
          (batch: any) =>
            String(batch.status || "").toLowerCase() === "checked out" &&
            batch.checked_out_by === user.username
        );

        latestBatch =
          checkedOutBatch?.batch_name ||
          checkedOutBatch?.batch_id ||
          checkedOutBatch?.name ||
          "";

        setCurrentUserBatch(latestBatch);
      }
    } catch (error) {
      console.error("Failed to refresh current user batch:", error);
    }

    const reviewOpenParams = new URLSearchParams();

    reviewOpenParams.set("workspace", workspaceName);

    if (clientId) {
      reviewOpenParams.set("client", clientId);
    }

    if (projectId) {
      reviewOpenParams.set("project", projectId);
    }

    if (latestBatch) {
      reviewOpenParams.set("batch", latestBatch);
    }

    reviewOpenParams.set("refresh", String(refreshToken));

    router.push(
      `${workspaceBase}/review?${reviewOpenParams.toString()}`
    );
  }

  function isHiddenFor1L(label: string) {
    if (user?.role !== "1L") return false;

    return [
      "Batch Management",
      "Processing Center",
      "Overlays / Final Deliverables",
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
      href: isSummaries
        ? `/summaries/files${projectQuery}`
        : isDiscovery
          ? `/discovery/files${projectQuery}`
          : `/capture/files${projectQuery}`,
      icon: FileText,
    },
    {
      label: "Processing Center",
      href: isSummaries
        ? `/summaries/processing-center${projectQuery}`
        : isDiscovery
          ? `/discovery/processing-center${projectQuery}`
          : `/capture/processing-center${projectQuery}`,
      icon: HardDriveUpload,
    },
    {
      label: "Overlays / Final Deliverables",
      href: `/project-management/upload-overlay${overlaysQuery}`,
      icon: UploadCloud,
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
      href: isSummaries
        ? `/summaries/review${reviewQuery}`
        : isDiscovery
          ? `/discovery/review${reviewQuery}`
          : `/capture/review${reviewQuery}`,
      icon: FileSearch,
    },
    {
      label: "QC Review",
      href: `${workspaceBase}/qc-review${projectQuery}`,
      icon: ClipboardList,
    },
    {
      label: isSummaries
        ? "Completed QC Summaries"
        : isDiscovery
          ? "Captured Coding"
          : "Captured Entities",
      href: isSummaries
        ? `/summaries/summary-data${projectQuery}&view=raw`
        : `${workspaceBase}/captured-entities${projectQuery}&view=raw`,
      icon: Database,
    },
    {
      label: "Review Hours",
      href: `/review-hours${projectQuery}`,
      icon: Clock,
    },
    {
      label: "Messaging",
      href: `${workspaceBase}/messaging${projectQuery}`,
      icon: MessageSquare,
    },
    {
      label: "Review Team",
      href: `/project-users${projectQuery}`,
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
          isSummariesReviewDoc
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
            collapsed ? "p-2 pt-4" : "p-5 pt-4 pr-4"
          }`}
        >
          {navItems
            .filter((item) => !isHiddenFor1L(item.label))
            .map((item) => {
              const itemPath = item.href.split("?")[0];

              const active = pathname === itemPath;

              const Icon = item.icon;

              const linkClass = active
                ? `flex items-center ${
                    collapsed ? "justify-center px-2" : "gap-3 px-3"
                  } py-2.5 rounded-xl bg-teal-600 text-white`
                : `flex items-center ${
                    collapsed ? "justify-center px-2" : "gap-3 px-3"
                  } py-2.5 rounded-xl hover:bg-slate-800 text-slate-300`;

              if (item.label === "Review") {
                return (
                  <button
                    key={item.href}
                    type="button"
                    title={item.label}
                    onClick={refreshAndOpenReview}
                    className={`${linkClass} w-full text-left`}
                  >
                    <Icon size={18} />

                    {!collapsed && (
                      <span className="insyt-workspace text-sm">
                        {item.label}
                      </span>
                    )}
                  </button>
                );
              }

              return (
                <Link
                  key={item.href}
                  href={item.href}
                  title={item.label}
                  onClick={() => {
                    if (item.label === "Files") {
                      console.log("PROJECT SIDEBAR FILES CLICK", item.href);
                    }
                  }}
                  className={`${linkClass} relative`}
                >
                  <Icon size={18} />

                  {!collapsed && (
                    <span className="insyt-workspace text-sm">
                      {item.label}
                    </span>
                  )}

                  {item.label === "Messaging" && Boolean(hasNewMessages) ? (
                    <span
                      className={
                        collapsed
                          ? "absolute -right-1 -top-1 rounded-full bg-red-600 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wide text-white shadow-lg"
                          : "absolute right-2 top-1 rounded-full bg-red-600 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-white shadow-lg"
                      }
                    >
                      New
                    </span>
                  ) : null}
                </Link>
              );
            })}
        </nav>
      </div>

      {isSummariesReviewDoc && !collapsed && (
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

      {isSummariesReviewDoc && collapsed && (
        <div className="h-1/2 flex items-center justify-center border-t border-slate-800">
          <div className="rotate-90 whitespace-nowrap text-[11px] uppercase tracking-[0.18em] text-slate-500">
            PDF Outline
          </div>
        </div>
      )}
    </aside>
  );
}