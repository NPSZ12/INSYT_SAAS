"use client";

import { useEffect, useState } from "react";
import {
  useRouter,
  usePathname,
  useSearchParams,
} from "next/navigation";

import Button from "./Button";

type StoredUser = {
  username: string;
  display_name: string;
  role: string;
};

function getWorkspaceName(pathname: string) {
  if (pathname.startsWith("/summaries")) {
    return "INSYT Summaries";
  }

  if (pathname.startsWith("/discovery")) {
    return "INSYT Discovery";
  }

  return "INSYT Capture";
}

export default function Topbar() {
  const router = useRouter();

  const pathname = usePathname();
  const searchParams = useSearchParams();

  const [user, setUser] =
    useState<StoredUser | null>(null);

  /**
   * IMPORTANT:
   * Only use actual URL project selection.
   * Do NOT use localStorage fallback here.
   */
  const selectedProject =
    searchParams.get("project");

  const workspaceName =
    getWorkspaceName(pathname);

  useEffect(() => {
    const storedUser =
      localStorage.getItem("insyt_user");

    if (storedUser) {
      setUser(JSON.parse(storedUser));
    }
  }, []);

  function handleLogout() {
    localStorage.removeItem("insyt_access_token");
    localStorage.removeItem("insyt_user");
    localStorage.removeItem("insyt_selected_project");

    sessionStorage.clear();

    router.push("/login");
  }

  return (
    <header className="relative h-16 bg-slate-950 border-b border-slate-800 px-8 flex items-center justify-between">

      {/* LEFT */}
      <div className="flex flex-col items-start leading-tight">

        <div className="text-xs uppercase tracking-[0.18em] text-slate-500 mb-1">
          Workspace
        </div>

        <h1 className="insyt-workspace text-2xl font-bold">
          <span className="text-white">I</span>
          <span className="text-sky-400">N</span>
          <span className="text-white">SYT</span>
          <span className="text-sky-400">
            {workspaceName.replace("INSYT", "")}
          </span>
        </h1>

      </div>

      {/* CENTER */}
      {selectedProject && (
        <div className="absolute left-1/2 -translate-x-1/2 text-center">

          <p className="text-xs text-slate-500">
            Selected Project
          </p>

          <p className="insyt-project text-2xl font-bold text-sky-400 tracking-wide">
            {selectedProject.replaceAll("_", " ")}
          </p>

        </div>
      )}

      {/* RIGHT */}
      <div className="flex items-center gap-4">

        <span className="text-sm text-slate-400">
          Environment: Local Dev
        </span>

        <div className="bg-slate-900 border border-slate-800 px-4 py-2 rounded-xl text-sm text-white">
          {user ? (
            <div className="leading-tight">

              <p className="font-medium">
                {user.display_name}
              </p>

              <p className="text-xs text-slate-400">
                {user.role}
              </p>

            </div>
          ) : (
            "Loading..."
          )}
        </div>

        <Button
          variant="secondary"
          onClick={handleLogout}
        >
          Logout
        </Button>

      </div>

    </header>
  );
}








