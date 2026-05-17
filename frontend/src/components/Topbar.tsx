"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Button from "./Button";

type StoredUser = {
  username: string;
  display_name: string;
  role: string;
};

export default function Topbar() {
  const router = useRouter();
  const [user, setUser] = useState<StoredUser | null>(null);
  const [selectedProject, setSelectedProject] = useState("");

  useEffect(() => {
    const storedUser = localStorage.getItem("insyt_user");

    if (storedUser) {
      setUser(JSON.parse(storedUser));
    }
    const storedProject = localStorage.getItem("insyt_selected_project");

    if (storedProject) {
      setSelectedProject(storedProject);
    }
  }, []);

  function handleLogout() {
    localStorage.removeItem("insyt_access_token");
    localStorage.removeItem("insyt_user");
    router.push("/launcher");
  }

  return (
    <header className="relative h-16 bg-slate-950 border-b border-slate-800 px-8 flex items-center justify-between">
      <div className="flex flex-col items-start leading-tight">
        <p className="text-sm text-slate-400">
          INSYT360™
        </p>

        <h2 className="text-xl font-bold text-white">
          INSYT™ Capture
        </h2>
      </div>

      {selectedProject && (
        <div className="absolute left-[42%] -translate-x-1/2 text-left">
          <p className="text-xs text-slate-500">
            Selected Project
          </p>

          <p className="text-2xl font-bold text-teal-400 tracking-wide">
            {selectedProject.replaceAll("_", " ")}
          </p>
        </div>
      )}

      <div className="flex items-center gap-4">
        <span className="text-sm text-slate-400">Environment: Local Dev</span>

        <div className="bg-slate-900 border border-slate-800 px-4 py-2 rounded-xl text-sm text-white">
          {user ? (
            <div className="leading-tight">
              <p className="font-medium">
                {user.display_name}
              </p>

              <p className="text-xs text-slate-400">
                INSYT360
              </p>
            </div>
          ) : (
            "Loading..."
          )}
        </div>

        <Button variant="secondary" onClick={handleLogout}>
          Logout
        </Button>
      </div>
    </header>
  );
}