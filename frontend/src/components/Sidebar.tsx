"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import {
  LayoutDashboard,
  FolderKanban,
  FileSearch,
  ShieldCheck,
  Settings,
  MessageSquare,
  Clock,
  Database,
  Layers,
  Search,
  FileText,
  Users,
} from "lucide-react";


type StoredUser = {
  username: string;
  display_name: string;
  role: string;
};

export default function Sidebar() {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const queryProject = searchParams.get("project");
  const storedProject =
    typeof window !== "undefined"
      ? localStorage.getItem("insyt_selected_project")
      : "";

  const selectedProject = queryProject || storedProject;
  const selectedBatch = searchParams.get("batch");

  const [role, setRole] = useState("");

  useEffect(() => {
    const storedUser = localStorage.getItem("insyt_user");

    if (storedUser) {
      const user: StoredUser = JSON.parse(storedUser);
      setRole(user.role);
    }
  }, []);

  const projectQuery = selectedProject
    ? `?project=${selectedProject}${selectedBatch ? `&batch=${selectedBatch}` : ""}`
    : "";

  const reviewerNavItems = selectedProject
    ? [
        {
          label: "Dashboard",
          href: `/project-dashboard${projectQuery}`,
          icon: LayoutDashboard,
        },
        {
          label: "Batches",
          href: `/batches${projectQuery}`,
          icon: Layers,
        },
        {
          label: "Search Folders",
          href: `/search-folders${projectQuery}`,
          icon: Search,
        },
        {
          label: "Review",
          href: `/review${projectQuery}`,
          icon: FileSearch,
        },
        {
          label: "Captured Entities",
          href: `/captured-entities${projectQuery}`,
          icon: Database,
        },
        {
          label: "Timesheet",
          href: `/timesheet${projectQuery}`,
          icon: Clock,
        },
        {
          label: "Messaging",
          href: `/messaging${projectQuery}`,
          icon: MessageSquare,
        },
        {
          label: "Projects",
          href: "/projects",
          icon: FolderKanban,
        },
      ]
    : [
        {
          label: "Projects",
          href: "/projects",
          icon: FolderKanban,
        },
      ];

  const adminNavItems = selectedProject
    ? [
        {
          label: "Dashboard",
          href: `/project-dashboard${projectQuery}`,
          icon: LayoutDashboard,
        },
        {
          label: "Projects",
          href: "/projects",
          icon: FolderKanban,
        },
        {
          label: "Files",
          href: `/files${projectQuery}`,
          icon: FileText,
        },
        {
          label: "Batches",
          href: `/batches${projectQuery}`,
          icon: Layers,
        },
        {
          label: "Search Folders",
          href: `/search-folders${projectQuery}`,
          icon: Search,
        },
        {
          label: "Review",
          href: `/review${projectQuery}`,
          icon: FileSearch,
        },
        {
          label: "Captured Entities",
          href: `/captured-entities${projectQuery}`,
          icon: Database,
        },
        {
          label: "Timesheet",
          href: `/timesheet${projectQuery}`,
          icon: Clock,
        },
        {
          label: "Messaging",
          href: `/messaging${projectQuery}`,
          icon: MessageSquare,
        },
        {
          label: "User Access",
          href: "/user-access",
          icon: Users,
        },
        {
          label: "Admin",
          href: "/admin",
          icon: ShieldCheck,
        },
        {
          label: "Settings",
          href: "/settings",
          icon: Settings,
        },
      ]
    : [
        {
          label: "Dashboard",
          href: "/dashboard",
          icon: LayoutDashboard,
        },
        {
          label: "Projects",
          href: "/projects",
          icon: FolderKanban,
        },
        {
          label: "User Access",
          href: "/user-access",
          icon: Users,
        },
        {
          label: "Admin",
          href: "/admin",
          icon: ShieldCheck,
        },
        {
          label: "Settings",
          href: "/settings",
          icon: Settings,
        },
      ];

  const navItems =
    role === "1L Reviewer"
      ? reviewerNavItems
      : adminNavItems;

  return (
    <aside className="w-72 bg-slate-900 border-r border-slate-800 p-6 min-h-screen">
      <h1 className="text-3xl font-bold tracking-tight mb-10 text-white">
        INSYT
      </h1>

      <nav className="space-y-3">
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
              <span>{item.label}</span>
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}