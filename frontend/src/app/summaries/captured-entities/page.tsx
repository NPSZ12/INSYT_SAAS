"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams, useRouter } from "next/navigation";

import AppShell from "../../../components/AppShell";
import PageContainer from "../../../components/PageContainer";
import PageHeader from "../../../components/PageHeader";
import ContentCard from "../../../components/ContentCard";
import { apiGet } from "../../../lib/api";

type SummariesEntitiesResponse = {
  headers: string[];
  rows: Record<string, string>[];
};

function SummariesEntitiesPageContent() {
  const searchParams = useSearchParams();
  const router = useRouter();

  const clientId = searchParams.get("client") || "";
  const projectId = searchParams.get("project") || "";
  const batchId = searchParams.get("batch") || "";

  const [data, setData] = useState<SummariesEntitiesResponse>({
    headers: [],
    rows: [],
  });

  useEffect(() => {
    if (!projectId) return;

    const batchQuery = batchId
      ? `&batch=${encodeURIComponent(batchId)}`
      : "";

    apiGet(
      `/api/entities?project=${encodeURIComponent(projectId)}${batchQuery}`
    )
      .then((response: any) => {
        setData({
          headers: response?.headers || [],
          rows: response?.rows || [],
        });
      })
      .catch((error: any) => {
        console.error(error);
        setData({
          headers: [],
          rows: [],
        });
      });
  }, [projectId, batchId]);

  if (!projectId) {
    return (
      <AppShell>
        <PageContainer>
          <PageHeader
            title="No Project Selected"
            subtitle="Return to Projects and select a project first."
          />
        </PageContainer>
      </AppShell>
    );
  }

  function openDocument(docId: string) {
    const params = new URLSearchParams();

    if (clientId) {
      params.set("client", clientId);
    }

    if (projectId) {
      params.set("project", projectId);
    }

    if (batchId) {
      params.set("batch", batchId);
    }

    if (docId) {
      params.set("doc", docId);
    }

    router.push(`/summaries/review/doc?${params.toString()}`);
  }

  return (
    <AppShell>
      <PageContainer>
        <PageHeader
          title="Summary Data Points"
          subtitle={`Protocol-aligned summary data for ${projectId.replaceAll(
            "_",
            " "
          )}${batchId ? ` / ${batchId.replaceAll("_", " ")}` : ""}.`}
        />

        <ContentCard title="Summary Data Table">
          {data.rows.length === 0 ? (
            <p className="text-slate-500">
              No summary data points found for this project/batch.
            </p>
          ) : (
            <div className="bg-slate-950 border border-slate-800 rounded-xl overflow-auto max-h-[70vh]">
              <table className="min-w-max w-full text-xs">
                <thead className="bg-slate-900 text-slate-400 sticky top-0 z-20">
                  <tr>
                    {data.headers.map((header, index) => (
                      <th
                        key={header}
                        className={
                          index === 0
                            ? "p-3 text-left sticky left-0 bg-slate-900 z-10 whitespace-nowrap"
                            : "p-3 text-left border-l border-slate-800 whitespace-nowrap"
                        }
                      >
                        {header}
                      </th>
                    ))}
                  </tr>
                </thead>

                <tbody>
                  {data.rows.map((row, rowIndex) => (
                    <tr
                      key={rowIndex}
                      className="border-t border-slate-800"
                    >
                      {data.headers.map((header, index) => {
                        const value = row[header] || "";

                        if (header === "Doc ID") {
                          return (
                            <td
                              key={header}
                              className="p-3 sticky left-0 bg-slate-950 z-10 whitespace-nowrap"
                            >
                              <button
                                type="button"
                                className="text-sky-400 hover:text-sky-300 underline"
                                onClick={() => openDocument(value)}
                              >
                                {value || "Open Doc"}
                              </button>
                            </td>
                          );
                        }

                        return (
                          <td
                            key={header}
                            className="p-3 text-slate-300 border-l border-slate-800 whitespace-nowrap"
                          >
                            {value}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </ContentCard>
      </PageContainer>
    </AppShell>
  );
}

export default function SummariesEntitiesPage() {
  return (
    <Suspense fallback={<div>Loading summary data...</div>}>
      <SummariesEntitiesPageContent />
    </Suspense>
  );
}