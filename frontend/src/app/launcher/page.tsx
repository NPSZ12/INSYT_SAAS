"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
// import Image from "next/image";

import Button from "../../components/Button";

type StoredUser = {
  username: string;
  display_name?: string;
  role?: string;
  workspace_access?: string[];
};

type LauncherApp = {
  key: string;
  name: string;
  description: string;
  path: string;
  requiresLogin: boolean;
  buttonLabel?: string;
};

export default function LauncherPage() {
  const router = useRouter();
  const [user, setUser] = useState<StoredUser | null>(null);

  useEffect(() => {
    const storedUser = localStorage.getItem("insyt_user");

    if (!storedUser) {
      return;
    }

    try {
      setUser(JSON.parse(storedUser));
    } catch (error) {
      console.error("Unable to parse stored INSYT user.", error);
      localStorage.removeItem("insyt_user");
    }
  }, []);

  const apps: LauncherApp[] = [
    {
      key: "advantage",
      name: "INSYT Advantage",
      description:
        "Explore the INSYT360 platform, products, industries, pricing, and real-world solutions.",
      path: "/advantage",
      requiresLogin: true,
      buttonLabel: "Explore INSYT360",
    },
    {
      key: "capture",
      name: "INSYT Capture",
      description: "Protocol-driven breach and entity capture workflows.",
      path: "/capture/projects",
      requiresLogin: true,
    },
    {
      key: "discovery",
      name: "INSYT Discovery",
      description: "eDiscovery processing, review, and production workflows.",
      path: "/discovery/projects",
      requiresLogin: true,
    },
    {
      key: "summaries",
      name: "INSYT Summaries",
      description: "Medical, deposition, and litigation summary workflows.",
      path: "/summaries/projects",
      requiresLogin: true,
    },
  ];

  function hasWorkspaceAccess(appKey: string) {
    if (!user) {
      return false;
    }

    if (user.role === "INSYT Admin" || user.role === "CDS Admin") {
      return true;
    }

    return user.workspace_access?.includes(appKey) ?? false;
  }

  function openApp(app: LauncherApp) {
    if (!app.requiresLogin) {
      router.push(app.path);
      return;
    }

    if (!user) {
      router.push(
        `/login?next=${encodeURIComponent(app.path)}`
      );
      return;
    }

    router.push(app.path);
  }

  return (
    <main className="min-h-screen bg-slate-950 p-10 text-white">
      <div className="mb-10">
        <div className="flex flex-col items-start">
          <div className="mb-2 flex items-end gap-0.5">
            <span className="insyt-brand text-5xl font-bold text-white">
              I
            </span>

            <span className="insyt-brand text-5xl font-bold text-sky-400">
              N
            </span>

            <span className="insyt-brand text-5xl font-bold text-white">
              SYT
            </span>

            <span className="insyt-brand mb-[0.11em] text-[2.1em] font-bold leading-none text-sky-400">
              360
            </span>
          </div>

          {/*
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
            */}
        </div>

        <div className="mt-3 text-center">
          <p className="text-lg text-slate-400">
            Explore the INSYT360 Platform Advantage or Select a Workspace to Begin.
          </p>
        </div>
      </div>

      <div className="mx-auto mt-2 grid max-w-7xl grid-cols-1 gap-6 md:grid-cols-3">
        {apps.map((app) => {
          const loggedIn = Boolean(user);

          const allowed =
            !app.requiresLogin ||
            !loggedIn ||
            hasWorkspaceAccess(app.key);

          const isAdvantage = app.key === "advantage";

          return (
            <div
              key={app.key}
              className={`flex min-h-[230px] flex-col justify-between rounded-3xl border bg-slate-900 p-6 shadow-xl transition ${
                isAdvantage
                  ? "md:col-span-3 md:mx-auto md:w-full md:max-w-4xl border-sky-500/60"
                  : "border-slate-800"
              } ${
                allowed
                  ? "hover:border-sky-500"
                  : ""
              }`}
            >
              <h2
                className={`insyt-workspace mb-4 font-bold ${
                  isAdvantage
                    ? "text-center text-4xl"
                    : "text-3xl"
                }`}
              >
                <span className="text-white">I</span>
                <span className="text-sky-400">N</span>
                <span className="text-white">SYT</span>
                <span className="text-sky-400">
                  {app.name.replace("INSYT", "")}
                </span>
              </h2>

              <p
                className={`text-base leading-relaxed text-slate-400 ${
                  isAdvantage
                    ? "mx-auto min-h-[70px] max-w-3xl text-center"
                    : "min-h-[90px]"
                }`}
              >
                {app.description}
              </p>

              {!allowed && (
                <div className="flex flex-1 flex-col items-center justify-center text-center">
                  <p className="text-base font-semibold text-slate-300">
                    Current Access Restricted.
                  </p>

                  <p className="mt-1 text-sm text-slate-400">
                    Please contact an INSYT Administrator for assistance.
                  </p>
                </div>
              )}

              {allowed && (
                <div
                  className={
                    isAdvantage
                      ? "mx-auto mt-6 w-full max-w-md"
                      : "mt-6"
                  }
                >
                  <Button
                    fullWidth
                    unstyled={isAdvantage}
                    className={
                      isAdvantage
                        ? "insyt-workspace w-full rounded-xl border-2 border-white bg-white px-5 py-3.5 text-lg font-bold tracking-wide text-sky-600 shadow-lg shadow-black/20 transition-all duration-150 hover:border-sky-300 hover:bg-sky-50 hover:text-sky-500 hover:shadow-xl hover:shadow-sky-950/30 active:scale-[0.98] active:bg-sky-100 focus:outline-none focus:ring-2 focus:ring-sky-400 focus:ring-offset-2 focus:ring-offset-slate-950"
                        : ""
                    }
                    onClick={() => openApp(app)}
                  >
                    {app.buttonLabel ??
                      (loggedIn ? "Open" : "Sign In")}
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