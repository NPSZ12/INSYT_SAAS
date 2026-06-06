"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import AppShell from "../../../../components/AppShell";
import ReviewHeader from "../../../../components/ReviewHeader";
import ReviewDocumentPane from "../../../../components/ReviewDocumentPane";
import ReviewCapturePanel from "../../../../components/ReviewCapturePanel";
import PageContainer from "../../../../components/PageContainer";
import PageHeader from "../../../../components/PageHeader";
import ContentCard from "../../../../components/ContentCard";
import LinkedEntitiesStrip from "../../../../components/LinkedEntitiesStrip";

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

type CaptureField = {
  section: string;
  label: string;
  type: string;
  format?: string;
  notes?: string;
};

type ReviewDocumentWithNav = ReviewDocument & {
  batch_doc_index?: number;
  batch_doc_count?: number;
  batch_doc_ids?: string[];
  is_first_doc?: boolean;
  is_last_doc?: boolean;
};

function normalizeDocLookup(value: string) {
  return decodeURIComponent(value || "")
    .trim()
    .replaceAll("_", " ")
    .replace(/\.[^.]+$/, "")
    .toLowerCase();
}

function getFileDocCandidates(item: any) {
  const blobName = String(item.blob_path || item.name || "");
  const fileName =
    String(item.file_name || item.filename || item.name || "")
      || blobName.split("/").pop()
      || "";

  return [
    item.doc_id,
    item.document_id,
    item.id,
    fileName,
    fileName.replace(/\.[^.]+$/, ""),
    blobName.split("/").pop() || "",
    (blobName.split("/").pop() || "").replace(/\.[^.]+$/, ""),
  ]
    .filter(Boolean)
    .map((value) => normalizeDocLookup(String(value)));
}

function ReviewPageContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  

  const clientId = searchParams.get("client") || "";
  const projectId = searchParams.get("project") || "";
  const batchId = searchParams.get("batch") || "";
  const docId = searchParams.get("doc") || "";

  const [error, setError] = useState("");
  const [protocolMessage, setProtocolMessage] = useState("");
  const [reviewDoc, setReviewDoc] = useState<ReviewDocument | null>(null);
  const [protocolFields, setProtocolFields] = useState<ProtocolField[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [linkedEntities, setLinkedEntities] = useState<any[]>([]);
  const [fileDocIds, setFileDocIds] = useState<string[]>([]);
  const isFileView = Boolean(docId && !batchId);

  useEffect(() => {
    if (!projectId || (!batchId && !docId)) {
      return;
    }

    setIsLoading(true);
    setError("");
    setReviewDoc(null);

    if (docId && !batchId) {
      apiGet(
        `/api/review/current?client=${encodeURIComponent(
          clientId
        )}&project=${encodeURIComponent(
          projectId
        )}&doc=${encodeURIComponent(docId)}`
      )
        .then((response) => {
          setReviewDoc(response);
        })
        .catch((error) => {
          console.error(error);
          setError(String(error?.message || "Failed to open document directly."));
        })
        .finally(() => {
          setIsLoading(false);
        });

      return;
    }

    const params = new URLSearchParams({
      client: clientId,
      project: projectId,
      batch: batchId,
    });

    if (docId) {
      params.set("doc", docId);
    }

    apiGet(`/api/review/current?${params.toString()}`)
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
    if (!projectId || !isFileView) {
      setFileDocIds([]);
      return;
    }

    apiGet(
      `/api/capture/files?client=${encodeURIComponent(
        clientId
      )}&project=${encodeURIComponent(
        projectId
      )}&folder=${encodeURIComponent("source/native")}`
    )
      .then((files: any[]) => {
        const docIds = files
          .map((file) => file.doc_id || file.file_name || "")
          .filter(Boolean);

        setFileDocIds(docIds);
      })
      .catch(console.error);
  }, [clientId, projectId, isFileView]);
  
  useEffect(() => {
    if (!projectId || !reviewDoc?.doc_id) return;

    apiGet(
      `/api/entities/document?client=${encodeURIComponent(
        clientId
      )}&workspace=capture&project=${encodeURIComponent(
        projectId
      )}&batch=${encodeURIComponent(
        batchId
      )}&doc=${encodeURIComponent(
        reviewDoc.doc_id
      )}&view=raw`
    )
      .then((entities: any[]) => {
        setLinkedEntities(
          entities.map((entity: any, index: number) => ({
            id: entity.id ?? index + 1,
            docId: entity.doc_id,
            linked: entity.linked ?? true,
            values: entity.values || {},
          }))
        );
      })
      .catch(console.error);
  }, [clientId, projectId, batchId, reviewDoc?.doc_id]);
  
  useEffect(() => {
    if (!projectId) {
      return;
    }

    setProtocolMessage("Loading saved protocol fields...");
    setProtocolFields([]);

    apiGet(
      `/api/capture/projects/${encodeURIComponent(
        projectId
      )}/protocol?client=${encodeURIComponent(clientId)}`
    )
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
  }, [clientId, projectId]);

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

  console.log("FIELDS FOR CAPTURE INPUT", {
    protocolFieldsLength: protocolFields.length,
    protocolFields,
  });

  

  const fieldsForCapture: CaptureField[] = protocolFields.map((field) => {
    const fieldFormat = field.format || field.default_format || "";

    return {
      section: field.section || "General",
      label: field.data_element,
      type: fieldFormat.toLowerCase().includes("tag") ? "tag" : "text",
      format: fieldFormat,
      notes: field.notes || "",
    };
  });

  const reviewNav = reviewDoc as ReviewDocument & {
    previous_doc_id?: string;
    next_doc_id?: string;
    is_first_doc?: boolean;
    is_last_doc?: boolean;
    batch_doc_index?: number;
    batch_doc_count?: number;
  };

  function buildReviewDocUrl(targetDocId: string) {
    const params = new URLSearchParams({
      client: clientId,
      project: projectId,
      batch: batchId,
      doc: targetDocId,
    });

    return `/capture/review/doc?${params.toString()}`;
  }

  function getBatchDocIds() {
    return ((reviewNav as any).batch_doc_ids || []) as string[];
  }

  function getCurrentDocIndex() {
    return Number((reviewNav as any).batch_doc_index ?? -1);
  }

  function goFirstDoc() {
    const batchDocIds = getBatchDocIds();
    const firstDocId = batchDocIds[0] || "";

    if (!firstDocId) return;

    router.push(buildReviewDocUrl(firstDocId));
  }

  function goLastDoc() {
    const batchDocIds = getBatchDocIds();
    const lastDocId = batchDocIds[batchDocIds.length - 1] || "";

    if (!lastDocId) return;

    router.push(buildReviewDocUrl(lastDocId));
  }

  const currentDocIndex = getCurrentDocIndex();
  const batchDocCount =
    Number((reviewNav as any).batch_doc_count || getBatchDocIds().length || 0);

  const docPositionLabel =
    currentDocIndex >= 0 && batchDocCount > 0
      ? `Doc ${currentDocIndex + 1} of ${batchDocCount}`
      : "";

  function goPreviousDoc() {
    const batchDocIds = getBatchDocIds();
    const currentIndex = getCurrentDocIndex();

    const previousDocId =
      reviewNav.previous_doc_id ||
      (
        currentIndex > 0
          ? batchDocIds[currentIndex - 1]
          : ""
      );

    if (!previousDocId) return;

    router.push(buildReviewDocUrl(previousDocId));
  }

  function goNextDoc() {
    const batchDocIds = getBatchDocIds();
    const currentIndex = getCurrentDocIndex();

    const nextDocId =
      reviewNav.next_doc_id ||
      (
        currentIndex >= 0 &&
        currentIndex < batchDocIds.length - 1
          ? batchDocIds[currentIndex + 1]
          : ""
      );

    if (!nextDocId) return;

    router.push(buildReviewDocUrl(nextDocId));
  }

  function exitReview() {
    const params = new URLSearchParams({
      client: clientId,
      project: projectId,
    });

    router.push(`/capture/batch-management?${params.toString()}`);
  }

  function handleSaveComplete() {
    if (reviewNav.is_last_doc) {
      exitReview();
      return;
    }

    goNextDoc();
  }

  const fileDocIndex = fileDocIds.findIndex(
    (id) =>
      normalizeDocLookup(id) === normalizeDocLookup(reviewDoc?.doc_id || "") ||
      normalizeDocLookup(id) === normalizeDocLookup(docId)
  );

  const fileDocCount = fileDocIds.length;

  function openFileViewDoc(nextDocId: string) {
    const params = new URLSearchParams();

    if (clientId) params.set("client", clientId);
    if (projectId) params.set("project", projectId);
    if (nextDocId) params.set("doc", nextDocId);

    router.push(`/capture/review/doc?${params.toString()}`);
  }

  function goFileFirstDoc() {
    if (fileDocIds[0]) openFileViewDoc(fileDocIds[0]);
  }

  function goFilePreviousDoc() {
    if (fileDocIndex > 0) openFileViewDoc(fileDocIds[fileDocIndex - 1]);
  }

  function goFileNextDoc() {
    if (fileDocIndex >= 0 && fileDocIndex < fileDocIds.length - 1) {
      openFileViewDoc(fileDocIds[fileDocIndex + 1]);
    }
  }

  function goFileLastDoc() {
    if (fileDocIds.length > 0) {
      openFileViewDoc(fileDocIds[fileDocIds.length - 1]);
    }
  }

  function editLinkedEntity(entity: any) {
    console.log("Edit linked entity", entity);
  }

  function unlinkEntity(entityId: number) {
    setLinkedEntities((current) =>
      current.map((entity) =>
        entity.id === entityId
          ? { ...entity, linked: false }
          : entity
      )
    );
  }

  function deleteEntity(entityId: number) {
    const confirmed = window.confirm(
      "Confirm Deletion: This will permanently remove this linked entity from the project. Continue?"
    );

    if (!confirmed) return;

    setLinkedEntities((current) =>
      current.filter((entity) => entity.id !== entityId)
    );
  }

  return (
    <AppShell>
      <div className="min-h-screen flex flex-col text-white">
        <ReviewHeader
          project={reviewDoc.project}
          batch={isFileView ? "File View" : reviewDoc.batch}
          docId={reviewDoc.doc_id}
          isFirstDoc={
            isFileView
              ? fileDocIndex <= 0
              : Boolean(reviewNav.is_first_doc)
          }
          isLastDoc={
            isFileView
              ? fileDocIndex >= fileDocCount - 1
              : Boolean(reviewNav.is_last_doc)
          }
          docPositionLabel={
            isFileView
              ? fileDocIndex >= 0 && fileDocCount > 0
                ? `Doc ${fileDocIndex + 1} of ${fileDocCount}`
                : ""
              : docPositionLabel
          }
          onFirstDoc={isFileView ? goFileFirstDoc : goFirstDoc}
          onPreviousDoc={isFileView ? goFilePreviousDoc : goPreviousDoc}
          onNextDoc={isFileView ? goFileNextDoc : goNextDoc}
          onLastDoc={isFileView ? goFileLastDoc : goLastDoc}
        />

        {protocolMessage && (
          <div className="mx-4 mt-4 rounded-xl border border-amber-700 bg-amber-950/40 px-4 py-3 text-sm text-amber-200">
            {protocolMessage}
          </div>
        )}

        <section className="flex-1 flex flex-col gap-4 p-4 overflow-hidden">
          <div className="flex-1 grid grid-cols-3 gap-4 min-h-0">
            <ReviewDocumentPane
              text={reviewDoc.text}
              nativeUrl={reviewDoc.native_url}
              nativeBlob={reviewDoc.native_blob}
            />

            {fieldsForCapture.length === 0 ? (
              <aside className="bg-slate-900 border border-slate-800 rounded-2xl p-6 overflow-y-auto h-full">
                <h2 className="text-lg font-semibold mb-4 text-white">
                  Capture Panel
                </h2>

                <p className="text-sm text-amber-200 rounded-xl border border-amber-700 bg-amber-950/40 px-4 py-3">
                  No protocol capture fields loaded for this project.
                </p>
              </aside>
            ) : (
              <ReviewCapturePanel
                clientId={clientId}
                workspace="capture"
                projectId={projectId}
                batchId={batchId}
                docId={reviewDoc.doc_id}
                fields={fieldsForCapture}
                isFirstDoc={Boolean(reviewNav.is_first_doc)}
                isLastDoc={Boolean(reviewNav.is_last_doc)}
                onPreviousDoc={isFileView ? goFilePreviousDoc : goPreviousDoc}
                onNextDoc={isFileView ? goFileNextDoc : goNextDoc}
                onSaveComplete={handleSaveComplete}
              />
            )}
          </div>

          <LinkedEntitiesStrip
            fields={fieldsForCapture}
            linkedEntities={linkedEntities}
            onEdit={editLinkedEntity}
            onUnlink={unlinkEntity}
            onDelete={deleteEntity}
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