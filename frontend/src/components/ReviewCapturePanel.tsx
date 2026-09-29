"use client";

import { useEffect, useState } from "react";

import {
  apiGet,
  apiPost,
} from "../lib/api";

import Button from "./Button";
import Input from "./Input";
import TextArea from "./TextArea";
import FormLabel from "./FormLabel";
import Checkbox from "./Checkbox";

type CaptureField = {
  section: string;
  label: string;
  type: string;
  format?: string;
  notes?: string;
};

type AiEntityCandidate = {
  id: string;
  status?: "pending" | "approved" | "rejected";
  confidence?: number | null;
  values: Record<string, string | boolean>;
  source_text?: string;
  source_page?: number | null;
  source_field?: string;
  source_record_id?: string;
};

type AiEntityApprovalResult = {
  candidateId: string;
  values: Record<string, string | boolean>;
};

type QcSeverityModel = {
  severity: string;
  weight: number;
  description?: string;
};

type QcScoringModel = {
  Critical?: QcSeverityModel;
  Important?: QcSeverityModel;
  Minimal?: QcSeverityModel;
  Informational?: QcSeverityModel;
};

type QcGuideItem = {
  severity: string;
  weight: number;
  category: string;
  error_type: string;
  description: string;
};

type ReviewCapturePanelProps = {
  projectId: string;
  batchId: string;
  docId: string;
  fields: CaptureField[];

  workspace?: "capture" | "discovery" | "summaries";
  clientId?: string;
  isFirstDoc?: boolean;
  isLastDoc?: boolean;
  hasLinkedEntities?: boolean;
  initialDocumentCoding?: string;
  onPreviousDoc?: () => void;
  onNextDoc?: () => void;
  onSaveComplete?: () => void;
  onLinkedEntitySaved?: () => void;
  editingEntity?: any | null;
  onEditComplete?: () => void;
  onEditCancel?: () => void;

  aiEntities?: AiEntityCandidate[];
  onApproveAiEntity?: (
    result: AiEntityApprovalResult
  ) => void;
  onRejectAiEntity?: (candidateId: string) => void;
};

export default function ReviewCapturePanel({
  projectId,
  batchId,
  docId,
  fields,
  workspace = "capture",
  clientId = "",
  isFirstDoc = false,
  isLastDoc = false,
  hasLinkedEntities = false,
  initialDocumentCoding = "",
  onPreviousDoc,
  onNextDoc,
  onSaveComplete,
  onLinkedEntitySaved,
  editingEntity = null,
  onEditComplete,
  onEditCancel,
  aiEntities = [],
  onApproveAiEntity,
  onRejectAiEntity,
}: ReviewCapturePanelProps) {
  const [values, setValues] = useState<Record<string, string | boolean>>({});

  const [selectedAiEntityId, setSelectedAiEntityId] =
    useState<string>("");

  const selectedAiEntity =
    aiEntities.find(
      (candidate) =>
        candidate.id === selectedAiEntityId
    ) || null;

  const [message, setMessage] = useState("");
  const [localLinkedEntityAttached, setLocalLinkedEntityAttached] = useState(false);

  const [openSections, setOpenSections] =
    useState<Record<string, boolean>>({});

  const [documentCoding, setDocumentCoding] =
    useState("");

  const [furtherReviewReason, setFurtherReviewReason] =
    useState("");

  const [qcCoding, setQcCoding] = useState("");
  const [qcQuestions, setQcQuestions] = useState("");

  const [qcCriticalCount, setQcCriticalCount] =
    useState(0);

  const [qcImportantCount, setQcImportantCount] =
    useState(0);

  const [qcMinimalCount, setQcMinimalCount] =
    useState(0);

  const [qcInformationalCount, setQcInformationalCount] =
    useState(0);

  const [showQcSeverityGuide, setShowQcSeverityGuide] =
    useState(false);

  const [
    qcScoringModel,
    setQcScoringModel,
  ] = useState<QcScoringModel>({});

  const [
    qcScoringGuide,
    setQcScoringGuide,
  ] = useState<QcGuideItem[]>([]);

  const [
    qcScoringLoading,
    setQcScoringLoading,
  ] = useState(false);

  const [
    qcScoringError,
    setQcScoringError,
  ] = useState("");

  const qcCriticalWeight =
    Number(
      qcScoringModel.Critical?.weight
    ) || 0;

  const qcImportantWeight =
    Number(
      qcScoringModel.Important?.weight
    ) || 0;

  const qcMinimalWeight =
    Number(
      qcScoringModel.Minimal?.weight
    ) || 0;

  const qcInformationalWeight =
    Number(
      qcScoringModel.Informational?.weight
    ) || 0;

  const qcWeightedErrorPoints =
    qcCriticalCount *
      qcCriticalWeight +
    qcImportantCount *
      qcImportantWeight +
    qcMinimalCount *
      qcMinimalWeight +
    qcInformationalCount *
      qcInformationalWeight;

  const qcWeightedScore = Math.max(
    0,
    100 - qcWeightedErrorPoints
  );

  useEffect(() => {
    const initialOpenState: Record<string, boolean> = {};

    fields.forEach((field) => {
      const section = field.section || "General";

      initialOpenState[section] = false;
    });

    setOpenSections(initialOpenState);
  }, [fields]);

  const isInitialNotResponsiveCoding =
    initialDocumentCoding === "Not Responsive" ||
    initialDocumentCoding === "Not Responsive - AI";

  const forceResponsive =
    !isInitialNotResponsiveCoding &&
    (hasLinkedEntities || localLinkedEntityAttached);

  const isBatchReview = Boolean(batchId);

  const isQcBatch =
    String(batchId || "").startsWith("QC_");

  useEffect(() => {
    if (!isQcBatch) {
      setQcScoringModel({});
      setQcScoringGuide([]);
      setQcScoringError("");
      setQcScoringLoading(false);
      return;
    }

    let cancelled = false;

    async function loadQcScoringModel() {
      setQcScoringLoading(true);
      setQcScoringError("");

      try {
        const params =
          new URLSearchParams({
            workspace,
            client: clientId,
            project: projectId,
          });

        const response =
          await apiGet(
            `/api/review/qc-scoring-model?${params.toString()}`
          );

        if (cancelled) {
          return;
        }

        setQcScoringModel(
          response?.model || {}
        );

        setQcScoringGuide(
          Array.isArray(response?.guide)
            ? response.guide
            : []
        );

      } catch (error) {
        console.error(
          "Failed to load QC scoring model:",
          error
        );

        if (!cancelled) {
          setQcScoringModel({});
          setQcScoringGuide([]);
          setQcScoringError(
            "Unable to load QC scoring model."
          );
        }
      } finally {
        if (!cancelled) {
          setQcScoringLoading(false);
        }
      }
    }

    loadQcScoringModel();

    return () => {
      cancelled = true;
    };
  }, [
    isQcBatch,
    workspace,
    clientId,
    projectId,
  ]);

  useEffect(() => {
    setLocalLinkedEntityAttached(false);

    setQcCriticalCount(0);
    setQcImportantCount(0);
    setQcMinimalCount(0);
    setQcInformationalCount(0);
    setShowQcSeverityGuide(false);
  }, [docId]);

  useEffect(() => {
    const firstPending =
      aiEntities.find(
        (candidate) =>
          candidate.status !== "approved" &&
          candidate.status !== "rejected"
      ) || aiEntities[0];

    setSelectedAiEntityId(
      firstPending?.id || ""
    );
  }, [docId, aiEntities]);

  useEffect(() => {
    if (forceResponsive) {
      setDocumentCoding("Responsive");
    }
  }, [forceResponsive]);

  useEffect(() => {
    if (initialDocumentCoding) {
      setDocumentCoding(initialDocumentCoding);
    }
  }, [docId, initialDocumentCoding]);

  useEffect(() => {
    if (!editingEntity) return;

    const incomingValues = editingEntity.values || {};

    const cleanValues = Object.fromEntries(
      Object.entries(incomingValues).filter(
        ([key]) => key.toUpperCase() !== "UCID"
      )
    );

    setValues(cleanValues as Record<string, string | boolean>);
    setMessage(`Editing ${editingEntity.ucid || editingEntity.UCID || "linked entity"}.`);
  }, [editingEntity]);

  useEffect(() => {
    if (!selectedAiEntity) {
      return;
    }

    const incomingValues =
      selectedAiEntity.values || {};

    const cleanValues =
      Object.fromEntries(
        Object.entries(incomingValues).filter(
          ([key]) =>
            key.toUpperCase() !== "UCID"
        )
      );

    setValues(
      cleanValues as Record<
        string,
        string | boolean
      >
    );

    setMessage(
      `AI Entity ${Math.max(
        1,
        aiEntities.findIndex(
          (candidate) =>
            candidate.id ===
            selectedAiEntity.id
        ) + 1
      )} loaded for review.`
    );

    //
    // Expand any Capture sections containing
    // AI-populated values so the reviewer can
    // immediately see what AI extracted.
    //
    setOpenSections((current) => {
      const next = { ...current };

      for (const field of fields) {
        const value =
          cleanValues[field.label];

        const hasValue =
          typeof value === "boolean"
            ? value
            : String(value ?? "").trim() !== "";

        if (hasValue) {
          next[
            field.section || "General"
          ] = true;
        }
      }

      return next;
    });
  }, [
    selectedAiEntity,
    aiEntities,
    fields,
  ]);

  function normalizeFieldType(field: CaptureField) {
    const typeText =
      `${field.type || ""} ${field.format || ""}`.toLowerCase();

    if (
      typeText.includes("tag") ||
      typeText.includes("checkbox") ||
      typeText.includes("boolean") ||
      typeText.includes("yes/no")
    ) {
      return "tag";
    }

    if (
      typeText.includes("textarea") ||
      typeText.includes("long text")
    ) {
      return "textarea";
    }

    return "text";
  }

  function updateValue(
    label: string,
    value: string | boolean
  ) {
    setValues((current) => ({
      ...current,
      [label]: value,
    }));
  }

  function toggleSection(section: string) {
    setOpenSections((current) => ({
      ...current,
      [section]: !current[section],
    }));
  }

  function clearValues() {
    setValues({});
  }

  function validateDocumentCoding() {
    if (!documentCoding) {
      setMessage(
        "Document Coding selection is required."
      );

      return false;
    }

    if (
      documentCoding === "Needs Further Review" &&
      !furtherReviewReason.trim()
    ) {
      setMessage(
        "Further Review reason is required."
      );

      return false;
    }

    if (
      isQcBatch &&
      (
        qcScoringLoading ||
        !qcScoringModel.Critical ||
        !qcScoringModel.Important ||
        !qcScoringModel.Minimal ||
        !qcScoringModel.Informational
      )
    ) {
      setMessage(
        qcScoringLoading
          ? "QC scoring model is still loading."
          : "QC scoring model is unavailable."
      );

      return false;
    }

    if (isQcBatch && !qcCoding) {
      setMessage("QC Coding selection is required.");

      return false;
    }

    if (isQcBatch && qcCoding === "QC-NFR" && !qcQuestions.trim()) {
      setMessage("QC-NFR questions are required.");

      return false;
    }

    return true;
  }

  function handleLinkEntity() {
    const hasAnyValue = Object.values(values).some(
      (value) => {
        if (typeof value === "boolean") {
          return value;
        }

        return String(value).trim() !== "";
      }
    );

    if (!hasAnyValue) {
      setMessage(
        "Add at least one captured value before linking an entity."
      );

      return;
    }

    apiPost("/api/review/save", {
      workspace,
      client_id: clientId,
      project_id: projectId,
      batch_id: batchId,
      doc_id: docId,
      values,
    })
      .then(() => {
        setMessage("Entity linked.");
        setLocalLinkedEntityAttached(true);
        setDocumentCoding("Responsive");
        clearValues();
        onLinkedEntitySaved?.();
      })
      .catch(() => {
        setMessage(
          "Entity link failed. Please try again."
        );
      });
  }

  function handleUpdateLinkedEntity() {
    if (!editingEntity) return;

    const ucid =
      editingEntity.ucid ||
      editingEntity.UCID ||
      editingEntity.values?.UCID ||
      "";

    if (!ucid) {
      setMessage("Cannot update linked entity without UCID.");
      return;
    }

    apiPost("/api/entities/update", {
      workspace,
      client: clientId,
      project: projectId,
      doc_id: docId,
      ucid,
      values,
    })
      .then(() => {
        setMessage("Linked entity updated.");
        setLocalLinkedEntityAttached(true);
        setDocumentCoding("Responsive");
        clearValues();
        onEditComplete?.();
      })
      .catch(() => {
        setMessage("Linked entity update failed.");
      });
  }

  function handleSaveNext() {
    if (!validateDocumentCoding()) {
      return;
    }

    const hasCapturedValues = Object.values(values).some((value) => {
      if (value === null || value === undefined) return false;
      return String(value).trim() !== "";
    });

    const hasPendingAiEntity =
      Boolean(selectedAiEntity) &&
      selectedAiEntity?.status !== "approved" &&
      selectedAiEntity?.status !== "rejected";

    const valuesToSave =
      hasPendingAiEntity ||
      (
        (
          documentCoding === "Not Responsive" ||
          documentCoding === "Not Responsive - AI"
        ) &&
        !hasCapturedValues
      )
        ? {}
        : values;

    apiPost("/api/review/save-next", {
      workspace,
      client_id: clientId,
      project_id: projectId,
      batch_id: batchId,
      doc_id: docId,
      values: valuesToSave,
      document_coding: documentCoding,
      further_review_reason: furtherReviewReason,
      qc_coding: isQcBatch ? qcCoding : "",
      qc_questions: isQcBatch ? qcQuestions : "",
      qc_critical_count:
        isQcBatch
          ? qcCriticalCount
          : 0,

      qc_important_count:
        isQcBatch
          ? qcImportantCount
          : 0,

      qc_minimal_count:
        isQcBatch
          ? qcMinimalCount
          : 0,

      qc_informational_count:
        isQcBatch
          ? qcInformationalCount
          : 0,
    })
      .then(() => {
        setMessage(
          isLastDoc
            ? "Document saved. Exiting review batch."
            : "Loading next document"
        );

        setValues({});
        setDocumentCoding("");
        setFurtherReviewReason("");
        setQcCoding("");
        setQcQuestions("");
        setQcCriticalCount(0);
        setQcImportantCount(0);
        setQcMinimalCount(0);
        setQcInformationalCount(0);
        setShowQcSeverityGuide(false);
        onSaveComplete?.();
      })
      .catch(() => {
        setMessage("Save & Next failed.");
      });
  }

  function handleSaveUpdate() {
    if (!validateDocumentCoding()) {
      return;
    }

    const hasCapturedValues = Object.values(values).some((value) => {
      if (value === null || value === undefined) return false;
      return String(value).trim() !== "";
    });

    const hasPendingAiEntity =
      Boolean(selectedAiEntity) &&
      selectedAiEntity?.status !== "approved" &&
      selectedAiEntity?.status !== "rejected";

    const valuesToSave =
      hasPendingAiEntity ||
      (
        (
          documentCoding === "Not Responsive" ||
          documentCoding === "Not Responsive - AI"
        ) &&
        !hasCapturedValues
      )
        ? {}
        : values;

    apiPost("/api/review/save", {
      workspace,
      client_id: clientId,
      project_id: projectId,
      batch_id: batchId,
      doc_id: docId,
      values: valuesToSave,
      document_coding: documentCoding,
      further_review_reason: furtherReviewReason,
      qc_coding: isQcBatch ? qcCoding : "",
      qc_critical_count:
        isQcBatch
          ? qcCriticalCount
          : 0,

      qc_important_count:
        isQcBatch
          ? qcImportantCount
          : 0,

      qc_minimal_count:
        isQcBatch
          ? qcMinimalCount
          : 0,

      qc_informational_count:
        isQcBatch
          ? qcInformationalCount
          : 0,
      qc_questions: isQcBatch ? qcQuestions : "",
    })
      .then(() => {
        setMessage("Saved Successfully.");

        setValues({});
        setQcCoding("");
        setQcQuestions("");
        setQcCriticalCount(0);
        setQcImportantCount(0);
        setQcMinimalCount(0);
        setQcInformationalCount(0);
        setShowQcSeverityGuide(false);
        onSaveComplete?.();
      })
      .catch(() => {
        setMessage("Save / Update failed.");
      });
  }

  const groupedFields =
    fields.reduce<Record<string, CaptureField[]>>(
      (groups, field) => {
        const section = field.section || "General";

        if (!groups[section]) {
          groups[section] = [];
        }

        groups[section].push(field);

        return groups;
      },
      {}
    );

  return (
    <aside className="insyt-panel h-full flex flex-col overflow-hidden">
      <div className="shrink-0 space-y-3 border-b border-[var(--insyt-border)] p-6">
        <Button
          fullWidth
          onClick={isBatchReview ? handleSaveNext : handleSaveUpdate}
        >
          {isBatchReview
            ? isLastDoc
              ? "Save & Exit"
              : "Save & Next"
            : "Save / Update"}
        </Button>

        {message && (
          <p className="text-sm font-medium text-emerald-500">
            {message}
          </p>
        )}

        {isQcBatch && (
          <div className="insyt-card p-4">
            <h3 className="mb-3 text-sm font-semibold text-[var(--insyt-text-primary)]">
              QC Coding
            </h3>

            <div className="space-y-2">
              {[
                "QC - No Change",
                "QC - Change",
                "QC-NFR",
              ].map((option) => (
                <label
                  key={option}
                  className="flex items-center gap-3 text-sm text-[var(--insyt-text-secondary)]"
                >
                  <input
                    type="radio"
                    name="qcCoding"
                    checked={qcCoding === option}
                    onChange={() =>
                      setQcCoding(option)
                    }
                    className="accent-sky-600"
                  />

                  <span>{option}</span>
                </label>
              ))}
            </div>

            <div className="mt-5 border-t border-[var(--insyt-border)] pt-4">
              <h4 className="mb-3 text-sm font-semibold text-[var(--insyt-text-primary)]">
                Weighted QC Findings
              </h4>
              {qcScoringLoading && (
                <p className="mb-3 text-xs text-[var(--insyt-text-muted)]">
                  Loading QC scoring model...
                </p>
              )}

              {qcScoringError && (
                <p className="mb-3 text-xs font-medium text-red-400">
                  {qcScoringError}
                </p>
              )}

              <div className="space-y-3">
                <QcCountRow
                  label="Critical"
                  weight={qcCriticalWeight}
                  value={qcCriticalCount}
                  onChange={setQcCriticalCount}
                />

                <QcCountRow
                  label="Important"
                  weight={qcImportantWeight}
                  value={qcImportantCount}
                  onChange={setQcImportantCount}
                />

                <QcCountRow
                  label="Minimal"
                  weight={qcMinimalWeight}
                  value={qcMinimalCount}
                  onChange={setQcMinimalCount}
                />

                <QcCountRow
                  label="Informational"
                  weight={qcInformationalWeight}
                  value={qcInformationalCount}
                  onChange={setQcInformationalCount}
                />
              </div>

              <div className="mt-4 grid grid-cols-2 gap-3">
                <div className="rounded-lg border border-[var(--insyt-border)] bg-[var(--insyt-surface-2)] p-3">
                  <div className="text-xs text-[var(--insyt-text-muted)]">
                    Weighted Deduction
                  </div>

                  <div className="mt-1 text-lg font-semibold text-[var(--insyt-text-primary)]">
                    {qcWeightedErrorPoints}
                  </div>
                </div>

                <div className="rounded-lg border border-[var(--insyt-border)] bg-[var(--insyt-surface-2)] p-3">
                  <div className="text-xs text-[var(--insyt-text-muted)]">
                    QC Score
                  </div>

                  <div className="mt-1 text-lg font-semibold text-[var(--insyt-text-primary)]">
                    {qcWeightedScore.toFixed(2)}
                  </div>
                </div>
              </div>

              <button
                type="button"
                onClick={() =>
                  setShowQcSeverityGuide(
                    (current) => !current
                  )
                }
                className="mt-4 text-sm font-semibold text-sky-400 hover:text-sky-300"
              >
                {showQcSeverityGuide
                  ? "Hide Severity Guide"
                  : "Show Severity Guide"}
              </button>

              {showQcSeverityGuide && (
                <div className="mt-3 space-y-4 rounded-lg border border-[var(--insyt-border)] bg-[var(--insyt-surface-2)] p-3 text-xs text-[var(--insyt-text-secondary)]">
                  {qcScoringGuide.length === 0 ? (
                    <div className="text-[var(--insyt-text-muted)]">
                      No active QC severity guide entries found.
                    </div>
                  ) : (
                    [
                      "Critical",
                      "Important",
                      "Minimal",
                      "Informational",
                    ].map((severity) => {
                      const items =
                        qcScoringGuide.filter(
                          (item) =>
                            item.severity === severity
                        );

                      if (items.length === 0) {
                        return null;
                      }

                      const weight =
                        items[0]?.weight ?? 0;

                      return (
                        <div key={severity}>
                          <div className="mb-2 font-semibold text-[var(--insyt-text-primary)]">
                            {severity} ×{weight}
                          </div>

                          <div className="space-y-2">
                            {items.map(
                              (
                                item,
                                index
                              ) => (
                                <div
                                  key={`${severity}-${item.error_type}-${index}`}
                                  className="rounded-md border border-[var(--insyt-border)] bg-[var(--insyt-surface-1)] p-2"
                                >
                                  <div className="font-medium text-[var(--insyt-text-primary)]">
                                    {item.error_type}
                                  </div>

                                  {item.category && (
                                    <div className="mt-0.5 text-[var(--insyt-text-muted)]">
                                      {item.category}
                                    </div>
                                  )}

                                  {item.description && (
                                    <div className="mt-1">
                                      {item.description}
                                    </div>
                                  )}
                                </div>
                              )
                            )}
                          </div>
                        </div>
                      );
                    })
                  )}
                </div>
              )}
            </div>

            {qcCoding === "QC-NFR" && (
              <div className="mt-4">
                <FormLabel>
                  QC Questions
                </FormLabel>

                <TextArea
                  rows={3}
                  value={qcQuestions}
                  onChange={setQcQuestions}
                />
              </div>
            )}
          </div>
        )}

        <div>
          <h2 className="insyt-section-title text-lg text-[var(--insyt-text-primary)]">
            Capture Panel
          </h2>

          {aiEntities.length > 0 && (
            <div className="mt-2 flex flex-wrap items-center gap-1.5">
              <span className="mr-1 text-sm font-semibold text-[var(--insyt-text-secondary)]">
                AI - Entities:
              </span>

              {aiEntities.map(
                (candidate, index) => {
                  const selected =
                    candidate.id ===
                    selectedAiEntityId;

                  const approved =
                    candidate.status ===
                    "approved";

                  const rejected =
                    candidate.status ===
                    "rejected";

                  return (
                    <button
                      key={candidate.id}
                      type="button"
                      onClick={() => {
                        setSelectedAiEntityId(
                          candidate.id
                        );
                      }}
                      title={
                        candidate.confidence != null
                          ? `AI Entity ${
                              index + 1
                            } - ${Math.round(
                              candidate.confidence *
                                100
                            )}% confidence`
                          : `AI Entity ${
                              index + 1
                            }`
                      }
                      className={[
                        "min-w-7 rounded-md border px-2 py-1 text-xs font-bold transition",
                        selected
                          ? "border-sky-400 bg-sky-500 text-white"
                          : approved
                            ? "border-emerald-500/70 bg-emerald-500/15 text-emerald-300"
                            : rejected
                              ? "border-red-500/60 bg-red-500/10 text-red-300"
                              : "border-slate-600 bg-slate-900 text-sky-300 hover:border-sky-500 hover:bg-slate-800",
                      ].join(" ")}
                    >
                      {index + 1}
                      {approved
                        ? " ✓"
                        : rejected
                          ? " ×"
                          : ""}
                    </button>
                  );
                }
              )}
            </div>
          )}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-6">
        <div className="insyt-card mb-6 p-4">
          <h3 className="mb-4 text-base font-semibold text-[var(--insyt-text-primary)]">
            Document Coding Panel
          </h3>

          <div className="space-y-3">
            {[
              "Not Responsive",
              "Not Responsive - AI",
              "Responsive",
              "Foreign Language",
              "Tech Issue",
              "Password Protected",
              "Needs Further Review",
            ].map((option) => (
              <label
                key={option}
                className="flex items-center gap-3 text-[var(--insyt-text-secondary)]"
              >
                <input
                  type="radio"
                  name="documentCoding"
                  checked={documentCoding === option}
                  disabled={forceResponsive && option !== "Responsive"}
                  onChange={() => {
                    if (forceResponsive) {
                      setDocumentCoding("Responsive");
                      return;
                    }

                    setDocumentCoding(option);
                  }}
                  className="accent-sky-600"
                />

                <span>{option}</span>
              </label>
            ))}

            {documentCoding ===
              "Needs Further Review" && (
              <div className="mt-4">
                <FormLabel>
                  Further Review Reason
                </FormLabel>

                <TextArea
                  rows={3}
                  value={furtherReviewReason}
                  onChange={setFurtherReviewReason}
                />
              </div>
            )}
          </div>
        </div>

        <div className="space-y-4">
          {Object.entries(groupedFields).length ===
          0 ? (
            <p className="text-sm text-[var(--insyt-text-muted)]">
              No protocol capture fields loaded.
            </p>
          ) : (
            Object.entries(groupedFields).map(
              ([section, sectionFields]) => {
                const isOpen =
                  openSections[section] ?? false;

                return (
                  <div
                    key={section}
                    className="overflow-hidden rounded-xl border border-[var(--insyt-border)] bg-[var(--insyt-surface-1)]"
                  >
                    <button
                      type="button"
                      onClick={() =>
                        toggleSection(section)
                      }
                      className="sticky top-0 z-10 flex w-full items-center justify-between border-b border-[var(--insyt-border)] bg-[var(--insyt-surface-2)] px-4 py-3 text-left transition-colors hover:bg-[var(--insyt-surface-hover)]"
                    >
                      <span className="font-semibold text-[var(--insyt-text-primary)]">
                        {section}
                      </span>

                      <span className="text-sky-400 text-lg font-bold">
                        {isOpen ? "−" : "+"}
                      </span>
                    </button>

                    {isOpen && (
                      <div className="max-h-72 space-y-4 overflow-y-auto border-t border-[var(--insyt-border)] p-4">
                        {sectionFields.map((field) => {
                          const fieldType =
                            normalizeFieldType(field);

                          return (
                            <div key={field.label}>
                              {fieldType === "tag" ? (
                                <>
                                  <Checkbox
                                    label={field.label}
                                    checked={Boolean(
                                      values[field.label]
                                    )}
                                    onChange={(
                                      checked
                                    ) =>
                                      updateValue(
                                        field.label,
                                        checked
                                      )
                                    }
                                  />

                                  {field.notes && (
                                    <p className="mt-1 ml-7 text-xs text-[var(--insyt-text-muted)]">
                                      {field.notes}
                                    </p>
                                  )}
                                </>
                              ) : fieldType ===
                                "textarea" ? (
                                <>
                                  <FormLabel>
                                    {field.label}
                                  </FormLabel>

                                  <TextArea
                                    rows={2}
                                    value={String(
                                      values[
                                        field.label
                                      ] ?? ""
                                    )}
                                    onChange={(
                                      value
                                    ) =>
                                      updateValue(
                                        field.label,
                                        value
                                      )
                                    }
                                  />

                                  {field.notes && (
                                    <p className="mt-1 text-xs text-[var(--insyt-text-muted)]">
                                      {field.notes}
                                    </p>
                                  )}
                                </>
                              ) : (
                                <>
                                  <FormLabel>
                                    {field.label}
                                  </FormLabel>

                                  <Input
                                    value={String(
                                      values[
                                        field.label
                                      ] ?? ""
                                    )}
                                    onChange={(
                                      value
                                    ) =>
                                      updateValue(
                                        field.label,
                                        value
                                      )
                                    }
                                  />

                                  {field.notes && (
                                    <p className="text-xs text-slate-500 mt-1">
                                      {field.notes}
                                    </p>
                                  )}
                                </>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </div>
                );
              }
            )
          )}
        </div>
      </div>

      <div className="shrink-0 space-y-3 border-t border-[var(--insyt-border)] p-6">
        
        {selectedAiEntity &&
          selectedAiEntity.status !==
            "approved" &&
          selectedAiEntity.status !==
            "rejected" && (
            <div className="space-y-2">
              <Button
                fullWidth
                onClick={() => {
                  const candidateId =
                    selectedAiEntity.id;

                  const currentValues = {
                    ...values,
                  };

                  const hasAnyValue =
                    Object.values(
                      currentValues
                    ).some((value) => {
                      if (
                        typeof value ===
                        "boolean"
                      ) {
                        return value;
                      }

                      return (
                        String(
                          value ?? ""
                        ).trim() !== ""
                      );
                    });

                  if (!hasAnyValue) {
                    setMessage(
                      "AI Entity contains no Capture values to approve."
                    );
                    return;
                  }

                  //
                  // Use the same existing entity-link
                  // workflow. The backend AI provenance
                  // flag will be added in the next step.
                  //
                  apiPost("/api/review/save", {
                    workspace,
                    client_id: clientId,
                    project_id: projectId,
                    batch_id: batchId,
                    doc_id: docId,
                    values: currentValues,
                  })
                    .then(() => {
                      setMessage(
                        "AI Entity approved and added to Linked Entities."
                      );

                      setLocalLinkedEntityAttached(
                        true
                      );

                      setDocumentCoding(
                        "Responsive"
                      );

                      onApproveAiEntity?.({
                        candidateId,
                        values: currentValues,
                      });

                      onLinkedEntitySaved?.();

                      //
                      // Move automatically to the next
                      // pending AI Entity.
                      //
                      const currentIndex =
                        aiEntities.findIndex(
                          (candidate) =>
                            candidate.id ===
                            candidateId
                        );

                      const nextCandidate =
                        aiEntities
                          .slice(
                            currentIndex + 1
                          )
                          .find(
                            (candidate) =>
                              candidate.status !==
                                "approved" &&
                              candidate.status !==
                                "rejected"
                          ) ||
                        aiEntities.find(
                          (candidate) =>
                            candidate.id !==
                              candidateId &&
                            candidate.status !==
                              "approved" &&
                            candidate.status !==
                              "rejected"
                        );

                      if (nextCandidate) {
                        setSelectedAiEntityId(
                          nextCandidate.id
                        );
                      } else {
                        clearValues();
                        setSelectedAiEntityId(
                          ""
                        );
                      }
                    })
                    .catch(() => {
                      setMessage(
                        "AI Entity approval failed."
                      );
                    });
                }}
              >
                Approve AI
              </Button>

              <Button
                fullWidth
                variant="secondary"
                onClick={() => {
                  const candidateId =
                    selectedAiEntity.id;

                  onRejectAiEntity?.(
                    candidateId
                  );

                  setMessage(
                    "AI Entity rejected."
                  );

                  const currentIndex =
                    aiEntities.findIndex(
                      (candidate) =>
                        candidate.id ===
                        candidateId
                    );

                  const nextCandidate =
                    aiEntities
                      .slice(currentIndex + 1)
                      .find(
                        (candidate) =>
                          candidate.status !==
                            "approved" &&
                          candidate.status !==
                            "rejected"
                      );

                  if (nextCandidate) {
                    setSelectedAiEntityId(
                      nextCandidate.id
                    );
                  } else {
                    clearValues();
                    setSelectedAiEntityId(
                      ""
                    );
                  }
                }}
              >
                Reject AI
              </Button>
            </div>
          )}
        
        <Button
          fullWidth
          onClick={editingEntity ? handleUpdateLinkedEntity : handleLinkEntity}
        >
          {editingEntity ? "Update Link" : "Link Entity"}
        </Button>

        {editingEntity && (
          <Button
            fullWidth
            variant="secondary"
            onClick={() => {
              clearValues();
              onEditCancel?.();
              setMessage("");
            }}
          >
            Cancel Edit
          </Button>
        )}
      </div>
    </aside>
  );
}

function QcCountRow({
  label,
  weight,
  value,
  onChange,
}: {
  label: string;
  weight: number;
  value: number;
  onChange: (value: number) => void;
}) {
  return (
    <div className="grid grid-cols-[1fr_auto_90px] items-center gap-3">
      <div className="text-sm font-medium text-[var(--insyt-text-secondary)]">
        {label}
      </div>

      <div className="text-xs text-[var(--insyt-text-muted)]">
        × {weight}
      </div>

      <input
        type="number"
        min={0}
        step={1}
        value={value}
        onChange={(event) => {
          const parsed = Number.parseInt(
            event.target.value,
            10
          );

          onChange(
            Number.isNaN(parsed)
              ? 0
              : Math.max(parsed, 0)
          );
        }}
        className="w-full rounded-lg border border-[var(--insyt-border)] bg-[var(--insyt-surface-2)] px-3 py-2 text-right text-sm text-[var(--insyt-text-primary)] outline-none focus:border-sky-500"
      />
    </div>
  );
}
