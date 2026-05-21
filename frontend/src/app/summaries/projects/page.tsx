"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { apiGet } from "../../../lib/api";
import AppShell from "../../../components/AppShell";

function SummariesProjectsPageContent() {
  const router = useRouter();
  const [projects, setProjects] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function loadProjects() {
      try {
        const data = await apiGet("/api/summaries/projects/");

        setProjects(data.projects || []);
      } catch (error) {
        console.error("Failed to load summaries projects", error);
        setProjects([]);
      } finally {
        setLoading(false);
      }
    }

    loadProjects();
  }, []);

  function openProject(project: string) {
    localStorage.setItem("insyt_selected_project", project);
    router.push(`/summaries/review?project=${encodeURIComponent(project)}`);
  }

  return (
    <AppShell>
      <main className="p-8 text-white">
        <h1 className="text-3xl font-bold mb-2">INSYT Summaries Projects</h1>

        <p className="text-slate-400 mb-6">
          Select a project from Azure Storage container: insyt-summaries.
        </p>

        {loading ? (
          <div className="text-slate-400">Loading projects...</div>
        ) : projects.length === 0 ? (
          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 text-slate-400">
            No Summaries projects found.
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {projects.map((project) => (
              <button
                key={project}
                type="button"
                onClick={() => openProject(project)}
                className="bg-slate-900 border border-slate-800 rounded-2xl p-6 text-left hover:border-sky-500"
              >
                <div className="text-xl font-bold">{project}</div>
                <div className="text-slate-400 text-sm mt-2">
                  Open Summaries review workspace
                </div>
              </button>
            ))}
          </div>
        )}
      </main>
    </AppShell>
  );
}

export default function SummariesProjectsPage() {
  return (
    <Suspense fallback={<div>Loading...</div>}>
      <SummariesProjectsPageContent />
    </Suspense>
  );
}






