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
  format: string;
  notes: string;
};

type ProtocolResponse = {
  protocol_blob: string | null;
  protocol?: {
    protocol_template?: string;
    fields?: ProtocolField[];
  };
  message?: string;
};

function CaptureProtocolPageContent() {
  const searchParams = useSearchParams();
  const projectId = searchParams.get("project");

  const [protocol, setProtocol] = useState<ProtocolResponse | null>(null);
  const [message, setMessage] = useState("");

  useEffect(() => {
    if (!projectId) {
      setMessage("Select a project to view its protocol.");
      return;
    }

    apiGet(`/api/capture/projects/${projectId}/protocol`)
      .then((response) => {
        setProtocol(response);
        setMessage("");
      })
      .catch((error) => {
        console.error(error);
        setMessage("Failed to load protocol.");
      });
  }, [projectId]);

  const fields = protocol?.protocol?.fields || [];

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
          <p className="text-sm text-sky-700 mb-6">
            {message}
          </p>
        )}

        <ContentCard title="Project Protocol">
          {!projectId ? (
            <p className="text-slate-400">
              No project selected.
            </p>
          ) : !protocol?.protocol_blob ? (
            <p className="text-slate-400">
              No saved protocol found for this project.
            </p>
          ) : (
            <>
              <div className="mb-6">
                <p className="text-sm text-slate-400">
                  Protocol Template
                </p>

                <p className="insyt-workspace text-xl font-semibold text-white">
                  {protocol.protocol?.protocol_template || "—"}
                </p>
              </div>

              <div className="bg-slate-950 border border-slate-800 rounded-xl overflow-auto max-h-[70vh]">
                <table className="w-full text-xs table-auto">
                  <thead className="bg-slate-900 text-slate-400 sticky top-0 z-20">
                    <tr>
                      <th className="p-3 text-left">Section</th>
                      <th className="p-3 text-left">Data Element</th>
                      <th className="p-3 text-left">Capture Type</th>
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
                          {field.format}
                        </td>

                        <td className="p-3 text-slate-400">
                          {field.notes || "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </ContentCard>
      </PageContainer>
    </AppShell>
  );
}

export default function Page() {
  return (
    <Suspense fallback={<div>Loading...</div>}>
      <CaptureProtocolPageContent />
    </Suspense>
  );
}

