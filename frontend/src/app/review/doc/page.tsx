"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";

import AppShell from "../../../components/AppShell";
import ReviewHeader from "../../../components/ReviewHeader";
import ReviewDocumentPane from "../../../components/ReviewDocumentPane";
import ReviewCapturePanel from "../../../components/ReviewCapturePanel";

import PageContainer from "../../../components/PageContainer";
import PageHeader from "../../../components/PageHeader";

import { apiGet } from "../../../lib/api";

import type { ReviewDocument } from "../../../types";

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

function ReviewPageContent() {
  const searchParams = useSearchParams();

  const projectId = searchParams.get("project");
  const batchId = searchParams.get("batch");

  const [reviewDoc, setReviewDoc] = useState<ReviewDocument | null>(null);
  const [protocolFields, setProtocolFields] = useState<ProtocolField[]>([]);
  const [protocolMessage, setProtocolMessage] = useState("");

  useEffect(() => {
    if (!projectId || !batchId) return;

    apiGet(
      `/api/review/current?project=${encodeURIComponent(
        projectId
      )}&batch=${encodeURIComponent(batchId)}`
    )
      .then(setReviewDoc)
      .catch(console.error);
  }, [projectId, batchId]);

  useEffect(() => {
    if (!projectId) return;

    apiGet(`/api/capture/projects/${encodeURIComponent(projectId)}/protocol`)
      .then((data: ProtocolResponse) => {
        const fields = data.protocol?.fields || data.fields || [];

        setProtocolFields(fields);

        if (!data.has_protocol) {
          setProtocolMessage("No saved protocol found for this project.");
        } else if (fields.length === 0) {
          setProtocolMessage("Saved protocol found, but no fields were parsed.");
        } else {
          setProtocolMessage("");
        }
      })
      .catch((error) => {
        console.error("Failed to load protocol fields", error);
        setProtocolFields([]);
        setProtocolMessage("Failed to load saved protocol fields.");
      });
  }, [projectId]);

  if (!projectId) {
    return (
      <AppShell>
        <div className="p-10">
          <p className="text-slate-400">
            Please select a project before beginning review.
          </p>
        </div>
      </AppShell>
    );
  }

  if (!batchId) {
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

  if (!reviewDoc) {
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

  const fieldsForCapture =
    protocolFields.length > 0
      ? protocolFields.map((field) => ({
          section: field.section || "General",
          label: field.data_element,
          type:
            `${field.format || field.default_format || ""}`
              .toLowerCase()
              .includes("tag")
              ? "tag"
              : "text",
          format: field.format || field.default_format || "",
          notes: field.notes || "",
        }))
      : reviewDoc.fields || [];

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

          <ReviewCapturePanel
            projectId={projectId}
            batchId={batchId}
            docId={reviewDoc.doc_id}
            fields={fieldsForCapture}
          />
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