"use client";

import { useEffect, useState } from "react";

import { apiPost } from "../lib/api";

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
}: ReviewCapturePanelProps) {
  const [values, setValues] = useState<Record<string, string | boolean>>({});

  const [message, setMessage] = useState("");
  const [localLinkedEntityAttached, setLocalLinkedEntityAttached] = useState(false);

  const [openSections, setOpenSections] =
    useState<Record<string, boolean>>({});

  const [documentCoding, setDocumentCoding] =
    useState("");

  const [furtherReviewReason, setFurtherReviewReason] =
    useState("");

  useEffect(() => {
    const initialOpenState: Record<string, boolean> = {};

    fields.forEach((field) => {
      const section = field.section || "General";

      initialOpenState[section] = false;
    });

    setOpenSections(initialOpenState);
  }, [fields]);

  const forceResponsive =
    initialDocumentCoding !== "Not Responsive" &&
    (hasLinkedEntities || localLinkedEntityAttached);

  useEffect(() => {
    setLocalLinkedEntityAttached(false);
  }, [docId]);

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
      })
      .catch(() => {
        setMessage(
          "Entity link failed. Please try again."
        );
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

    const valuesToSave =
      documentCoding === "Not Responsive" && !hasCapturedValues ? {} : values;

    apiPost("/api/review/save-next", {
      workspace,
      client_id: clientId,
      project_id: projectId,
      batch_id: batchId,
      doc_id: docId,
      values: valuesToSave,
      document_coding: documentCoding,
      further_review_reason: furtherReviewReason,
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

        onSaveComplete?.();
      })
      .catch(() => {
        setMessage("Save & Next failed.");
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
    <aside className="bg-slate-900 border border-slate-800 rounded-2xl h-full flex flex-col overflow-hidden">
      <div className="shrink-0 p-6 border-b border-slate-800 space-y-3">
        <Button
          fullWidth
          onClick={handleSaveNext}
        >
          {isLastDoc ? "Save & Exit" : "Save & Next"}
        </Button>

        <h2 className="text-lg font-semibold text-white">
          Capture Panel
        </h2>
      </div>

      <div className="flex-1 overflow-y-auto p-6">
        <div className="bg-slate-950 border border-slate-800 rounded-xl p-4 mb-6">
          <h3 className="text-md font-semibold text-white mb-4">
            Document Coding Panel
          </h3>

          <div className="space-y-3">
            {[
              "Not Responsive",
              "Responsive",
              "Foreign Language",
              "Tech Issue",
              "Password Protected",
              "Needs Further Review",
            ].map((option) => (
              <label
                key={option}
                className="flex items-center gap-3 text-slate-300"
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
            <p className="text-sm text-slate-500">
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
                    className="bg-slate-950 border border-slate-800 rounded-xl overflow-hidden"
                  >
                    <button
                      type="button"
                      onClick={() =>
                        toggleSection(section)
                      }
                      className="w-full flex items-center justify-between px-4 py-3 text-left bg-slate-800 hover:bg-slate-700 border-b border-slate-800 transition sticky top-0 z-10"
                    >
                      <span className="font-semibold text-white">
                        {section}
                      </span>

                      <span className="text-sky-400 text-lg font-bold">
                        {isOpen ? "−" : "+"}
                      </span>
                    </button>

                    {isOpen && (
                      <div className="max-h-72 overflow-y-auto p-4 border-t border-slate-800 space-y-4">
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
                                    <p className="text-xs text-slate-500 mt-1 ml-7">
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
                                    <p className="text-xs text-slate-500 mt-1">
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

      <div className="shrink-0 border-t border-slate-800 p-6 space-y-3">
        <Button
          fullWidth
          onClick={handleLinkEntity}
        >
          Link Entity
        </Button>

        {message && (
          <p className="text-sm text-slate-400 mt-2">
            {message}
          </p>
        )}
      </div>
    </aside>
  );
}