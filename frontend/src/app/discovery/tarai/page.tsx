"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";

import AppShell from "../../../components/AppShell";
import PageContainer from "../../../components/PageContainer";
import PageHeader from "../../../components/PageHeader";
import ContentCard from "../../../components/ContentCard";
import { apiGet } from "../../../lib/api";

type ProjectFile = {
  doc_id?: string;
  file_name?: string;
};

type ProtocolResponse = {
  has_protocol?: boolean;
  fields?: unknown[];
  protocol?: {
    fields?: unknown[];
  };
};

function TARaiContent() {
  const params = useSearchParams();

  const client = params.get("client") || "";
  const project = params.get("project") || "";

  const [files, setFiles] = useState<ProjectFile[]>([]);
  const [coding, setCoding] = useState<Record<string, string>>({});
  const [protocol, setProtocol] = useState<ProtocolResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!client || !project) {
      setLoading(false);
      return;
    }

    let active = true;

    setLoading(true);
    setError("");

    const fileParams = new URLSearchParams({
      client,
      project,
      folder: "source/native",
    });

    const codingParams = new URLSearchParams({
      client,
      project,
      workspace: "discovery",
    });

    Promise.all([
      apiGet(`/api/discovery/files?${fileParams.toString()}`),
      apiGet(`/api/review/coding-map?${codingParams.toString()}`),
      apiGet(
        `/api/discovery/projects/${encodeURIComponent(project)}/protocol`
      ),
    ])
      .then(([fileResponse, codingResponse, protocolResponse]) => {
        if (!active) return;

        const incomingFiles = Array.isArray(fileResponse)
          ? fileResponse
          : Array.isArray(fileResponse?.files)
            ? fileResponse.files
            : [];

        setFiles(incomingFiles);
        setCoding(codingResponse || {});
        setProtocol(protocolResponse || null);
      })
      .catch((err) => {
        if (!active) return;
        setError(String(err?.message || "Unable to load TARai project data."));
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
    };
  }, [client, project]);

  const codedCount = files.filter((file) => {
    const id = file.doc_id || "";
    const normalized = id.replace(/\.[^/.]+$/, "");
    return Boolean(coding[id] || coding[normalized]);
  }).length;

  const totalCount = files.length;
  const uncodedCount = totalCount - codedCount;

  const protocolFields =
    protocol?.protocol?.fields || protocol?.fields || [];

  if (!client || !project) {
    return (
      <AppShell>
        <PageContainer>
          <PageHeader
            title="TARai"
            subtitle="Select a Discovery client and project first."
          />
        </PageContainer>
      </AppShell>
    );
  }

  return (
    <AppShell>
      <PageContainer>
        <PageHeader
          title="TARai"
          subtitle={`Technology-Assisted Review | ${client} / ${project}`}
        />

        {loading ? (
          <ContentCard title="Loading Discovery Data">
            <p>Loading project documents, coding, and protocol...</p>
          </ContentCard>
        ) : error ? (
          <ContentCard title="TARai Data Error">
            <p className="text-red-400">{error}</p>
          </ContentCard>
        ) : (
          <>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
              {[
                ["Documents", totalCount],
                ["Coded", codedCount],
                ["Uncoded", uncodedCount],
              ].map(([label, value]) => (
                <ContentCard key={label} title={String(label)}>
                  <div className="text-3xl font-bold text-sky-400">
                    {value}
                  </div>
                </ContentCard>
              ))}
            </div>

            <ContentCard title="Discovery Protocol">
              <p className="text-sm text-slate-300">
                {protocol?.has_protocol
                  ? `${protocolFields.length} protocol fields loaded.`
                  : "No saved Discovery protocol found."}
              </p>
            </ContentCard>

            <div className="mt-6">
              <ContentCard title="AI Privilege Review">
                <p className="text-sm text-slate-300">
                  TARai will use the Discovery protocol to propose
                  privilege and other legal review classifications.
                  AI classification is not yet enabled.
                </p>
              </ContentCard>
            </div>
          </>
        )}
      </PageContainer>
    </AppShell>
  );
}

export default function TARaiPage() {
  return (
    <Suspense fallback={<div>Loading TARai...</div>}>
      <TARaiContent />
    </Suspense>
  );
}