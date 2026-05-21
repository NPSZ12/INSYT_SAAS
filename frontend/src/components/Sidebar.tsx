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
};

type NavItem = {
  label: string;
  href: string;
  icon: any;
};

export default function Sidebar() {
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const isSummaries = pathname.startsWith("/summaries");
  const isDiscovery = pathname.startsWith("/discovery");

  const workspaceBase = isSummaries
    ? "/summaries"
    : isDiscovery
      ? "/discovery"
      : "/capture";

  const projectsHref = `${workspaceBase}/projects`;

  const queryProject = searchParams.get("project");
  const selectedBatch = searchParams.get("batch");

  const [role, setRole] = useState("");

  useEffect(() => {
    const storedUser = localStorage.getItem("insyt_user");

    if (storedUser) {
      const user: StoredUser = JSON.parse(storedUser);
      setRole(user.role);
    }
  }, []);

  const projectQuery = queryProject
    ? `?project=${queryProject}${
        selectedBatch ? `&batch=${selectedBatch}` : ""
      }`
    : "";

  const normalizedRole = role.toLowerCase();

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
          label: "New Project",
          href: `${workspaceBase}/new-project`,
          icon: FolderPlus,
        },
        {
          label: "Clients",
          href: `${workspaceBase}/clients`,
          icon: Building2,
        },
        {
          label: "User Accounts",
          href: `${workspaceBase}/review-team`,
          icon: Users,
        },
        {
          label: "Project Hours",
          href: `${workspaceBase}/project-hours`,
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
    <aside className="w-72 bg-slate-900 border-r border-slate-800 p-6 min-h-screen h-screen flex flex-col">

      {/* TOP STATIC */}
      <div className="shrink-0">

        <div className="flex items-end gap-0.5 mb-4">
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
        </div>

        <Link
          href="/launcher"
          className="flex items-center gap-3 px-4 py-3 rounded-xl bg-slate-700 hover:bg-slate-600 text-slate-200 text-base font-semibold transition mb-3"
        >
          <Rocket size={20} />

          <span className="insyt-workspace">
            Launcher
          </span>
        </Link>

        <Link
          href={`/cyber-utility${projectQuery}`}
          className="flex items-center gap-3 px-4 py-3 rounded-xl bg-slate-700 hover:bg-slate-600 text-slate-200 text-base font-semibold transition mb-4"
        >
          <Image
            src="/Cyber2_Logo_White.svg"
            alt="Cyber² Utility"
            width={22}
            height={22}
            priority
            style={{ width: "22px", height: "auto" }}
          />

          <span className="insyt-workspace">
            Cyber² Utility
          </span>
        </Link>

      </div>

      {/* MIDDLE SCROLLABLE NAV */}
      <nav className="space-y-3 overflow-y-auto pr-1 flex-1">
        {navItems.map((item) => {
          const active = pathname === item.href.split("?")[0];
          const Icon = item.icon;

          return (
            <Link
              key={item.href}
              href={item.href}
              className={
                active
                  ? "flex items-center gap-3 px-4 py-3 rounded-xl bg-teal-600 text-white"
                  : "flex items-center gap-3 px-4 py-3 rounded-xl hover:bg-slate-800 text-slate-300"
              }
            >
              <Icon size={20} />

              <span className="insyt-workspace">
                {item.label}
              </span>
            </Link>
          );
        })}
      </nav>

    </aside>
  );
}