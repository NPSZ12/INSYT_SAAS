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
import type { PdfOutlineItem } from "../../../../components/summaries/PdfOutlinePane";


function ReviewPageContent() {
  const searchParams = useSearchParams();
  const docId = searchParams.get("doc") || "";

  const clientId =
    searchParams.get("client") || "";

  const projectId =
    searchParams.get("project") || "";

  const batchId =
    searchParams.get("batch") || "";

  const [error, setError] = useState("");
  const [reviewDoc, setReviewDoc] =
    useState<ReviewDocument | null>(null);

  const [isLoading, setIsLoading] = useState(false);

  const [originalSummary, setOriginalSummary] =
    useState("");

  const [qcSummary, setQcSummary] =
    useState("");
  
  const [outlineItems, setOutlineItems] =
    useState<PdfOutlineItem[]>([]);

  const [targetPdfPage, setTargetPdfPage] =
    useState<number | null>(null);

  const [selectedSummaryDocId, setSelectedSummaryDocId] = useState("");

  const [currentCitation, setCurrentCitation] = useState("");

  const outlineId = searchParams.get("outline") || "";
  const pageParam = searchParams.get("page") || "";

  const [qcPaneWidth, setQcPaneWidth] = useState(544);
  const [isResizing, setIsResizing] = useState(false);
  

  // =====================================================
  // PDF Outline Controller State
  // =====================================================

  const [currentOutlineTitle, setCurrentOutlineTitle] =
    useState("");


  function handleOutlineSelect(item: PdfOutlineItem) {
    const targetPage =
      item.summaryPdfPage ??
      item.summary_pdf_page ??
      item.pdfPage ??
      item.pdf_page ??
      item.page ??
      item.pageStart ??
      1;

    setSelectedSummaryDocId(item.id);

    setCurrentOutlineTitle(item.title);
    setCurrentCitation(item.citation || "");

    setTargetPdfPage(targetPage);

    setOriginalSummary(item.originalSummary || "");

    setQcSummary(
      item.qcSummary ||
      item.originalSummary ||
      ""
    );
  }

  useEffect(() => {
    if (!isResizing) return;

    function handleMouseMove(event: MouseEvent) {
      const windowWidth = window.innerWidth;
      const newWidth = windowWidth - event.clientX;

      const minWidth = 380;
      const maxWidth = 760;

      setQcPaneWidth(
        Math.min(Math.max(newWidth, minWidth), maxWidth)
      );
    }

    function handleMouseUp() {
      setIsResizing(false);
    }

    window.addEventListener("mousemove", handleMouseMove);
    window.addEventListener("mouseup", handleMouseUp);

    return () => {
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", handleMouseUp);
    };
  }, [isResizing]);

  useEffect(() => {
    if (!outlineId || outlineItems.length === 0) return;

    const item = outlineItems.find(
      (outlineItem) => outlineItem.id === outlineId
    );

    if (!item) return;

    handleOutlineSelect(item);
  }, [outlineId, outlineItems]);

  useEffect(() => {
    if (!pageParam) return;

    const page = Number(pageParam);

    if (!Number.isNaN(page) && page > 0) {
      setTargetPdfPage(page);
    }
  }, [pageParam]);

  useEffect(() => {
    if (!clientId || !projectId || !batchId) {
      return;
    }

    setIsLoading(true);
    setError("");
    setReviewDoc(null);

    apiGet(
      `/api/summaries/review/current?client=${encodeURIComponent(
        clientId
      )}&project=${encodeURIComponent(
        projectId
      )}&batch=${encodeURIComponent(batchId)}`
    )
      .then((response: any) => {
        setReviewDoc(response);

        const incomingOutlineItems =
          response?.outline_items || [
            {
              id: "summary-1",
              title: "1: Statement of Account",
              citation:
                "2024/01/01 | Omni/Glofin | p. 38 | Importance: 30%",
              originalSummary:
                "Pre-settlement funding and medical billing statement for plaintiff Jane Doe (Case ID 1023416). Total medical charges managed: $2,583.14. Amount due subject to change at case settlement.",
              pageStart: 38,
              pageEnd: 38,
            },
          ];

        const firstOutlineItem =
          incomingOutlineItems[0];

        const original =
          response?.original_summary ||
          firstOutlineItem?.originalSummary ||
          "";

        const qc =
          response?.qc_summary ||
          firstOutlineItem?.qcSummary ||
          original;

        setOriginalSummary(original);
        setQcSummary(qc);

        setOutlineItems(incomingOutlineItems);

        if (incomingOutlineItems.length > 0) {
          handleOutlineSelect(
            incomingOutlineItems[0]
          );
        }

        setCurrentOutlineTitle(
          response?.outline_title ||
            firstOutlineItem?.title ||
            ""
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
        }, [clientId, projectId, batchId]);

  async function saveQcSummary(
    summaryDocId: string,
    updatedQcSummary: string
  ) {
    if (!projectId || !clientId || !reviewDoc) return;

    const pdfName =
      reviewDoc.native_blob?.split("/").pop() ||
      reviewDoc.doc_id ||
      "Unknown PDF";

    const title =
      currentOutlineTitle ||
      summaryDocId;

    const existingCheck = await apiPost(
      "/api/summaries/summary-data/exists",
      {
        client: clientId,
        project_id: projectId,
        pdf_name: pdfName,
        summary_key: title,
      }
    );

    if (existingCheck.exists) {
      const confirmed = window.confirm(
        `${title} has already been saved for ${pdfName}.\n\nDo you want to update the existing Summary Data Table row?`
      );

      if (!confirmed) {
        return;
      }
    }

    await apiPost("/api/summaries/summary-data/save", {
      client: clientId,
      project_id: projectId,
      batch_id: batchId,
      pdf_name: pdfName,
      summary_doc_id: summaryDocId,

      // Save by summary number/title, not page number.
      summary_key: title,
      title,

      citation: currentCitation || "",
      original_summary: originalSummary || "",
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

        <section className="flex-1 flex gap-4 p-4 items-stretch overflow-hidden">

          {/* Native PDF Viewer */}
          <div className="flex-1 min-w-0 self-stretch">
            <ReviewDocumentPane
              text={reviewDoc.text}
              nativeUrl={reviewDoc.native_url}
              nativeBlob={reviewDoc.native_blob}
              targetPage={targetPdfPage}
            />
          </div>

          {/* Draggable Pane Divider */}
          <div
            role="separator"
            aria-orientation="vertical"
            title="Drag to resize panes"
            onMouseDown={(event) => {
              event.preventDefault();
              setIsResizing(true);
            }}
            className={[
              "relative w-3 shrink-0 cursor-col-resize",
              "bg-slate-950 hover:bg-sky-950/70",
              "border-x border-slate-800",
              isResizing ? "bg-sky-900/70" : "",
            ].join(" ")}
          >
            <div className="absolute inset-y-0 left-1/2 -translate-x-1/2 flex items-center">
              <div className="rounded-full border border-slate-600 bg-slate-900 px-1 py-3 text-[10px] text-slate-300 shadow-lg">
                &lt;&gt;
              </div>
            </div>
          </div>

          {/* Summary QC Pane */}
          <div
            className="shrink-0 self-stretch min-h-[760px] h-full overflow-hidden"
            style={{ width: qcPaneWidth }}
          >
            <SummariesRightPane
              summaryDocId={selectedSummaryDocId || reviewDoc.doc_id}
              title={
                currentOutlineTitle ||
                reviewDoc.doc_id ||
                "Summary Review"
              }
              citation={currentCitation}
              originalSummary={originalSummary}
              qcSummary={qcSummary}
              onSaveQcSummary={saveQcSummary}
            />
          </div>
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