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
    <div className="min-h-screen bg-slate-950 text-white flex">
      <AutoLogout />
      <UrgentMessageOverlay />
      <div
        className={
          projectSidebarVisible && mainSidebarCollapsed
            ? "relative w-16 shrink-0 overflow-hidden border-r border-slate-800"
            : "relative w-64 shrink-0 border-r border-slate-800"
        }
      >
        {projectSidebarVisible && (
          <button
            type="button"
            onClick={() =>
              setMainSidebarCollapsed((current) => !current)
            }
            className="absolute top-1/2 -translate-y-1/2 right-[-14px] z-50 rounded-full border-2 border-slate-600 bg-slate-900 p-2 text-slate-200 shadow-lg hover:bg-slate-800 hover:border-sky-500 transition"
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
              ? "w-64 scale-90 origin-top-left"
              : "w-64"
          }
        >
          <Sidebar collapsed={projectSidebarVisible && mainSidebarCollapsed} />
        </div>
      </div>

      <ProjectSidebar />

      <div className="flex-1 min-w-0">
        <Topbar />

        <main>{children}</main>
      </div>
    </div>
  );
}

export default function AppShell({ children }: AppShellProps) {
  return (
    <Suspense fallback={<div>Loading...</div>}>
      <AppShellContent>{children}</AppShellContent>
    </Suspense>
  );
}