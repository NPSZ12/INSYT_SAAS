"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Image from "next/image";
import Button from "../../components/Button";

type StoredUser = {
  username: string;
  display_name?: string;
  role?: string;
  workspace_access?: string[];
};

export default function LauncherPage() {
  const router = useRouter();
  const [user, setUser] = useState<StoredUser | null>(null);

  useEffect(() => {
    const storedUser = localStorage.getItem("insyt_user");

    if (storedUser) {
      setUser(JSON.parse(storedUser));
    }
  }, []);

  const apps = [
    {
      key: "capture",
      name: "INSYT Capture",
      description: "Protocol-driven breach and entity capture workflows.",
      path: "/capture/projects",
    },
    {
      key: "discovery",
      name: "INSYT Discovery",
      description: "eDiscovery processing, review, and production workflows.",
      path: "/discovery/projects",
    },
    {
      key: "summaries",
      name: "INSYT Summaries",
      description: "Medical, deposition, and litigation summary workflows.",
      path: "/summaries/projects",
    },
    {
      key: "developer",
      name: "INSYT Developer",
      description: "Internal tools, configuration, and system utilities.",
      path: "/developer",
    },
  ];

  function hasWorkspaceAccess(appKey: string) {
    if (!user) return false;

    if (user.role === "INSYT Admin" || user.role === "CDS Admin") {
      return true;
    }

    return user.workspace_access?.includes(appKey);
  }

  return (
    <main className="min-h-screen bg-slate-950 text-white p-10">
      <div className="mb-10">
        <div className="flex flex-col items-start">
          <div className="flex items-end gap-0.5 mb-2">
            <span className="insyt-brand text-5xl font-bold text-white">I</span>
            <span className="insyt-brand text-5xl font-bold text-sky-400">N</span>
            <span className="insyt-brand text-5xl font-bold text-white">SYT</span>
            <span className="insyt-brand text-[2.1em] leading-none mb-[0.11em] text-sky-400 font-bold">
              360
            </span>
          </div>

          <div className="flex items-center gap-3 mt-1">
            <span className="text-slate-300 text-xl font-medium">
              Powered by:
            </span>

            <Image
              src="/CDS_Logo_W.svg"
              alt="Cyber Discovery Solutions"
              width={195}
              height={45}
              priority
              style={{ width: "260px", height: "auto" }}
            />
          </div>
        </div>

        <div className="text-center mt-3">
          <p className="text-slate-400 text-lg">
            Select a workspace to continue.
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 max-w-4xl mx-auto mt-2">
        {apps.map((app) => {
          const allowed = hasWorkspaceAccess(app.key);

          return (
            <div
              key={app.name}
              className={`bg-slate-900 border border-slate-800 rounded-3xl p-6 transition min-h-[230px] flex flex-col justify-between shadow-xl ${
                allowed ? "hover:border-sky-500" : ""
              }`}
            >
              <h2 className="insyt-workspace text-3xl font-bold mb-4">
                <span className="text-white">I</span>
                <span className="text-sky-400">N</span>
                <span className="text-white">SYT</span>
                <span className="text-sky-400">
                  {app.name.replace("INSYT", "")}
                </span>
              </h2>

              <p className="text-slate-400 text-base leading-relaxed min-h-[90px]">
                {app.description}
              </p>

              {!allowed && (
                <div className="flex-1 flex flex-col justify-center items-center text-center">
                  <p className="text-slate-300 font-semibold text-base">
                    Current Access Restricted.
                  </p>

                  <p className="text-slate-400 text-sm mt-1">
                    Please contact an INSYT Administrator for assistance.
                  </p>
                </div>
              )}

              {allowed && (
                <div className="mt-6">
                  <Button
                    fullWidth
                    onClick={() => router.push(app.path)}
                  >
                    Open
                  </Button>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </main>
  );
}