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

type SavedSummaryLink = {
  link_id?: string;
  batch_summary_set_id?: string;
  source_doc_id?: string;
  source_pdf_name?: string;
  source_pdf_path?: string;
  summary_id?: string;
  section_id?: string;
  source_outline_index?: number | null;
  summary_number?: number | null;
  title?: string;
  citation?: string;
  original_summary?: string;
  qc_summary?: string;
  pdf_viewer_page?: number | null;
  pdfViewerPage?: number | null;
  page?: number | null;
  page_start?: number | null;
  page_end?: number | null;
  pdf_page?: number | null;
  summary_pdf_page?: number | null;
  insyt_anchor_id?: string | null;
  linked?: boolean;
  status?: string;
  saved_by?: string;
  saved_at?: string;
  updated_at?: string;
};

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

  const [activeSummarySetId, setActiveSummarySetId] = useState(summarySetId);

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

  const [currentPdfViewerPage, setCurrentPdfViewerPage] =
    useState<number | null>(null);

  const [currentSourceOutlineIndex, setCurrentSourceOutlineIndex] =
    useState<number | null>(null);

  const [savedSummaryLinks, setSavedSummaryLinks] =
    useState<SavedSummaryLink[]>([]);

  const outlineId = searchParams.get("outline") || "";
  const pageParam = searchParams.get("page") || "";
  const activePdfPage = pageParam ? Number(pageParam) : undefined;

  const [qcPaneWidth, setQcPaneWidth] = useState(544);
  const [isResizing, setIsResizing] = useState(false);
  

  // =====================================================
  // PDF Outline Controller State
  // =====================================================

  const [currentOutlineTitle, setCurrentOutlineTitle] =
    useState("");


  function toPositivePage(value: unknown) {
    const page = Number(value);

    if (Number.isFinite(page) && page > 0) {
      return page;
    }

    return null;
  }

  function getPdfViewerPage(item: any) {
    return (
      toPositivePage(item?.pdf_viewer_page) ??
      toPositivePage(item?.pdfViewerPage) ??
      toPositivePage(item?.summaryPdfPage) ??
      toPositivePage(item?.summary_pdf_page) ??
      toPositivePage(item?.pdfPage) ??
      toPositivePage(item?.pdf_page) ??
      toPositivePage(item?.page) ??
      toPositivePage(item?.pageStart) ??
      toPositivePage(item?.page_start) ??
      1
    );
  }

  function getSourceOutlineIndex(item: any) {
    return (
      toPositivePage(item?.source_outline_index) ??
      toPositivePage(item?.sourceOutlineIndex) ??
      toPositivePage(item?.summary_number) ??
      toPositivePage(item?.summaryNumber) ??
      toPositivePage(item?.section_index) ??
      toPositivePage(item?.sectionIndex) ??
      null
    );
  }

  function handleOutlineSelect(item: PdfOutlineItem) {
    const targetPage = getPdfViewerPage(item);
    const sourceOutlineIndex = getSourceOutlineIndex(item);

    console.log("SUMMARY OUTLINE PAGE JUMP:", {
      id: item.id,
      title: item.title,
      source_outline_index: sourceOutlineIndex,
      pdf_viewer_page: (item as any).pdf_viewer_page,
      pdfViewerPage: (item as any).pdfViewerPage,
      page: item.page,
      pageStart: item.pageStart,
      targetPage,
    });

    setSelectedSummaryDocId(item.id);

    setCurrentOutlineTitle(item.title);
    setCurrentCitation(item.citation || "");

    setTargetPdfPage(targetPage);
    setCurrentPdfViewerPage(targetPage);
    setCurrentSourceOutlineIndex(sourceOutlineIndex);

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
    setActiveSummarySetId(summarySetId);
  }, [summarySetId]);

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
          setActiveSummarySetId(effectiveSummarySetId);
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

          setSavedSummaryLinks(
            (response?.qc?.saved_summaries || []).filter(
              (item: SavedSummaryLink) => item?.linked !== false
            )
          );

          const incomingOutlineItems =
            items.map((item: any, index: number) => {
              const pdfViewerPage = getPdfViewerPage(item);
              const sourceOutlineIndex = getSourceOutlineIndex(item);

              return {
                id: item.summary_id || `summary-${sourceOutlineIndex || index + 1}`,
                title:
                  item.title ||
                  item.section_id ||
                  `Summary ${sourceOutlineIndex || index + 1}`,
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

                source_outline_index: sourceOutlineIndex,
                summary_number: sourceOutlineIndex,

                /*
                  Canonical permanent source PDF jump location.
                  This value belongs to the summary itself, not the Summary Set slice.
                */
                pdf_viewer_page: pdfViewerPage,
                pdfViewerPage,

                insyt_anchor_id:
                  item.insyt_anchor_id ||
                  item.insytAnchorId ||
                  null,

                /*
                  Backward-compatible fields are all normalized from pdfViewerPage.
                  Do not recalculate these from the Summary Set local index.
                */
                page: pdfViewerPage,
                pageStart: pdfViewerPage,
                pageEnd: pdfViewerPage,
                pdfPage: pdfViewerPage,
                pdf_page: pdfViewerPage,
                summaryPdfPage: pdfViewerPage,
                summary_pdf_page: pdfViewerPage,
              };
            }) || [];

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
            batch_doc_ids: [
              batch.source_doc_id ||
                response?.summary_set?.source_doc_id ||
                effectiveSummarySetId,
            ],
            batch_doc_index: 0,
            batch_doc_count: 1,
            is_first_doc: true,
            is_last_doc: true,
            is_summary_set_review: true,
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
        setSavedSummaryLinks([]);

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

  function getCurrentUsername() {
    try {
      return (
        JSON.parse(localStorage.getItem("insyt_user") || "{}")?.username ||
        user?.username ||
        ""
      );
    } catch {
      return user?.username || "";
    }
  }

  function editLinkedQcSave(link: SavedSummaryLink) {
    const targetSummaryId = link.summary_id || "";

    const matchingOutlineItem = outlineItems.find((item: any) => {
      return String(item.id || "") === String(targetSummaryId);
    });

    if (matchingOutlineItem) {
      handleOutlineSelect(matchingOutlineItem);
    } else {
      setSelectedSummaryDocId(targetSummaryId);
      setCurrentOutlineTitle(link.title || targetSummaryId);
      setCurrentCitation(link.citation || "");
      setOriginalSummary(link.original_summary || "");
    }

    setQcSummary(link.qc_summary || link.original_summary || "");

    const linkedPage = getPdfViewerPage(link);
    const linkedSourceOutlineIndex = getSourceOutlineIndex(link);

    if (linkedPage) {
      setTargetPdfPage(linkedPage);
      setCurrentPdfViewerPage(linkedPage);
    }

    setCurrentSourceOutlineIndex(linkedSourceOutlineIndex);
  }

  async function unlinkLinkedQcSave(link: SavedSummaryLink) {
    if (!clientId || !projectId || !activeSummarySetId || !link.summary_id) {
      return;
    }

    const confirmed = window.confirm(
      `Unlink this QC Save from the Summary Set?\n\n${link.title || link.summary_id}`
    );

    if (!confirmed) return;

    try {
      await apiPost("/api/summaries/summary-sets/unlink", {
        client: clientId,
        project: projectId,
        batch_summary_set_id:
          link.batch_summary_set_id || activeSummarySetId,
        summary_id: link.summary_id,
        acted_by: getCurrentUsername(),
      });

      setSavedSummaryLinks((current) =>
        current.filter((item) => item.summary_id !== link.summary_id)
      );
    } catch (error) {
      console.error(error);
      setError("Failed to unlink QC Save.");
    }
  }

  async function deleteLinkedQcSave(link: SavedSummaryLink) {
    if (!clientId || !projectId || !activeSummarySetId || !link.summary_id) {
      return;
    }

    const confirmed = window.confirm(
      `Delete this QC Save from the Summary Set?\n\n${link.title || link.summary_id}`
    );

    if (!confirmed) return;

    try {
      await apiPost("/api/summaries/summary-sets/delete", {
        client: clientId,
        project: projectId,
        batch_summary_set_id:
          link.batch_summary_set_id || activeSummarySetId,
        summary_id: link.summary_id,
        acted_by: getCurrentUsername(),
      });

      setSavedSummaryLinks((current) =>
        current.filter((item) => item.summary_id !== link.summary_id)
      );
    } catch (error) {
      console.error(error);
      setError("Failed to delete QC Save.");
    }
  }

  async function saveQcSummary(
    summaryDocId: string,
    updatedQcSummary: string,
    saveType: "edited" | "no_qc_needed" = "edited"
  ) {
    if (!projectId || !clientId || !reviewDoc) return;

    const pdfName =
      reviewDoc.native_blob?.split("/").pop() ||
      reviewDoc.doc_id ||
      "Unknown PDF";

    const title =
      currentOutlineTitle ||
      summaryDocId;

    if (activeSummarySetId) {
      const response = await apiPost("/api/summaries/summary-sets/save", {
        client: clientId,
        project: projectId,
        batch_summary_set_id: activeSummarySetId,
        summary_id: summaryDocId,
        section_id: selectedSummaryDocId || "",
        title,
        citation: currentCitation || "",
        original_summary: originalSummary || "",
        qc_summary: updatedQcSummary,
        save_type: saveType,
        saved_by:
          JSON.parse(localStorage.getItem("insyt_user") || "{}")?.username ||
          "",

        /*
          Preserve permanent source location for Completed QC Summaries,
          Saved QC rows, and future single-click reopen/edit flows.
        */
        pdf_viewer_page:
          currentPdfViewerPage ||
          targetPdfPage ||
          activePdfPage ||
          null,
        source_outline_index: currentSourceOutlineIndex,
        summary_number: currentSourceOutlineIndex,
      });

      const savedRow = response?.saved_row;

      if (savedRow) {
        setSavedSummaryLinks((current) => {
          const others = current.filter(
            (item) => item.summary_id !== savedRow.summary_id
          );

          return [...others, savedRow];
        });
      }

      /*
        Mirror Summary Set QC saves into the project-level Summary Data table
        so the Saved QC Summaries sidebar and future PDF rebuilds see all
        reviewer work across all Summary Sets.
      */
      await apiPost("/api/summaries/summary-data/save", {
        client: clientId,
        project_id: projectId,
        batch_id: activeSummarySetId,
        pdf_name: pdfName,
        summary_doc_id: summaryDocId,
        summary_key: title,
        title,
        citation: currentCitation || "",
        original_summary: originalSummary || "",
        qc_summary: updatedQcSummary,
        pdf_viewer_page:
          currentPdfViewerPage ||
          targetPdfPage ||
          activePdfPage ||
          null,
        source_outline_index: currentSourceOutlineIndex,
        summary_number: currentSourceOutlineIndex,
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
      pdf_viewer_page:
        currentPdfViewerPage ||
        targetPdfPage ||
        activePdfPage ||
        null,
      source_outline_index: currentSourceOutlineIndex,
      summary_number: currentSourceOutlineIndex,
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

  const isSummarySetReview = Boolean(activeSummarySetId);

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

    if (activeSummarySetId) {
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

  const effectiveIsFirstDoc = isSummarySetReview
    ? true
    : isFileView
      ? fileDocIndex <= 0
      : Boolean((reviewNav as any).is_first_doc);

  const effectiveIsLastDoc = isSummarySetReview
    ? true
    : isFileView
      ? fileDocIndex >= fileDocCount - 1
      : Boolean((reviewNav as any).is_last_doc);

  const effectiveDocPositionLabel = isSummarySetReview
    ? "Doc 1 of 1"
    : isFileView
      ? fileDocIndex >= 0 && fileDocCount > 0
        ? `Doc ${fileDocIndex + 1} of ${fileDocCount}`
        : ""
      : docPositionLabel;

  const effectiveCurrentDocIndex = isSummarySetReview
    ? 0
    : isFileView
      ? fileDocIndex
      : currentDocIndex;

  const effectiveDocCount = isSummarySetReview
    ? 1
    : isFileView
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
          hideDocNavigation={isSummarySetReview}
        />

        <section className="flex-1 flex gap-4 p-4 items-stretch overflow-hidden">

          {/* Native PDF Viewer */}
          <div className="flex-1 min-w-0 self-stretch flex flex-col gap-3 overflow-hidden">
            <div className="min-h-0 flex-1 overflow-hidden">
              <ReviewDocumentPane
                text={reviewDoc.text}
                nativeUrl={reviewDoc.native_url}
                nativeBlob={reviewDoc.native_blob}
                targetPage={targetPdfPage || activePdfPage}
              />
            </div>

            {isSummarySetReview && (
              <div className="shrink-0 rounded-2xl border border-slate-800 bg-slate-950 p-3">
                <div className="mb-2 flex items-center justify-between gap-3">
                  <div>
                    <h3 className="text-sm font-semibold text-white">
                      Linked QC Saves
                    </h3>
                    <p className="text-xs text-slate-500">
                      {savedSummaryLinks.length} linked save{savedSummaryLinks.length === 1 ? "" : "s"} for this Summary Set.
                    </p>
                  </div>
                </div>

                {savedSummaryLinks.length === 0 ? (
                  <p className="rounded-xl border border-slate-800 bg-slate-900 p-3 text-sm text-slate-400">
                    No linked QC saves yet.
                  </p>
                ) : (
                  <div className="max-h-48 overflow-y-auto rounded-xl border border-slate-800">
                    <table className="w-full min-w-[760px] text-left text-xs">
                      <thead>
                        <tr className="border-b border-slate-800 bg-slate-900 uppercase tracking-wide text-slate-500">
                          <th className="px-3 py-2">Summary</th>
                          <th className="px-3 py-2">Citation</th>
                          <th className="px-3 py-2">Status</th>
                          <th className="px-3 py-2">Saved By</th>
                          <th className="px-3 py-2">Saved At</th>
                          <th className="px-3 py-2 text-right">Actions</th>
                        </tr>
                      </thead>

                      <tbody>
                        {savedSummaryLinks.map((link) => (
                          <tr
                            key={link.link_id || link.summary_id}
                            className="border-b border-slate-800 last:border-b-0"
                          >
                            <td className="px-3 py-2 text-slate-200">
                              {link.title || link.summary_id || "—"}
                            </td>

                            <td className="px-3 py-2 text-slate-400">
                              {link.citation || "—"}
                            </td>

                            <td className="px-3 py-2">
                              <span className="rounded-full border border-slate-700 px-2 py-0.5 text-slate-300">
                                {link.status || "saved"}
                              </span>
                            </td>

                            <td className="px-3 py-2 text-slate-400">
                              {link.saved_by || "—"}
                            </td>

                            <td className="px-3 py-2 text-slate-400">
                              {link.saved_at || "—"}
                            </td>
                            <td className="px-3 py-2">
                              <div className="flex justify-end gap-2">
                                <button
                                  type="button"
                                  onClick={() => editLinkedQcSave(link)}
                                  className="rounded-full border border-sky-700 bg-sky-950 px-3 py-1 text-xs font-semibold text-sky-300 hover:bg-sky-900"
                                >
                                  Edit
                                </button>

                                <button
                                  type="button"
                                  onClick={() => unlinkLinkedQcSave(link)}
                                  className="rounded-full border border-amber-700 bg-amber-950 px-3 py-1 text-xs font-semibold text-amber-300 hover:bg-amber-900"
                                >
                                  Unlink
                                </button>

                                <button
                                  type="button"
                                  onClick={() => deleteLinkedQcSave(link)}
                                  className="rounded-full border border-red-700 bg-red-950 px-3 py-1 text-xs font-semibold text-red-300 hover:bg-red-900"
                                >
                                  Delete
                                </button>
                              </div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            )}
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