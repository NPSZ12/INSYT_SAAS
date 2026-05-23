"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { ChevronLeft, ChevronRight } from "lucide-react";

import Sidebar from "./Sidebar";
import ProjectSidebar from "./ProjectSidebar";
import Topbar from "./Topbar";
import AutoLogout from "./AutoLogout";

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
    const storedUser = localStorage.getItem("insyt_user");

    if (!storedUser) {
      window.location.href = "/login";
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
            className="absolute top-4 right-2 z-50 rounded-full border border-slate-700 bg-slate-900 p-1 text-slate-300 hover:bg-slate-800"
          >
            {mainSidebarCollapsed ? (
              <ChevronRight size={16} />
            ) : (
              <ChevronLeft size={16} />
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