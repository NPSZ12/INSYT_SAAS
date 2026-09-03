"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { ChevronLeft, ChevronRight } from "lucide-react";

import Sidebar from "./Sidebar";
import ProjectSidebar from "./ProjectSidebar";
import Topbar from "./Topbar";
import AutoLogout from "./AutoLogout";
import UrgentMessageOverlay from "./UrgentMessageOverlay";

type AppShellProps = {
  children: React.ReactNode;
};

function AppShellContent({ children }: AppShellProps) {
  const searchParams = useSearchParams();
  const projectId = searchParams.get("project");

  const projectSidebarVisible = Boolean(projectId);

  const [mainSidebarCollapsed, setMainSidebarCollapsed] =
    useState(projectSidebarVisible);

  const [authChecked, setAuthChecked] = useState(false);

  useEffect(() => {
    const pathname = window.location.pathname;

    const publicRoutes = ["/launcher", "/login"];

    const isPublicRoute = publicRoutes.some((route) =>
      pathname.startsWith(route)
    );

    if (isPublicRoute) {
      setAuthChecked(true);
      return;
    }

    const storedUser = localStorage.getItem("insyt_user");

    if (!storedUser) {
      window.location.href = "/launcher";
      return;
    }

    setAuthChecked(true);
  }, []);

  if (!authChecked) {
    return null;
  }

  return (
    <div className="flex h-screen overflow-hidden bg-slate-950 text-white">
      <AutoLogout />
      <UrgentMessageOverlay />

      {/* MAIN SIDEBAR — remains visible while page content scrolls */}
      <div
        className={
          projectSidebarVisible && mainSidebarCollapsed
            ? "relative h-screen w-16 shrink-0 overflow-hidden border-r border-slate-800"
            : "relative h-screen w-64 shrink-0 overflow-hidden border-r border-slate-800"
        }
      >
        {projectSidebarVisible && (
          <button
            type="button"
            onClick={() =>
              setMainSidebarCollapsed((current) => !current)
            }
            className="absolute right-[-14px] top-1/2 z-50 -translate-y-1/2 rounded-full border-2 border-slate-600 bg-slate-900 p-2 text-slate-200 shadow-lg transition hover:border-sky-500 hover:bg-slate-800"
            aria-label={
              mainSidebarCollapsed
                ? "Expand main sidebar"
                : "Collapse main sidebar"
            }
          >
            {mainSidebarCollapsed ? (
              <ChevronRight size={20} strokeWidth={2.5} />
            ) : (
              <ChevronLeft size={20} strokeWidth={2.5} />
            )}
          </button>
        )}

        <div
          className={
            projectSidebarVisible && mainSidebarCollapsed
              ? "h-screen w-64 origin-top-left scale-90"
              : "h-screen w-64"
          }
        >
          <Sidebar
            collapsed={
              projectSidebarVisible &&
              mainSidebarCollapsed
            }
          />
        </div>
      </div>

      {/* PROJECT SIDEBAR — also remains visible */}
      <div className="h-screen shrink-0 overflow-hidden">
        <ProjectSidebar />
      </div>

      {/* TOPBAR REMAINS VISIBLE; ONLY MAIN CONTENT SCROLLS */}
      <div className="flex h-screen min-w-0 flex-1 flex-col overflow-hidden">
        <Topbar />

        <main className="insyt-content-surface min-h-0 flex-1 overflow-y-auto bg-slate-950 text-white">
          {children}
        </main>
      </div>
    </div>
  );
}

export default function AppShell({
  children,
}: AppShellProps) {
  return (
    <Suspense fallback={<div>Loading...</div>}>
      <AppShellContent>
        {children}
      </AppShellContent>
    </Suspense>
  );
}