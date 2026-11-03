"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";

import AppShell from "../../../components/AppShell";
import PageContainer from "../../../components/PageContainer";
import PageHeader from "../../../components/PageHeader";
import ContentCard from "../../../components/ContentCard";
import { apiGet, apiPost } from "../../../lib/api";

type ProjectFile = {
  doc_id?: string;
  file_name?: string;
};

type TARaiEvidence = {
  quote: string;
  explanation: string;
};

type TARaiSuggestion = {
  classification: string;
  rationale: string;
  evidence: TARaiEvidence[];
  reviewer_status: string;
};

type TARaiResult = {
  workspace: string;
  client: string;
  project: string;
  doc_id: string;
  suggestion: TARaiSuggestion;
  saved_to_review: boolean;
  requires_reviewer_approval: boolean;
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
  const [selectedDocId, setSelectedDocId] = useState("");
  const [analyzing, setAnalyzing] = useState(false);
  const [analysisError, setAnalysisError] = useState("");
  const [analysisResult, setAnalysisResult] =
    useState<TARaiResult | null>(null);

  function analyzeSelectedDocument() {
    if (!client || !project || !selectedDocId || analyzing) return;

    setAnalyzing(true);
    setAnalysisError("");
    setAnalysisResult(null);

    apiPost("/api/discovery/tarai/privilege/suggest", {
      client,
      project,
      doc_id: selectedDocId,
    })
      .then((result: TARaiResult) => {
        if (
          result.doc_id !== selectedDocId ||
          result.workspace !== "discovery" ||
          result.saved_to_review !== false ||
          result.requires_reviewer_approval !== true ||
          result.suggestion?.reviewer_status !== "pending"
        ) {
          throw new Error(
            "TARai returned an unexpected document or review state."
          );
        }

        setAnalysisResult(result);
      })
      .catch((err: unknown) => {
        setAnalysisError(
          err instanceof Error
            ? err.message
            : "TARai analysis failed."
        );
      })
      .finally(() => setAnalyzing(false));
  }

  useEffect(() => {
    if (!client || !project) {
      setLoading(false);
      return;
    }

    let active = true;

    setLoading(true);
    setError("");
    setSelectedDocId("");
    setAnalysisResult(null);
    setAnalysisError("");

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
                <div className="space-y-5">
                  <p className="text-sm text-slate-300">
                    Select a Discovery document to request a preliminary
                    privilege suggestion. Every suggestion requires
                    human reviewer approval. No coding is saved automatically.
                  </p>

                  <div>
                    <label
                      htmlFor="tarai-document"
                      className="block text-sm font-medium mb-2"
                    >
                      Discovery Document
                    </label>
                    <select
                      id="tarai-document"
                      value={selectedDocId}
                      onChange={(event) => {
                        setSelectedDocId(event.target.value);
                        setAnalysisResult(null);
                        setAnalysisError("");
                      }}
                      className="w-full rounded-md border border-slate-600 bg-slate-900 px-3 py-2 text-white"
                    >
                      <option value="">Select a document</option>
                      {files.filter((file) => Boolean(file.doc_id)).map(
                        (file) => (
                          <option
                            key={file.doc_id}
                            value={file.doc_id}
                          >
                            {file.doc_id}
                            {file.file_name
                              ? ` - ${file.file_name}`
                              : ""}
                          </option>
                        )
                      )}
                    </select>
                    {files.length > 0 &&
                      !files.some((file) => Boolean(file.doc_id)) && (
                        <p className="text-sm text-amber-300 mt-2">
                          No canonical document IDs were returned.
                          TARai will not analyze filename guesses.
                        </p>
                      )}
                  </div>

                  <button
                    type="button"
                    onClick={analyzeSelectedDocument}
                    disabled={!selectedDocId || analyzing}
                    className="rounded-md bg-sky-600 px-4 py-2 font-semibold text-white disabled:opacity-40"
                  >
                    {analyzing
                      ? "Analyzing..."
                      : "Analyze Privilege"}
                  </button>

                  {analysisError && (
                    <div
                      role="alert"
                      className="rounded-md border border-amber-600 p-3 text-sm text-amber-200"
                    >
                      {analysisError}
                    </div>
                  )}

                  {analysisResult && (
                    <div
                      className="space-y-4 border-t border-slate-700 pt-4"
                      aria-live="polite"
                    >
                      <div>
                        <p className="text-xs text-slate-400">
                          Document: {analysisResult.doc_id}
                        </p>
                        <h3 className="text-lg font-semibold">
                          {analysisResult.suggestion.classification
                            .replace(/_/g, " ")}
                        </h3>
                        <p className="text-sm text-amber-300">
                          Reviewer status: Pending
                        </p>
                      </div>

                      <div>
                        <h4 className="font-semibold mb-1">
                          AI Rationale
                        </h4>
                        <p className="whitespace-pre-wrap text-sm text-slate-200">
                          {analysisResult.suggestion.rationale}
                        </p>
                      </div>

                      <div>
                        <h4 className="font-semibold mb-2">
                          Supporting Evidence
                        </h4>
                        <div className="space-y-3">
                          {(analysisResult.suggestion.evidence || []).map(
                            (item, index) => (
                              <div
                                key={index}
                                className="rounded-md border border-slate-700 p-3"
                              >
                                <blockquote className="border-l-2 border-sky-500 pl-3 text-sm whitespace-pre-wrap">
                                  {item.quote}
                                </blockquote>
                                <p className="mt-2 text-sm text-slate-400">
                                  {item.explanation}
                                </p>
                              </div>
                            )
                          )}
                        </div>
                      </div>

                      <p className="text-xs text-slate-400">
                        Preliminary suggestion only. No Review coding
                        has been saved.
                      </p>
                    </div>
                  )}
                </div>
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