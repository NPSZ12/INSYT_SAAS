"use client";

import { Suspense } from "react";

import Sidebar from "./Sidebar";
import ProjectSidebar from "./ProjectSidebar";
import Topbar from "./Topbar";

type AppShellProps = {
  children: React.ReactNode;
};

function AppShellContent({ children }: AppShellProps) {
  return (
    <div className="min-h-screen bg-slate-950 text-white flex">
      <Sidebar />

      <ProjectSidebar />

      <div className="flex-1 min-w-0">
        <Topbar />

        <main>
          {children}
        </main>
      </div>
    </div>
  );
}

export default function AppShell({ children }: AppShellProps) {
  return (
    <Suspense fallback={<div>Loading...</div>}>
      <AppShellContent>
        {children}
      </AppShellContent>
    </Suspense>
  );
}