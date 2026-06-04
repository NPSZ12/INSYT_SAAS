"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";

import AppShell from "../../../../components/AppShell";
import ReviewHeader from "../../../../components/ReviewHeader";
import ReviewDocumentPane from "../../../../components/ReviewDocumentPane";
import DiscoveryReviewPanel from "../../../../components/DiscoveryReviewPanel";
import PageContainer from "../../../../components/PageContainer";
import PageHeader from "../../../../components/PageHeader";
import ContentCard from "../../../../components/ContentCard";

import { apiGet } from "../../../../lib/api";

import type { ReviewDocument } from "../../../../types";

type ProtocolField = {
  section: string;
  data_element: string;
  format?: string;
  default_format?: string;
  notes?: string;
  source_sheet?: string;
};

type ProtocolResponse = {
  has_protocol: boolean;
  fields?: ProtocolField[];
  protocol?: {
    fields?: ProtocolField[];
  };
};

type discoveryField = {
  section: string;
  label: string;
  type: string;
  format?: string;
  notes?: string;
};

function ReviewPageContent() {
  const searchParams = useSearchParams();

  const clientId = searchParams.get("client") || "";
  const projectId = searchParams.get("project") || "";
  const batchId = searchParams.get("batch") || "";
  const docId = searchParams.get("doc") || "";

  const [error, setError] = useState("");
  const [protocolMessage, setProtocolMessage] = useState("");
  const [reviewDoc, setReviewDoc] = useState<ReviewDocument | null>(null);
  const [protocolFields, setProtocolFields] = useState<ProtocolField[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    if (!projectId || (!batchId && !docId)) {
      return;
    }

    setIsLoading(true);
    setError("");
    setReviewDoc(null);

    if (docId && !batchId) {
      apiGet(
        `/api/discovery/files?client=${encodeURIComponent(
          clientId
        )}&project=${encodeURIComponent(
          projectId
        )}&folder=${encodeURIComponent("source/native")}`
      )
        .then((files: any[]) => {
          const file = files.find(
            (item) => item.doc_id === docId
          );

          if (!file) {
            setError("Document not found in project source/native.");
            return;
          }

          setReviewDoc({
            project: projectId,
            batch: "Direct Open",
            doc_id: file.doc_id,
            text: "",
            native_url: "",
            native_blob: file.blob_path,
          } as ReviewDocument);
        })
        .catch((error) => {
          console.error(error);
          setError("Failed to open document directly.");
        })
        .finally(() => {
          setIsLoading(false);
        });

      return;
    }

    apiGet(
      `/api/review/current?client=${encodeURIComponent(
        clientId
      )}&project=${encodeURIComponent(
        projectId
      )}&batch=${encodeURIComponent(batchId)}`
    )
      .then((response) => {
        setReviewDoc(response);
      })
      .catch((error) => {
        console.error(error);
        setError(String(error?.message || "Failed to load review document."));
      })
      .finally(() => {
        setIsLoading(false);
      });
  }, [clientId, projectId, batchId, docId]);

  useEffect(() => {
    if (!projectId) {
      return;
    }

    setProtocolMessage("Loading saved protocol fields...");
    setProtocolFields([]);

    apiGet(`/api/discovery/projects/${encodeURIComponent(projectId)}/protocol`)
      .then((response: ProtocolResponse) => {
        console.log("REVIEW PROTOCOL RESPONSE", response);

        const fields =
          response?.protocol?.fields ||
          response?.fields ||
          [];

        console.log("PARSED REVIEW FIELDS", fields);

        if (!response.has_protocol) {
          setProtocolMessage("No saved protocol found for this project.");
          setProtocolFields([]);
          return;
        }

        if (fields.length === 0) {
          console.error("NO REVIEW PROTOCOL FIELDS FOUND", response);

          setProtocolMessage(
            `Saved protocol found for ${projectId}, but no fields were returned.`
          );

          setProtocolFields([]);
          return;
        }

        setProtocolFields(fields);
        setProtocolMessage("");
      })
      .catch((error) => {
        console.error("Failed to load review protocol", error);
        setProtocolFields([]);
        setProtocolMessage("Failed to load saved protocol fields.");
      });
  }, [projectId]);

  if (!projectId) {
    return (
      <AppShell>
        <PageContainer>
          <PageHeader
            title="No Project Selected"
            subtitle="Please select a project before beginning review."
          />
        </PageContainer>
      </AppShell>
    );
  }

  if (!batchId && !docId) {
    return (
      <AppShell>
        <PageContainer>
          <PageHeader
            title="No Batch Selected"
            subtitle="Please select a batch before starting review."
          />
        </PageContainer>
      </AppShell>
    );
  }

  if (error) {
    return (
      <AppShell>
        <PageContainer>
          <ContentCard title="Review Workspace Error">
            <p className="text-red-400 text-sm whitespace-pre-wrap">
              {error}
            </p>
          </ContentCard>
        </PageContainer>
      </AppShell>
    );
  }

  if (isLoading || !reviewDoc) {
    return (
      <AppShell>
        <div className="min-h-screen bg-slate-950 text-white flex items-center justify-center">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-8 w-full max-w-md text-center">
            <div className="flex items-end justify-center gap-0.5 mb-6">
              <span className="insyt-brand text-5xl font-bold text-white">
                I
              </span>

              <span className="insyt-brand text-5xl font-bold text-sky-400">
                N
              </span>

              <span className="insyt-brand text-5xl font-bold text-white">
                SYT
              </span>

              <span className="insyt-brand text-[2.1em] leading-none mb-[0.11em] text-sky-400 font-bold">
                360
              </span>
            </div>

            <div className="mx-auto mb-6 h-12 w-12 rounded-full border-4 border-slate-700 border-t-sky-500 animate-spin" />

            <h1 className="text-2xl font-bold mb-2">
              Loading Review Workspace
            </h1>

            <p className="text-slate-400">
              Preparing document text, native viewer, protocol fields, and linked entities.
            </p>
          </div>
        </div>
      </AppShell>
    );
  }

  console.log("PROTOCOL FIELDS STATE", protocolFields);

  console.log("FIELDS FOR discovery INPUT", {
    protocolFieldsLength: protocolFields.length,
    protocolFields,
  });

  const fieldsForDiscovery = protocolFields.map((field) => {
    const fieldFormat = field.format || field.default_format || "";

    return {
      section: field.section || "General",
      label: field.data_element,
      type: fieldFormat.toLowerCase().includes("tag") ? "tag" : "text",
      format: fieldFormat,
      notes: field.notes || "",
    };
  });

  return (
    <AppShell>
      <div className="min-h-screen flex flex-col text-white">
        <ReviewHeader
          project={reviewDoc.project}
          batch={reviewDoc.batch}
          docId={reviewDoc.doc_id}
        />

        {protocolMessage && (
          <div className="mx-4 mt-4 rounded-xl border border-amber-700 bg-amber-950/40 px-4 py-3 text-sm text-amber-200">
            {protocolMessage}
          </div>
        )}

        <section className="flex-1 grid grid-cols-3 gap-4 p-4">
          <ReviewDocumentPane
            text={reviewDoc.text}
            nativeUrl={reviewDoc.native_url}
            nativeBlob={reviewDoc.native_blob}
          />

          {fieldsForDiscovery.length === 0 ? (
            <aside className="bg-slate-900 border border-slate-800 rounded-2xl p-6 overflow-y-auto h-[82vh]">
              <h2 className="text-lg font-semibold mb-4 text-white">
                discovery Panel
              </h2>

              <p className="text-sm text-amber-200 rounded-xl border border-amber-700 bg-amber-950/40 px-4 py-3">
                No protocol discovery fields loaded for this project.
              </p>
            </aside>
          ) : (
            <DiscoveryReviewPanel
              projectId={projectId}
              batchId={batchId}
              docId={reviewDoc.doc_id}
              fields={fieldsForDiscovery}
            />
          )}
        </section>
      </div>
    </AppShell>
  );
}

export default function ReviewPage() {
  return (
    <Suspense fallback={<div>Loading...</div>}>
      <ReviewPageContent />
    </Suspense>
  );
}
