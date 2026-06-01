"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";

import AppShell from "../../components/AppShell";
import PageContainer from "../../components/PageContainer";
import PageHeader from "../../components/PageHeader";
import ContentCard from "../../components/ContentCard";
import { apiGet } from "../../lib/api";

type ReviewHoursRow = {
  week_ending: string;
  username: string;
  display_name: string;
  role: string;
  total_hours: number;
};

function prettyWorkspace(workspace: string) {
  if (workspace === "capture") return "INSYT Capture";
  if (workspace === "discovery") return "INSYT Discovery";
  if (workspace === "summaries") return "INSYT Summaries";
  if (workspace === "development") return "INSYT Development";

  return workspace || "Workspace";
}

function ReviewHoursPageContent() {
  const searchParams = useSearchParams();

  const workspace = searchParams.get("workspace") || "";
  const client = searchParams.get("client") || "";
  const project = searchParams.get("project") || "";

  const [rows, setRows] = useState<ReviewHoursRow[]>([]);
  const [message, setMessage] = useState("");

  function loadRows() {
    if (!workspace || !client || !project) {
      setMessage("Missing workspace, client, or project.");
      return;
    }

    const query = new URLSearchParams({
      workspace,
      client,
      project,
    });

    apiGet(`/api/admin/review-hours?${query.toString()}`)
      .then((response: any) => {
        setRows(response.rows || []);
      })
      .catch((error) => {
        console.error(error);
        setMessage("Failed to load review hours.");
      });
  }

  useEffect(() => {
    loadRows();
  }, [workspace, client, project]);

  return (
    <AppShell>
      <PageContainer>
        <PageHeader
          title="Review Hours"
          subtitle={`${prettyWorkspace(workspace)} • ${client || "Client"} • ${
            project ? project.replaceAll("_", " ") : "Project"
          }`}
        />

        {message && (
          <p className="mb-6 text-sm text-sky-400">
            {message}
          </p>
        )}

        <ContentCard title="Weekly User Hours">
          <div className="overflow-auto rounded-xl border border-slate-800">
            <table className="w-full text-sm">
              <thead className="bg-slate-900 text-slate-400">
                <tr>
                  <th className="p-3 text-left">End of Week</th>
                  <th className="p-3 text-left">User</th>
                  <th className="p-3 text-left">Role</th>
                  <th className="p-3 text-right">Hours</th>
                </tr>
              </thead>

              <tbody>
                {rows.map((row) => (
                  <tr
                    key={`${row.week_ending}-${row.username}-${row.role}`}
                    className="border-t border-slate-800"
                  >
                    <td className="p-3 text-slate-300">
                      {row.week_ending || "—"}
                    </td>

                    <td className="p-3 text-white">
                      <div>{row.display_name || row.username}</div>
                      <div className="text-xs text-slate-500">
                        {row.username}
                      </div>
                    </td>

                    <td className="p-3 text-slate-300">
                      {row.role}
                    </td>

                    <td className="p-3 text-right text-slate-300">
                      {Number(row.total_hours || 0).toFixed(2)}
                    </td>
                  </tr>
                ))}

                {rows.length === 0 && (
                  <tr>
                    <td
                      colSpan={4}
                      className="p-6 text-center text-slate-500"
                    >
                      No review hours found for this project.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </ContentCard>
      </PageContainer>
    </AppShell>
  );
}

export default function ReviewHoursPage() {
  return (
    <Suspense fallback={<div>Loading review hours...</div>}>
      <ReviewHoursPageContent />
    </Suspense>
  );
}