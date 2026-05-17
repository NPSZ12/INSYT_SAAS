"use client";

import { useRouter } from "next/navigation";
import Button from "../../components/Button";

export default function LauncherPage() {
  const router = useRouter();

  const apps = [
    {
      name: "INSYT Capture",
      description:
        "Protocol-driven breach and entity capture workflows.",
      path: "/login?next=/capture",
    },
    {
      name: "INSYT Discovery",
      description:
        "eDiscovery processing, review, and production workflows.",
      path: "/login?next=/discovery",
    },
    {
      name: "INSYT Summaries",
      description:
        "Medical, deposition, and litigation summary workflows.",
      path: "/login?next=/summaries",
    },
    {
      name: "INSYT Developer",
      description:
        "Internal tools, configuration, and system utilities.",
      path: "/login?next=/developer",
    },
  ];

  return (
    <main className="min-h-screen bg-slate-950 text-white p-10">
      <div className="mb-10">
        <img
          src="/insyt360_logo.png"
          alt="INSYT360"
          className="h-16 w-auto"
        />

        <p className="text-slate-400 text-base mt-3 font-medium">
          Powered by Cyber Discovery Solutions
        </p>

        <p className="text-slate-400 mt-4 text-lg">
          Select a workspace to continue.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-8 max-w-6xl">
        {apps.map((app) => (
          <div
            key={app.name}
            className="bg-slate-900 border border-slate-800 rounded-3xl p-8 hover:border-teal-500 transition min-h-[260px] flex flex-col justify-between shadow-xl"
          >
            <h2 className="text-3xl font-bold mb-4">
              {app.name}
            </h2>

            <p className="text-slate-400 text-base leading-relaxed min-h-[90px]">
              {app.description}
            </p>

            <div className="mt-6">
              <Button
                fullWidth
                onClick={() => router.push(app.path)}
              >
                Open
              </Button>
            </div>
          </div>
        ))}
      </div>
    </main>
  );
}