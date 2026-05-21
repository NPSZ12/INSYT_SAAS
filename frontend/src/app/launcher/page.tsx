"use client";

import { useRouter } from "next/navigation";
import Image from "next/image";
import Button from "../../components/Button";

export default function LauncherPage() {
  const router = useRouter();

  const apps = [
    {
      name: "INSYT Capture",
      description: "Protocol-driven breach and entity capture workflows.",
      path: "/capture/projects",
    },
    {
      name: "INSYT Discovery",
      description: "eDiscovery processing, review, and production workflows.",
      path: "/discovery/projects",
    },
    {
      name: "INSYT Summaries",
      description: "Medical, deposition, and litigation summary workflows.",
      path: "/summaries/projects",
    },
    {
      name: "INSYT Developer",
      description: "Internal tools, configuration, and system utilities.",
      path: "/developer",
    },
  ];

  return (
    <main className="min-h-screen bg-slate-950 text-white p-10">
      <div className="mb-10">
        <div className="flex flex-col items-start">
          <div className="flex items-end gap-0.5 mb-2">
            <span className="insyt-brand text-5xl font-bold text-white">
              I
            </span>

            <span className="insyt-brand text-5xl font-bold text-sky-700">
              N
            </span>

            <span className="insyt-brand text-5xl font-bold text-white">
              SYT
            </span>

            <span className="insyt-brand text-[2.1em] leading-none mb-[0.11em] text-sky-700 font-bold">
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
        {apps.map((app) => (
          <div
            key={app.name}
            className="bg-slate-900 border border-slate-800 rounded-3xl p-6 hover:border-sky-500 transition min-h-[230px] flex flex-col justify-between shadow-xl"
          >
            <h2 className="insyt-workspace text-3xl font-bold mb-4">
              <span className="text-white">I</span>
              <span className="text-sky-700">N</span>
              <span className="text-white">SYT</span>
              <span className="text-sky-700">
                {app.name.replace("INSYT", "")}
              </span>
            </h2>

            <p className="text-slate-400 text-base leading-relaxed min-h-[90px]">
              {app.description}
            </p>

            <div className="mt-6">
              <Button fullWidth onClick={() => router.push(app.path)}>
                Open
              </Button>
            </div>
          </div>
        ))}
      </div>
    </main>
  );
}








