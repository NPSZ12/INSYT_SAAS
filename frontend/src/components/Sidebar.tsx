"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import Image from "next/image";

import {
  FolderKanban,
  Clock,
  Users,
  Building2,
  FolderPlus,
  Rocket,
} from "lucide-react";

type StoredUser = {
  username: string;
  display_name: string;
  role: string;

  workspace_access?: string[];
  client_access?: string[];
  project_access?: string[];
  permissions?: string[];
};

type NavItem = {
  label: string;
  href: string;
  icon: any;
};

type SidebarProps = {
  collapsed?: boolean;
};

export default function Sidebar({
  collapsed = false,
}: SidebarProps) {
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const isSummaries = pathname.startsWith("/summaries");
  const isDiscovery = pathname.startsWith("/discovery");

  const workspaceBase = isSummaries
    ? "/summaries"
    : isDiscovery
      ? "/discovery"
      : "/capture";

  const workspaceName =
    searchParams.get("workspace") ||
    localStorage.getItem("insyt_selected_workspace") ||
    "capture";

  const projectsHref = `/projects?workspace=${workspaceName}`;

  const queryClient = searchParams.get("client");
  const queryProject = searchParams.get("project");
  const selectedBatch = searchParams.get("batch");

  const contextParams = new URLSearchParams();

  if (queryClient) {
    contextParams.set("client", queryClient);
  }

  if (queryProject) {
    contextParams.set("project", queryProject);
  }

  if (selectedBatch) {
    contextParams.set("batch", selectedBatch);
  }

  const projectQuery = contextParams.toString()
    ? `?${contextParams.toString()}`
    : "";

  const [user, setUser] =
    useState<StoredUser | null>(null);

  useEffect(() => {
    const storedUser = localStorage.getItem("insyt_user");

    if (storedUser) {
      setUser(JSON.parse(storedUser));
    }
  }, []);

  const normalizedRole =
    user?.role?.toLowerCase() || "";

  const isAdminRole =
    normalizedRole.includes("admin") ||
    normalizedRole === "rm" ||
    normalizedRole === "tl" ||
    normalizedRole === "qc" ||
    normalizedRole.includes("review manager") ||
    normalizedRole.includes("team lead");

  const navItems: NavItem[] = isAdminRole
    ? [
        {
          label: "Projects",
          href: projectsHref,
          icon: FolderKanban,
        },
        {
          label: "Project Management",
          href: `/new-project?workspace=${workspaceName}`,
          icon: FolderPlus,
        },
        {
          label: "Clients",
          href: `/clients?workspace=${workspaceName}`,
          icon: Building2,
        },
        {
          label: "User Accounts",
          href: `/user-access?workspace=${workspaceName}`,
          icon: Users,
        },
        {
          label: "Project Hours",
          href: `/project-hours?workspace=${workspaceName}`,
          icon: Clock,
        },
      ]
    : [
        {
          label: "Projects",
          href: projectsHref,
          icon: FolderKanban,
        },
      ];

  return (
    <aside
      className={
        collapsed
          ? "w-16 bg-slate-900 border-r border-slate-800 p-3 min-h-screen h-screen flex flex-col transition-all duration-200"
          : "w-72 bg-slate-900 border-r border-slate-800 p-6 min-h-screen h-screen flex flex-col transition-all duration-200"
      }
    >
      <div className="shrink-0">
        <div
          className={
            collapsed
              ? "flex justify-center mb-4"
              : "flex items-end gap-0.5 mb-4"
          }
        >
          {collapsed ? (
            <span className="insyt-brand text-3xl font-bold text-sky-400">
              I
            </span>
          ) : (
            <>
              <span className="insyt-brand text-4xl font-bold text-white">
                I
              </span>

              <span className="insyt-brand text-4xl font-bold text-sky-400">
                N
              </span>

              <span className="insyt-brand text-4xl font-bold text-white">
                SYT
              </span>

              <span className="insyt-brand text-[1.4em] leading-none mb-[0.22em] text-sky-400 font-bold">
                360
              </span>
            </>
          )}
        </div>

        <Link
          href="/launcher"
          title={collapsed ? "Launcher" : undefined}
          className={
            collapsed
              ? "flex items-center justify-center py-3 rounded-xl bg-slate-700 hover:bg-slate-600 text-slate-200 transition mb-3"
              : "flex items-center gap-3 px-4 py-3 rounded-xl bg-slate-700 hover:bg-slate-600 text-slate-200 text-base font-semibold transition mb-3"
          }
        >
          <Rocket size={collapsed ? 24 : 20} />

          {!collapsed && (
            <span className="insyt-workspace">
              Launcher
            </span>
          )}
        </Link>

        <Link
          href={`/cyber-utility${projectQuery}`}
          title={collapsed ? "Cyber² Utility" : undefined}
          className={
            collapsed
              ? "flex items-center justify-center py-3 rounded-xl bg-slate-700 hover:bg-slate-600 text-slate-200 transition mb-3"
              : "flex items-center gap-3 px-4 py-3 rounded-xl bg-slate-700 hover:bg-slate-600 text-slate-200 text-base font-semibold transition mb-3"
          }
        >
          <Image
            src="/Cyber2_Logo_White.svg"
            alt="Cyber² Utility"
            width={collapsed ? 24 : 22}
            height={collapsed ? 24 : 22}
            priority
            style={{ width: collapsed ? "24px" : "22px", height: "auto" }}
          />

          {!collapsed && (
            <span className="insyt-workspace">
              Cyber² Utility
            </span>
          )}
        </Link>
      </div>

      <nav className="space-y-3 overflow-y-auto pr-1 flex-1">
        {navItems.map((item) => {
          const active = pathname === item.href.split("?")[0];
          const Icon = item.icon;

          return (
            <Link
              key={item.href}
              href={item.href}
              title={collapsed ? item.label : undefined}
              className={
                active
                  ? collapsed
                    ? "flex items-center justify-center py-3 rounded-xl bg-teal-600 text-white"
                    : "flex items-center gap-3 px-4 py-3 rounded-xl bg-teal-600 text-white"
                  : collapsed
                    ? "flex items-center justify-center py-3 rounded-xl hover:bg-slate-800 text-slate-300"
                    : "flex items-center gap-3 px-4 py-3 rounded-xl hover:bg-slate-800 text-slate-300"
              }
            >
              <Icon size={collapsed ? 24 : 20} />

              {!collapsed && (
                <span className="insyt-workspace">
                  {item.label}
                </span>
              )}
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}