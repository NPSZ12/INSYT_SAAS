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
      name: "Developer",
      description:
        "Internal tools, configuration, and system utilities.",
      path: "/login?next=/developer",
    },
  ];

  return (
    <main className="min-h-screen bg-slate-950 text-white p-10">
      <div className="mb-10">
        <h1 className="text-5xl font-bold">
          INSYT Platform
        </h1>

        <p className="text-slate-400 mt-3 text-lg">
          Select a workspace to continue.
        </p>
      </div>

      <div className="grid grid-cols-4 gap-6">
        {apps.map((app) => (
          <div
            key={app.name}
            className="bg-slate-900 border border-slate-800 rounded-2xl p-6 hover:border-teal-500 transition"
          >
            <h2 className="text-2xl font-semibold mb-3">
              {app.name}
            </h2>

            <p className="text-slate-400 min-h-20">
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