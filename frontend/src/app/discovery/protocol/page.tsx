"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";

import AppShell from "../../../components/AppShell";
import PageContainer from "../../../components/PageContainer";
import PageHeader from "../../../components/PageHeader";
import ContentCard from "../../../components/ContentCard";
import { apiGet } from "../../../lib/api";

type ProtocolField = {
  section: string;
  data_element: string;
  default_format?: string;
  format?: string;
  notes: string;
};

type SavedProtocolResponse = {
  project_id: string;
  has_protocol: boolean;
  protocol_blob_path: string | null;
  protocol_filename: string | null;
  protocol_template?: string;
  last_modified?: string | null;
  size?: number | null;
  protocol?: {
    protocol_template?: string;
    fields?: ProtocolField[];
  };
  fields?: ProtocolField[];
  message?: string;
};

function DiscoveryProtocolPageContent() {
  const searchParams = useSearchParams();
  const projectId = searchParams.get("project");

  const [protocol, setProtocol] = useState<SavedProtocolResponse | null>(null);
  const [message, setMessage] = useState("");

  useEffect(() => {
    if (!projectId) {
      setProtocol(null);
      setMessage("Select a project to view its protocol.");
      return;
    }

    setProtocol(null);
    setMessage("Loading saved protocol...");

    apiGet(`/api/discovery/projects/${encodeURIComponent(projectId)}/protocol`)
      .then((response: SavedProtocolResponse) => {
        setProtocol(response);
        setMessage("");
      })
      .catch((error) => {
        console.error(error);
        setProtocol(null);
        setMessage("Failed to load protocol.");
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
          title="Protocol"
          subtitle={
            projectId
              ? `Saved protocol for ${projectId.replaceAll("_", " ")}.`
              : "Select a project to view its saved protocol."
          }
        />

        {message && (
          <p className="text-sm text-sky-400 mb-6">
            {message}
          </p>
        )}

        <ContentCard title="Project Protocol">
          {!projectId ? (
            <p className="text-slate-400">
              No project selected.
            </p>
          ) : protocol && !protocol.has_protocol ? (
            <p className="text-slate-400">
              No saved protocol found for this project.
            </p>
          ) : protocol?.has_protocol ? (
            <>
              <div className="mb-6 rounded-xl border border-slate-800 bg-slate-950 p-4">
                <p className="text-sm text-slate-400">
                  Saved Protocol
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
                  Protocol file found, but no protocol fields were returned.
                </p>
              ) : (
                <div className="bg-slate-950 border border-slate-800 rounded-xl overflow-auto max-h-[70vh]">
                  <table className="w-full text-xs table-auto">
                    <thead className="bg-slate-900 text-slate-400 sticky top-0 z-20">
                      <tr>
                        <th className="p-3 text-left">Section</th>
                        <th className="p-3 text-left">Data Element</th>
                        <th className="p-3 text-left">discovery Type</th>
                        <th className="p-3 text-left">Notes</th>
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
              Loading protocol...
            </p>
          )}
        </ContentCard>
      </PageContainer>
    </AppShell>
  );
}

export default function Page() {
  return (
    <Suspense fallback={<div>Loading...</div>}>
      <DiscoveryProtocolPageContent />
    </Suspense>
  );
}
