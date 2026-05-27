"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";

import AppShell from "../../../../components/AppShell";
import ReviewHeader from "../../../../components/ReviewHeader";
import ReviewDocumentPane from "../../../../components/ReviewDocumentPane";

import SummariesRightPane from "../../../../components/summaries/SummariesRightPane";

import PageContainer from "../../../../components/PageContainer";
import PageHeader from "../../../../components/PageHeader";
import ContentCard from "../../../../components/ContentCard";

import { apiGet, apiPost } from "../../../../lib/api";

import type { ReviewDocument } from "../../../../types";
import PdfOutlinePane, {
  type SummaryOutlineItem,
} from "../../../../components/summaries/PdfOutlinePane";


function ReviewPageContent() {
  const searchParams = useSearchParams();

  const projectId = searchParams.get("project") || "";
  const batchId = searchParams.get("batch") || "";

  const [error, setError] = useState("");
  const [reviewDoc, setReviewDoc] =
    useState<ReviewDocument | null>(null);

  const [isLoading, setIsLoading] = useState(false);

  const [originalSummary, setOriginalSummary] =
    useState("");

  const [qcSummary, setQcSummary] =
    useState("");
  
  const [outlineItems, setOutlineItems] =
    useState<SummaryOutlineItem[]>([]);

  // =====================================================
  // PDF Outline Controller State
  // =====================================================

  const [currentOutlineTitle, setCurrentOutlineTitle] =
    useState("");

  const [currentOutlinePageStart, setCurrentOutlinePageStart] =
    useState<number | null>(null);

  const [currentOutlinePageEnd, setCurrentOutlinePageEnd] =
    useState<number | null>(null);

  useEffect(() => {
    if (!projectId || !batchId) {
      return;
    }

    setIsLoading(true);
    setError("");
    setReviewDoc(null);

    apiGet(
      `/api/summaries/review/current?project=${encodeURIComponent(
        projectId
      )}&batch=${encodeURIComponent(batchId)}`
    )
      .then((response: any) => {
        setReviewDoc(response);

        const original =
          response?.original_summary ||
          response?.summary ||
          response?.text ||
          "";

        const qc =
          response?.qc_summary ||
          original;

        setOriginalSummary(original);
        setQcSummary(qc);

        const incomingOutlineItems =
          response?.outline_items || [
            {
              id: "summary-1",
              title: "1: Statement of Account",
              citation: "2024/01/01 | Omni/Glofin | p. 38 | Importance: 30%",
              originalSummary:
                "Pre-settlement funding and medical billing statement for plaintiff Jane Doe (Case ID 1023416). Total medical charges managed: $2,583.14. Amount due subject to change at case settlement.",
              pageStart: 38,
              pageEnd: 38,
            },
          ];

        setOutlineItems(incomingOutlineItems);

        const firstOutlineItem = incomingOutlineItems[0];

        setCurrentOutlineTitle(
          response?.outline_title ||
            firstOutlineItem?.title ||
            ""
        );

        setCurrentOutlinePageStart(
          response?.outline_page_start ??
            firstOutlineItem?.pageStart ??
            null
        );

        setCurrentOutlinePageEnd(
          response?.outline_page_end ??
            firstOutlineItem?.pageEnd ??
            null
        );
      })
      .catch((error: any) => {
        console.error(error);

        setError(
          String(
            error?.message ||
              "Failed to load summary review document."
          )
        );
      })
      .finally(() => {
        setIsLoading(false);
      });
  }, [projectId, batchId]);

  function handleOutlineSelect(item: SummaryOutlineItem) {
    setCurrentOutlineTitle(item.title);
    setCurrentOutlinePageStart(item.pageStart);
    setCurrentOutlinePageEnd(item.pageEnd ?? null);

    setOriginalSummary(item.originalSummary);
    setQcSummary(item.originalSummary);
  }

  async function saveQcSummary(
    summaryDocId: string,
    updatedQcSummary: string
  ) {
    await apiPost("/api/summaries/qc/save", {
      project_id: projectId,
      batch_id: batchId,
      summary_doc_id: summaryDocId,
      qc_summary: updatedQcSummary,
    });

    setQcSummary(updatedQcSummary);
  }

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

  if (error) {
    return (
      <AppShell>
        <PageContainer>
          <ContentCard title="Summary Review Error">
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
              Loading Summary Review Workspace
            </h1>

            <p className="text-slate-400">
              Preparing native PDF, outline links, original summary, and QC review.
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

        <section className="flex-1 flex gap-4 p-4 overflow-hidden">
          <div className="flex-1 min-w-0">
            <ReviewDocumentPane
              text={reviewDoc.text}
              nativeUrl={reviewDoc.native_url}
              nativeBlob={reviewDoc.native_blob}
            />
          </div>

          <SummariesRightPane
            summaryDocId={reviewDoc.doc_id}
            title={
              currentOutlineTitle ||
              reviewDoc.doc_id ||
              "Summary Review"
            }
            originalSummary={originalSummary}
            qcSummary={qcSummary}
            onSaveQcSummary={saveQcSummary}
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