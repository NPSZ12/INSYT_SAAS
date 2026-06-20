"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

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
  const router = useRouter();

  const docId = searchParams.get("doc") || "";

  console.log("SUMMARIES REVIEW DOC PAGE MOUNTED", {
    client: searchParams.get("client") || "",
    project: searchParams.get("project") || "",
    batch: searchParams.get("batch") || "",
    doc: searchParams.get("doc") || "",
    pathname:
      typeof window !== "undefined"
        ? window.location.pathname
        : "",
  });

  const clientId =
    searchParams.get("client") || "";

  const projectId =
    searchParams.get("project") || "";

  const batchId =
    searchParams.get("batch") || "";

  const summarySetId =
    searchParams.get("summarySet") ||
    batchId;

  const [error, setError] = useState("");
  const [reviewDoc, setReviewDoc] =
    useState<ReviewDocument | null>(null);

  const [user, setUser] = useState<any>(null);

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
  const [fileDocIds, setFileDocIds] = useState<string[]>([]);
  const isFileView = Boolean(docId && !summarySetId);

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
    const storedUser = localStorage.getItem("insyt_user");

    if (storedUser) {
      setUser(JSON.parse(storedUser));
    }
  }, []);

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
    if (!clientId || !projectId) {
      return;
    }

    if (!summarySetId && !docId && !user?.username) {
      return;
    }

    setIsLoading(true);
    setError("");
    setReviewDoc(null);

    async function loadSummaryReview() {
      try {
        let effectiveSummarySetId = summarySetId;

        if (!effectiveSummarySetId && !docId && user?.username) {
          
          console.log("SUMMARIES CHECKED OUT SUMMARY SET LOOKUP:", {
            clientId,
            projectId,
            username: user.username,
          });

          const checkedOutResponse = await apiGet(
            `/api/summaries/summary-sets/checked-out?client=${encodeURIComponent(
              clientId
            )}&project=${encodeURIComponent(
              projectId
            )}&username=${encodeURIComponent(user.username)}`
          );

          const activeSummarySet =
            checkedOutResponse?.active_summary_set ||
            checkedOutResponse?.summary_sets?.[0];

          console.log("SUMMARIES CHECKED OUT SUMMARY SET RESPONSE:", {
            activeSummarySet,
            count: checkedOutResponse?.count,
          });

          if (!activeSummarySet?.batch_summary_set_id) {
            setError("No Summary Set is currently checked out to you.");
            setIsLoading(false);
            return;
          }

          effectiveSummarySetId = activeSummarySet.batch_summary_set_id;
        }

        if (effectiveSummarySetId) {
          const response = await apiGet(
            `/api/summaries/summary-sets/review/${encodeURIComponent(
              effectiveSummarySetId
            )}?client=${encodeURIComponent(clientId)}&project=${encodeURIComponent(
              projectId
            )}`
          );

          const batch = response?.batch || response?.summary_set || {};
          const items = batch?.items || response?.summary_set?.items || [];

          const incomingOutlineItems =
            items.map((item: any, index: number) => ({
              id: item.summary_id || `summary-${index + 1}`,
              title:
                item.title ||
                item.section_id ||
                `Summary ${index + 1}`,
              citation: item.citation || "",
              originalSummary:
                item.original_summary ||
                item.originalSummary ||
                "",
              qcSummary:
                item.saved_row?.qc_summary ||
                item.qc_summary ||
                item.qcSummary ||
                item.original_summary ||
                "",
              page:
                item.pdf_page ||
                item.pdfPage ||
                item.page ||
                item.page_start ||
                item.pageStart ||
                null,
              pageStart:
                item.page_start ||
                item.pageStart ||
                item.page ||
                null,
              pageEnd:
                item.page_end ||
                item.pageEnd ||
                item.page ||
                null,
              pdfPage:
                item.pdf_page ||
                item.pdfPage ||
                item.page ||
                null,
              summaryPdfPage:
                item.pdf_page ||
                item.pdfPage ||
                item.page ||
                null,
            })) || [];

          const firstOutlineItem = incomingOutlineItems[0];

          const reviewResponse = {
            project: projectId,
            batch: effectiveSummarySetId,
            batch_id: effectiveSummarySetId,
            doc_id:
              batch.source_doc_id ||
              response?.summary_set?.source_doc_id ||
              effectiveSummarySetId,
            native_blob:
              batch.source_pdf_path ||
              response?.summary_set?.source_pdf_path ||
              "",
            native_url:
              batch.native_url ||
              response?.summary_set?.native_url ||
              "",
            text:
              batch.text ||
              response?.summary_set?.text ||
              "",
            original_summary:
              firstOutlineItem?.originalSummary || "",
            qc_summary:
              firstOutlineItem?.qcSummary ||
              firstOutlineItem?.originalSummary ||
              "",
            outline_items: incomingOutlineItems,
            batch_doc_ids: incomingOutlineItems.map((item: any) => item.id),
            batch_doc_index: 0,
            batch_doc_count: incomingOutlineItems.length,
            is_first_doc: true,
            is_last_doc: incomingOutlineItems.length <= 1,
          };

          setReviewDoc(reviewResponse as unknown as ReviewDocument);

          const original =
            reviewResponse.original_summary ||
            firstOutlineItem?.originalSummary ||
            "";

          const qc =
            reviewResponse.qc_summary ||
            firstOutlineItem?.qcSummary ||
            original;

          setOriginalSummary(original);
          setQcSummary(qc);
          setOutlineItems(incomingOutlineItems);

          if (incomingOutlineItems.length > 0) {
            handleOutlineSelect(incomingOutlineItems[0]);
          }

          setCurrentOutlineTitle(firstOutlineItem?.title || "");
          return;
        }

        if (!docId) {
          setError("No document selected for direct document review.");
          return;
        }

        const response = await apiGet(
          `/api/summaries/review/current?client=${encodeURIComponent(
            clientId
          )}&project=${encodeURIComponent(
            projectId
          )}&doc=${encodeURIComponent(docId)}`
        );

        setReviewDoc(response);

        const incomingOutlineItems =
          response?.outline_items || [];

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
          handleOutlineSelect(incomingOutlineItems[0]);
        }

        setCurrentOutlineTitle(
          response?.outline_title ||
            firstOutlineItem?.title ||
            ""
        );
      } catch (error: any) {
        console.error(error);

        setError(
          String(
            error?.message ||
              "Failed to load Summary Review workspace."
          )
        );
      } finally {
        setIsLoading(false);
      }
    }

    loadSummaryReview();
  }, [clientId, projectId, batchId, summarySetId, docId, user?.username]);
  

  useEffect(() => {
    if (!clientId || !projectId || !isFileView) {
      setFileDocIds([]);
      return;
    }

    apiGet(
      `/api/summaries/files?client=${encodeURIComponent(
        clientId
      )}&project=${encodeURIComponent(
        projectId
      )}&folder=${encodeURIComponent("source/native")}`
    )
      .then((response: any) => {
        const incomingFiles = Array.isArray(response)
          ? response
          : response?.files || [];

        const docIds = incomingFiles
          .map((file: any) => file.doc_id || file.file_name || file.filename || file.name || "")
          .filter(Boolean);

        setFileDocIds(docIds);
      })
      .catch((error) => {
        console.error("Failed to load Summaries file navigation list", error);
        setFileDocIds([]);
      });
  }, [clientId, projectId, isFileView]);

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

    if (summarySetId) {
      await apiPost("/api/summaries/summary-sets/save", {
        client: clientId,
        project: projectId,
        batch_summary_set_id: summarySetId,
        summary_id: summaryDocId,
        section_id: selectedSummaryDocId || "",
        title,
        citation: currentCitation || "",
        original_summary: originalSummary || "",
        qc_summary: updatedQcSummary,
        saved_by:
          JSON.parse(localStorage.getItem("insyt_user") || "{}")?.username ||
          "",
      });

      setQcSummary(updatedQcSummary);
      return;
    }

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

  if (!summarySetId && !docId && !user?.username) {
    return (
      <AppShell>
        <div className="min-h-screen bg-slate-950 text-white flex items-center justify-center">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-8 w-full max-w-md text-center">
            <div className="mx-auto mb-6 h-12 w-12 rounded-full border-4 border-slate-700 border-t-sky-500 animate-spin" />

            <h1 className="text-2xl font-bold mb-2">
              Loading Summary Review Workspace
            </h1>

            <p className="text-slate-400">
              Checking for your checked-out Summary Set.
            </p>
          </div>
        </div>
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

  const reviewNav = reviewDoc as ReviewDocument & {
    previous_doc_id?: string;
    next_doc_id?: string;
    is_first_doc?: boolean;
    is_last_doc?: boolean;
    batch_doc_index?: number;
    batch_doc_count?: number;
    batch_doc_ids?: string[];
  };

  function buildReviewDocUrl(targetDocId: string) {
    const params = new URLSearchParams();

    if (clientId) params.set("client", clientId);
    if (projectId) params.set("project", projectId);
    if (targetDocId) params.set("doc", targetDocId);

    if (summarySetId) {
      params.set("batch", summarySetId);
      params.set("summarySet", summarySetId);
    }

    return `/summaries/review/doc?${params.toString()}`;
  }

  function getBatchDocIds() {
    return ((reviewNav as any).batch_doc_ids || []) as string[];
  }

  function getCurrentDocIndex() {
    return Number((reviewNav as any).batch_doc_index ?? -1);
  }

  const currentDocIndex = getCurrentDocIndex();

  const batchDocCount =
    Number((reviewNav as any).batch_doc_count || getBatchDocIds().length || 0);

  const docPositionLabel =
    currentDocIndex >= 0 && batchDocCount > 0
      ? `Doc ${currentDocIndex + 1} of ${batchDocCount}`
      : "";

  const fileDocIndex = fileDocIds.findIndex(
    (id) =>
      String(id || "").replace(/\.[^.]+$/, "").toLowerCase() ===
        String(reviewDoc?.doc_id || "").replace(/\.[^.]+$/, "").toLowerCase() ||
      String(id || "").replace(/\.[^.]+$/, "").toLowerCase() ===
        String(docId || "").replace(/\.[^.]+$/, "").toLowerCase()
  );

  const fileDocCount = fileDocIds.length;

  const effectiveIsFirstDoc = isFileView
    ? fileDocIndex <= 0
    : Boolean((reviewNav as any).is_first_doc);

  const effectiveIsLastDoc = isFileView
    ? fileDocIndex >= fileDocCount - 1
    : Boolean((reviewNav as any).is_last_doc);

  const effectiveDocPositionLabel = isFileView
    ? fileDocIndex >= 0 && fileDocCount > 0
      ? `Doc ${fileDocIndex + 1} of ${fileDocCount}`
      : ""
    : docPositionLabel;

  const effectiveCurrentDocIndex = isFileView
    ? fileDocIndex
    : currentDocIndex;

  const effectiveDocCount = isFileView
    ? fileDocCount
    : batchDocCount;

  function openDoc(targetDocId: string) {
    if (!targetDocId) return;

    router.push(buildReviewDocUrl(targetDocId));
  }

  function goBatchFirstDoc() {
    const ids = getBatchDocIds();
    openDoc(ids[0] || "");
  }

  function goBatchPreviousDoc() {
    const ids = getBatchDocIds();
    const previousDocId =
      (reviewNav as any).previous_doc_id ||
      (
        currentDocIndex > 0
          ? ids[currentDocIndex - 1]
          : ""
      );

    openDoc(previousDocId);
  }

  function goBatchNextDoc() {
    const ids = getBatchDocIds();
    const nextDocId =
      (reviewNav as any).next_doc_id ||
      (
        currentDocIndex >= 0 &&
        currentDocIndex < ids.length - 1
          ? ids[currentDocIndex + 1]
          : ""
      );

    openDoc(nextDocId);
  }

  function goBatchLastDoc() {
    const ids = getBatchDocIds();
    openDoc(ids[ids.length - 1] || "");
  }

  function goFileFirstDoc() {
    openDoc(fileDocIds[0] || "");
  }

  function goFilePreviousDoc() {
    if (fileDocIndex > 0) {
      openDoc(fileDocIds[fileDocIndex - 1]);
    }
  }

  function goFileNextDoc() {
    if (fileDocIndex >= 0 && fileDocIndex < fileDocIds.length - 1) {
      openDoc(fileDocIds[fileDocIndex + 1]);
    }
  }

  function goFileLastDoc() {
    openDoc(fileDocIds[fileDocIds.length - 1] || "");
  }

  return (
    <AppShell>
      <div className="min-h-screen flex flex-col text-white">
        <ReviewHeader
          project={reviewDoc.project}
          batch={
            isFileView
              ? "File View"
              : reviewDoc.batch
          }
          docId={reviewDoc.doc_id}
          isFirstDoc={effectiveIsFirstDoc}
          isLastDoc={effectiveIsLastDoc}
          docPositionLabel={effectiveDocPositionLabel}
          currentDocIndex={effectiveCurrentDocIndex}
          batchDocCount={effectiveDocCount}
          onFirstDoc={isFileView ? goFileFirstDoc : goBatchFirstDoc}
          onPreviousDoc={isFileView ? goFilePreviousDoc : goBatchPreviousDoc}
          onNextDoc={isFileView ? goFileNextDoc : goBatchNextDoc}
          onLastDoc={isFileView ? goFileLastDoc : goBatchLastDoc}
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