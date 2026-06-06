"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import AppShell from "./AppShell";
import PageContainer from "./PageContainer";
import PageHeader from "./PageHeader";
import ContentCard from "./ContentCard";
import { apiGet } from "../lib/api";

type Workspace = "capture" | "discovery" | "summaries";

type CapturedEntitiesResponse = {
  headers: string[];
  rows: Record<string, string>[];
};

type ProtocolField = {
  section?: string;
  data_element?: string;
  label?: string;
  name?: string;
  format?: string;
  notes?: string;
};

type ProtocolColumn = {
  header: string;
  group: string;
};

type ProtocolResponse = {
  has_protocol?: boolean;
  fields?: ProtocolField[];
  protocol?: {
    fields?: ProtocolField[];
  };
};

type CapturedEntitiesTableProps = {
  workspace: Workspace;
  title?: string;
  subtitlePrefix?: string;
};

function normalizeHeader(value: string) {
  return value.trim();
}

function uniqueHeaders(headers: string[]) {
  const seen = new Set<string>();
  const output: string[] = [];

  headers.forEach((header) => {
    const clean = normalizeHeader(header);

    if (!clean || seen.has(clean)) {
      return;
    }

    seen.add(clean);
    output.push(clean);
  });

  return output;
}

function getProtocolFields(response: ProtocolResponse): ProtocolField[] {
  return response.fields || response.protocol?.fields || [];
}

function getProtocolColumns(response: ProtocolResponse): ProtocolColumn[] {
  const fields = getProtocolFields(response);

  return fields
    .map((field) => {
      const header =
        field.data_element ||
        field.label ||
        field.name ||
        "";

      return {
        header: normalizeHeader(header),
        group: normalizeHeader(field.section || "Protocol"),
      };
    })
    .filter((column) => column.header);
}

function buildReviewHref(
  workspace: Workspace,
  clientId: string,
  projectId: string,
  batchId: string,
  docId: string
) {
  const params = new URLSearchParams();

  if (clientId) params.set("client", clientId);
  if (projectId) params.set("project", projectId);
  if (batchId) params.set("batch", batchId);
  if (docId) params.set("doc", docId);

  return `/${workspace}/review/doc?${params.toString()}`;
}

export default function CapturedEntitiesTable({
  workspace,
  title = "Captured Entities",
  subtitlePrefix = "Protocol-aligned captured entities",
}: CapturedEntitiesTableProps) {
  const searchParams = useSearchParams();
  const router = useRouter();

  const clientId = searchParams.get("client") || "";
  const projectId = searchParams.get("project") || "";
  const batchId = searchParams.get("batch") || "";

  const initialView =
    searchParams.get("view") === "final" ? "final" : "raw";

  const [entityView, setEntityView] =
    useState<"raw" | "final">(initialView);

  const [entityData, setEntityData] =
    useState<CapturedEntitiesResponse>({
      headers: [],
      rows: [],
    });

  const [protocolColumns, setProtocolColumns] =
    useState<ProtocolColumn[]>([]);

  const [message, setMessage] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    if (!projectId) return;

    setIsLoading(true);
    setMessage("");
    setProtocolColumns([]);
    setEntityData({
      headers: [],
      rows: [],
    });

    const protocolUrl =
      `/api/${workspace}/projects/${encodeURIComponent(
        projectId
      )}/protocol` +
      (clientId
        ? `?client=${encodeURIComponent(clientId)}`
        : "");

    apiGet(protocolUrl)
      .then((response: ProtocolResponse) => {
        setProtocolColumns(getProtocolColumns(response));
      })
      .catch((error) => {
        console.error(error);
        setMessage("Protocol headers could not be loaded.");
      });

    const batchQuery = batchId
      ? `&batch=${encodeURIComponent(batchId)}`
      : "";

    const clientQuery = clientId
      ? `client=${encodeURIComponent(clientId)}&`
      : "";

    const entitiesUrl =
      `/api/entities/?${clientQuery}workspace=${encodeURIComponent(
        workspace
      )}&project=${encodeURIComponent(
        projectId
      )}&view=${encodeURIComponent(
        entityView
      )}${batchQuery}`;

    const overlayUrl =
      `/api/document-overlays/${encodeURIComponent(
        projectId
      )}/latest?workspace=${encodeURIComponent(
        workspace
      )}&client=${encodeURIComponent(
        clientId
      )}&overlay_view=${encodeURIComponent(entityView)}`;

    Promise.allSettled([
      apiGet(entitiesUrl),
      apiGet(overlayUrl),
    ])
      .then(([entitiesResult, overlayResult]) => {
        let headers: string[] = [];
        let rows: Record<string, string>[] = [];

        if (entitiesResult.status === "fulfilled") {
          const response =
            entitiesResult.value as CapturedEntitiesResponse;

          headers = response.headers || [];
          rows = response.rows || [];
        }

        if (overlayResult.status === "fulfilled") {
          const overlay = overlayResult.value as any;

          const overlayHeaders =
            overlay.committed_headers ||
            overlay.headers ||
            [];

          const overlayRows = (overlay.records || []).map(
            (record: any) => ({
              "Doc ID": record.doc_id,
              ...(record.metadata || {}),
            })
          );

          headers = uniqueHeaders([
            ...headers,
            "Doc ID",
            ...overlayHeaders,
          ]);

          rows =
            entityView === "final"
              ? overlayRows
              : [...rows, ...overlayRows];
        }

        if (
          entitiesResult.status === "rejected" &&
          overlayResult.status === "rejected"
        ) {
          console.error(entitiesResult.reason);
          console.error(overlayResult.reason);
          setMessage("Captured entities could not be loaded.");
        } else if (entitiesResult.status === "rejected") {
          console.error(entitiesResult.reason);
          setMessage("Manual captured entities could not be loaded. Showing latest overlay data.");
        }

        setEntityData({
          headers,
          rows,
        });
      })
      .finally(() => {
        setIsLoading(false);
      });
    
  }, [workspace, clientId, projectId, batchId, entityView]);

  const headers = useMemo(() => {
    return uniqueHeaders([
      "Doc ID",
      ...protocolColumns.map((column) => column.header),
      ...entityData.headers,
    ]);
  }, [protocolColumns, entityData.headers]);

  const headerGroups = useMemo(() => {
    const groupByHeader = new Map<string, string>();

    groupByHeader.set("Doc ID", "Document");

    protocolColumns.forEach((column) => {
      groupByHeader.set(column.header, column.group);
    });

    entityData.headers.forEach((header) => {
      if (!groupByHeader.has(header)) {
        groupByHeader.set(header, "Captured Data");
      }
    });

    const groups: { label: string; span: number }[] = [];

    headers.forEach((header) => {
      const label = groupByHeader.get(header) || "Captured Data";
      const last = groups[groups.length - 1];

      if (last && last.label === label) {
        last.span += 1;
      } else {
        groups.push({
          label,
          span: 1,
        });
      }
    });

    return groups;
  }, [headers, protocolColumns, entityData.headers]);

  function openDocument(docId: string) {
    router.push(
      buildReviewHref(
        workspace,
        clientId,
        projectId,
        "",
        docId
      )
    );
  }

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

  return (
    <AppShell>
      <PageContainer>
        <PageHeader
          title={title}
          subtitle={`${subtitlePrefix} for ${projectId.replaceAll(
            "_",
            " "
          )}${batchId ? ` / ${batchId.replaceAll("_", " ")}` : ""}.`}
        />

        {message && (
          <p className="text-sm text-amber-300 mb-6">
            {message}
          </p>
        )}

        <ContentCard title="Captured Entity Table">
          <div className="mb-4 flex flex-col md:flex-row md:items-center md:justify-between gap-3">
            <p className="text-sm text-slate-400">
              Headers are loaded from the saved project protocol before captured rows are available.
            </p>

            <p className="text-xs text-slate-500">
              Rows: {entityData.rows.length} | Headers: {headers.length}
            </p>
          </div>

          <div className="flex gap-2 mb-4">
            <button
              type="button"
              onClick={() => setEntityView("raw")}
              className={
                entityView === "raw"
                  ? "rounded-lg bg-sky-600 px-4 py-2 text-sm font-semibold text-white"
                  : "rounded-lg bg-slate-800 px-4 py-2 text-sm font-semibold text-slate-300 hover:bg-slate-700"
              }
            >
              Raw
            </button>

            <button
              type="button"
              onClick={() => setEntityView("final")}
              className={
                entityView === "final"
                  ? "rounded-lg bg-sky-600 px-4 py-2 text-sm font-semibold text-white"
                  : "rounded-lg bg-slate-800 px-4 py-2 text-sm font-semibold text-slate-300 hover:bg-slate-700"
              }
            >
              Final
            </button>
          </div>

          <div className="bg-slate-950 border border-slate-800 rounded-xl overflow-auto max-h-[70vh]">
            <table className="min-w-max w-full text-xs">
              <thead className="bg-slate-900 text-slate-400 sticky top-0 z-20">
                <tr>
                  {headerGroups.map((group, index) => (
                    <th
                      key={`${group.label}-${index}`}
                      colSpan={group.span}
                      className={
                        index === 0
                          ? "p-3 text-left sticky left-0 bg-slate-900 z-20 whitespace-nowrap border-b border-slate-800"
                          : "p-3 text-left border-l border-b border-slate-800 whitespace-nowrap text-sky-300"
                      }
                    >
                      {group.label}
                    </th>
                  ))}
                </tr>

                <tr>
                  {headers.map((header, index) => (
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
                {entityData.rows.length === 0 ? (
                  <tr>
                    <td
                      colSpan={Math.max(headers.length, 1)}
                      className="p-6 text-slate-500"
                    >
                      {isLoading
                        ? "Loading captured entities..."
                        : "No captured entities found yet. Protocol headers are ready for incoming review data."}
                    </td>
                  </tr>
                ) : (
                  entityData.rows.map((row, rowIndex) => (
                    <tr
                      key={rowIndex}
                      className="border-t border-slate-800"
                    >
                      {headers.map((header, index) => {
                        const value = row[header] || "";

                        if (header === "Doc ID") {
                          return (
                            <td
                              key={header}
                              className="p-3 sticky left-0 bg-slate-950 z-10 whitespace-nowrap"
                            >
                              <button
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
                  ))
                )}
              </tbody>
            </table>
          </div>
        </ContentCard>
      </PageContainer>
    </AppShell>
  );
}