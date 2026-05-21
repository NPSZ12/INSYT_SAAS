"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";

import AppShell from "../../../../components/AppShell";
import ReviewHeader from "../../../../components/ReviewHeader";
import ReviewDocumentPane from "../../../../components/ReviewDocumentPane";
import ReviewCapturePanel from "../../../../components/ReviewCapturePanel";

import PageContainer from "../../../../components/PageContainer";
import PageHeader from "../../../../components/PageHeader";

import { apiGet } from "../../../../lib/api";

import type { ReviewDocument } from "../../../../types";

function ReviewPageContent() {
  const searchParams = useSearchParams();

  const projectId = searchParams.get("project");
  

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

  const batchId = searchParams.get("batch");
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

  const [reviewDoc, setReviewDoc] =
    useState<ReviewDocument | null>(null);

  useEffect(() => {
    apiGet(`/api/review/current?project=${projectId}&batch=${batchId}`)
      .then(setReviewDoc)
      .catch(console.error);
  }, [projectId]);

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

  return (
    <AppShell>
      <div className="min-h-screen flex flex-col text-white">

        <ReviewHeader
          project={reviewDoc.project}
          batch={reviewDoc.batch}
          docId={reviewDoc.doc_id}
        />

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
            fields={reviewDoc.fields}
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









