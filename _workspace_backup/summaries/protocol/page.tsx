"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";

import AppShell from "../../../components/AppShell";
import PageContainer from "../../../components/PageContainer";
import PageHeader from "../../../components/PageHeader";
import ContentCard from "../../../components/ContentCard";
import { apiGet } from "../../../lib/api";

type SummaryProtocolField = {
  section: string;
  data_element: string;
  default_format?: string;
  format?: string;
  notes: string;
};

type SavedSummaryProtocolResponse = {
  workspace?: string;
  project_id: string;
  has_protocol: boolean;
  protocol_blob: string | null;
  protocol_blob_path: string | null;
  protocol_filename: string | null;
  protocol_template?: string;
  last_modified?: string | null;
  size?: number | null;
  protocol?: {
    protocol_template?: string | null;
    fields?: SummaryProtocolField[];
  };
  fields?: SummaryProtocolField[];
  message?: string;
};

function SummariesProtocolPageContent() {
  const searchParams = useSearchParams();
  const projectId = searchParams.get("project");

  const [protocol, setProtocol] =
    useState<SavedSummaryProtocolResponse | null>(null);

  const [message, setMessage] = useState("");

  useEffect(() => {
    if (!projectId) {
      setProtocol(null);
      setMessage("Select a summary project to view its protocol.");
      return;
    }

    setProtocol(null);
    setMessage("Loading saved summary protocol...");

    apiGet(`/api/summaries/projects/${encodeURIComponent(projectId)}/protocol`)
      .then((response: SavedSummaryProtocolResponse) => {
        setProtocol(response);
        setMessage("");
      })
      .catch((error) => {
        console.error(error);
        setProtocol(null);
        setMessage("Failed to load summary protocol.");
      });
  }, [projectId]);

  const fields = protocol?.protocol?.fields || protocol?.fields || [];

  const protocolTemplate =
    protocol?.protocol?.protocol_template ||
    protocol?.protocol_template ||
    protocol?.protocol_filename ||
    "—";

  return (
    <AppShell>
      <PageContainer>
        <PageHeader
          title="Summary Protocol"
          subtitle={
            projectId
              ? `Saved summary protocol for ${projectId.replaceAll("_", " ")}.`
              : "Select a summary project to view its saved protocol."
          }
        />

        {message && (
          <p className="text-sm text-sky-400 mb-6">
            {message}
          </p>
        )}

        <ContentCard title="Summary Extraction Protocol">
          {!projectId ? (
            <p className="text-slate-400">
              No summary project selected.
            </p>
          ) : protocol && !protocol.has_protocol ? (
            <p className="text-slate-400">
              No saved summary protocol found for this project.
            </p>
          ) : protocol?.has_protocol ? (
            <>
              <div className="mb-6 rounded-xl border border-slate-800 bg-slate-950 p-4">
                <p className="text-sm text-slate-400">
                  Saved Summary Protocol
                </p>

                <p className="insyt-workspace text-xl font-semibold text-white mt-1">
                  {protocol.protocol_filename || protocolTemplate}
                </p>

                {protocol.protocol_blob_path && (
                  <p className="text-xs text-slate-500 mt-2 break-all">
                    {protocol.protocol_blob_path}
                  </p>
                )}

                {protocol.last_modified && (
                  <p className="text-xs text-slate-500 mt-1">
                    Last modified:{" "}
                    {new Date(protocol.last_modified).toLocaleString()}
                  </p>
                )}
              </div>

              {fields.length === 0 ? (
                <p className="text-slate-400">
                  Summary protocol file found, but no fields were returned.
                </p>
              ) : (
                <div className="bg-slate-950 border border-slate-800 rounded-xl overflow-auto max-h-[70vh]">
                  <table className="w-full text-xs table-auto">
                    <thead className="bg-slate-900 text-slate-400 sticky top-0 z-20">
                      <tr>
                        <th className="p-3 text-left">Summary Section</th>
                        <th className="p-3 text-left">Summary Data Element</th>
                        <th className="p-3 text-left">Capture Type</th>
                        <th className="p-3 text-left">Instructions</th>
                      </tr>
                    </thead>

                    <tbody>
                      {fields.map((field, index) => (
                        <tr
                          key={`${field.data_element}-${index}`}
                          className="border-t border-slate-800"
                        >
                          <td className="p-3 text-slate-300">
                            {field.section || "—"}
                          </td>

                          <td className="p-3 text-white">
                            {field.data_element}
                          </td>

                          <td className="p-3 text-slate-300">
                            {field.format || field.default_format || "—"}
                          </td>

                          <td className="p-3 text-slate-400">
                            {field.notes || "—"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </>
          ) : (
            <p className="text-slate-400">
              Loading summary protocol...
            </p>
          )}
        </ContentCard>
      </PageContainer>
    </AppShell>
  );
}

export default function Page() {
  return (
    <Suspense fallback={<div>Loading summary protocol...</div>}>
      <SummariesProtocolPageContent />
    </Suspense>
  );
}